#!/usr/bin/env python3
"""Run the persistent heat-index-urop version 0.3 A-E workflow."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.workflow.canonical_result import write_canonical_result
from scripts.workflow.extreme_temperature import extreme_summary, plot_pixel_extremes
from scripts.workflow.input_validation import (
    discover_dataset_groups,
    image_identifier,
    validate_group,
    write_validation_record,
)
from scripts.workflow.luhk_context import resolve_luhk_context
from scripts.workflow.models import (
    ArtifactReference,
    ContentTriageState,
    GroupInput,
    GroupRunSummary,
    LUHKProvenance,
    ManualReviewStatus,
    ProcessingRoute,
    ProcessingStatus,
    QAStatus,
    SourceMethod,
)
from scripts.workflow.part_b_adapter import run_full_part_b
from scripts.workflow.part_b_correspondence import (
    apply_part_b0_review,
    load_part_b0_reviews,
    triage_content_correspondence,
    write_part_b0_result,
)
from scripts.workflow.part_b_review import load_review_decisions, resolve_decision, verified_pilot_decisions
from scripts.workflow.part_c_adapter import load_reviewed_label_override, run_reviewed_part_c
from scripts.workflow.part_e_adapter import aggregate_canonical_results, write_run_summary
from scripts.workflow.part_e_runner import run_formal_part_e
from scripts.workflow.pilot_adapter import adapt_pilot_image, pilot_image_ids
from scripts.workflow.polygon_annotation import PolygonAnnotationUI, polygon_context_arrays
from scripts.workflow.result_index import ResultIndex, configuration_hash, sha256_file, source_hashes
from scripts.workflow.routing import route_after_part_a, route_after_part_b0, route_group
from scripts.workflow.temperature_extraction import (
    TemperatureResult,
    extract_temperature,
    load_parameter_row,
    load_temperature_override,
    resolve_irp_exe,
)


def project_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def parse_key_paths(values: list[str] | None, option: str) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values or []:
        if "=" not in value:
            raise ValueError(f"{option} expects IMAGE_ID=PATH; received {value!r}.")
        image_id, path_text = value.split("=", 1)
        if not image_id.strip() or not path_text.strip():
            raise ValueError(f"{option} expects non-empty IMAGE_ID=PATH values.")
        result[image_id.strip()] = project_path(path_text.strip())
    return result


def load_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    if not path.is_file():
        raise FileNotFoundError(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return payload


def cover_mapping() -> tuple[dict[int, str], dict[str, int], Path]:
    path = PROJECT_ROOT / "data" / "annotations" / "part_c" / "surface_cover_class_mapping.xlsx"
    table = pd.read_excel(path)
    by_id = {int(row.class_id): str(row.class_name) for row in table.itertuples(index=False)}
    by_name = {name.casefold(): class_id for class_id, name in by_id.items() if class_id not in {0, 9}}
    return by_id, by_name, path


def resolve_cover(value: str, by_id: dict[int, str], by_name: dict[str, int]) -> tuple[int, str]:
    text = value.strip()
    if not text:
        raise ValueError("Part C* requires --surface-cover or per-image polygon context.")
    try:
        class_id = int(text)
    except ValueError:
        class_id = by_name.get(text.casefold(), -1)
    if class_id not in by_id or class_id in {0, 9}:
        raise ValueError(f"Unknown or non-physical surface-cover category: {value!r}")
    return class_id, by_id[class_id]


def legacy_temperature(image_id: str) -> TemperatureResult | None:
    summary_path = PROJECT_ROOT / "outputs" / "part_d" / "summaries" / "part_d_tat3_parameter_temperature_extraction_summary.csv"
    if not summary_path.is_file():
        return None
    table = pd.read_csv(summary_path, keep_default_na=False)
    rows = table.loc[
        table["image_id"].astype(str).eq(image_id)
        & table["extraction_status"].astype(str).str.casefold().eq("success")
    ]
    if len(rows) != 1:
        return None
    row = rows.iloc[0]
    path = project_path(str(row["npy_path"]))
    if not path.is_file():
        return None
    result = load_temperature_override(
        path,
        ambient_metadata={"ambient_temperature_c": row.get("ambient_temperature_c", "")},
    )
    result.metadata.update(
        {
            "extraction_method": str(row.get("extraction_method", "legacy_part_d")),
            "ambient_temperature_c": row.get("ambient_temperature_c", ""),
            "legacy_validation_status": row.get("validation_status", ""),
        }
    )
    return result


def ambient_for_image(payload: dict[str, Any], image_id: str) -> dict[str, Any]:
    value = payload.get(image_id, payload.get("default"))
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    return {"ambient_temperature_c": value, "source": "explicit_ambient_json"}


def temperature_for_group(
    *,
    image_id: str,
    thermal_path: Path,
    native_shape: tuple[int, int],
    overrides: dict[str, Path],
    ambient_payload: dict[str, Any],
    args: argparse.Namespace,
) -> TemperatureResult:
    if image_id in overrides:
        return load_temperature_override(
            overrides[image_id],
            ambient_metadata=ambient_for_image(ambient_payload, image_id),
            native_shape=native_shape,
        )
    legacy = legacy_temperature(image_id)
    if legacy is not None:
        if legacy.matrix.shape != native_shape:
            raise ValueError(f"Legacy temperature shape {legacy.matrix.shape} does not match native thermal grid {native_shape}.")
        return legacy
    if not args.tat3_params_csv:
        raise ValueError("temperature_matrix_unavailable: provide --temperature-npy or --tat3-params-csv with DJI SDK options")
    parameters = load_parameter_row(project_path(args.tat3_params_csv), image_id)
    irp = resolve_irp_exe(
        irp_exe=args.irp_exe,
        sdk_root=args.sdk_root,
        sdk_config_path=project_path(args.sdk_config) if args.sdk_config else None,
    )
    result = extract_temperature(
        thermal_path=thermal_path,
        image_id=image_id,
        parameters=parameters,
        work_directory=PROJECT_ROOT / "data" / "processed" / "part_d" / "temperature_matrices" / "sdk_raw",
        irp_exe=irp,
        keep_raw=args.keep_sdk_raw,
    )
    if result.matrix.shape != native_shape:
        raise ValueError(f"SDK temperature shape {result.matrix.shape} does not match native thermal grid {native_shape}.")
    return result


def qa_enum(status: str) -> QAStatus:
    return QAStatus(status) if status in {item.value for item in QAStatus} else QAStatus.WARN


def selected_groups(args: argparse.Namespace, config: dict[str, Any]) -> list[GroupInput]:
    if args.mode == "selected":
        return [
            GroupInput(
                group_id=f"selected-{index:03d}::{image_identifier(Path(thermal))}",
                visible_path=visible,
                thermal_path=thermal,
                dataset_id=args.dataset_id or "selected",
            )
            for index, (visible, thermal) in enumerate(args.group, start=1)
        ]
    dataset_value = Path(args.dataset)
    if not dataset_value.is_absolute():
        dataset_value = project_path(config["dataset_root"]) / dataset_value
    return discover_dataset_groups(dataset_value, args.dataset_id or Path(args.dataset).name)


def polygon_payload_for_image(payload: dict[str, Any], image_id: str) -> dict[str, Any]:
    value = payload.get(image_id, {})
    if isinstance(value, list):
        return {"review_status": "accepted", "coordinates": value}
    if not isinstance(value, dict):
        raise ValueError(f"Polygon JSON entry for {image_id} must be coordinates or an object.")
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/workflow_v0_3.json")
    parser.add_argument("--part-b0-review", help="Explicit Part B0 accept/reject/cancel decisions by group/image ID.")
    parser.add_argument("--part-b-review", help="Final full-Part-B decisions; automatic candidates never accept alignment.")
    parser.add_argument("--part-c-review", action="append", help="IMAGE_ID=accepted/draft superpixel review JSON.")
    parser.add_argument("--launch-part-c-gui", action="store_true")
    parser.add_argument("--polygon-json", help="Per-image polygon coordinates and target/LUHK/cover context.")
    parser.add_argument("--surface-cover", default="", help="Part C* physical category fallback.")
    parser.add_argument("--target-name", default="")
    parser.add_argument("--target-id", default="", help="Stable cross-capture target identifier for temporal linkage.")
    parser.add_argument("--luhk", default="", help="Part C* controlled LUHK category fallback.")
    parser.add_argument("--luhk-provenance", choices=["official_luhk_lookup", "user_supplied_luhk", "unknown"], default="unknown")
    parser.add_argument("--reviewer-confidence", choices=["", "low", "medium", "high"], default="")
    parser.add_argument("--notes", default="")
    parser.add_argument("--temperature-npy", action="append", help="IMAGE_ID=PATH override; repeatable.")
    parser.add_argument("--ambient-json", help="Ambient metadata keyed by image ID for NPY overrides.")
    parser.add_argument("--normal-labels-npy", action="append", help="Compatibility IMAGE_ID=PATH; requires review manifest.")
    parser.add_argument("--normal-review-manifest", action="append", help="IMAGE_ID=PATH companion for --normal-labels-npy.")
    parser.add_argument("--tat3-params-csv", default="")
    parser.add_argument("--sdk-config", default="config/part_d_sdk.local.json")
    parser.add_argument("--sdk-root", default="")
    parser.add_argument("--irp-exe", default="")
    parser.add_argument("--keep-sdk-raw", action="store_true")
    parser.add_argument("--max-groups", type=int)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--no-part-e", action="store_true")
    parser.add_argument("--part-e-dry-run", action="store_true")
    parser.add_argument("--write-full-pixel-csv", action="store_true")
    subparsers = parser.add_subparsers(dest="mode", required=True)
    selected = subparsers.add_parser("selected", help="Process explicit V/T groups.")
    selected.add_argument("--group", nargs=2, metavar=("VISIBLE", "THERMAL"), action="append", required=True)
    selected.add_argument("--dataset-id", default="selected")
    dataset = subparsers.add_parser("dataset", help="Process every thermal group in a dataset.")
    dataset.add_argument("--dataset", required=True)
    dataset.add_argument("--dataset-id", default="")
    return parser.parse_args()


def attach_extreme_outputs(manifest: Any, manifest_path: Path) -> None:
    pixels = pd.read_parquet(manifest_path.parent / manifest.artifacts["pixels"].path)
    summary, coordinates = extreme_summary(pixels)
    summary_path = manifest_path.parent / "extreme_temperature_summary.csv"
    coordinates_path = manifest_path.parent / "extreme_temperature_coordinates.csv"
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    coordinates.to_csv(coordinates_path, index=False, encoding="utf-8-sig")
    matrix = np.load(manifest_path.parent / manifest.artifacts["temperature"].path, allow_pickle=False)
    eligible = pixels["analysis_eligible"].to_numpy(dtype=bool).reshape(matrix.shape)
    figure_path = manifest_path.parent / "extreme_temperature_locations.png"
    plot_pixel_extremes(
        matrix=matrix,
        eligible_mask=eligible,
        output_path=figure_path,
        image_id=manifest.image_id,
        source_annotation=(
            f"measurement_type={manifest.measurement_type.value}; source={manifest.source_method.value}; "
            f"surface_cover_provenance={manifest.surface_cover_provenance}; luhk_provenance={manifest.luhk_provenance}"
        ),
        polygon_coordinates=manifest.polygon_coordinates,
    )
    for name, path in (
        ("extreme_summary", summary_path),
        ("extreme_coordinates", coordinates_path),
        ("extreme_location_figure", figure_path),
        ("extreme_location_figure_pdf", figure_path.with_suffix(".pdf")),
    ):
        manifest.artifacts[name] = ArtifactReference(path=path.name, sha256=sha256_file(path))
    temporary = manifest_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(manifest_path)


def main() -> int:
    args = parse_args()
    config = load_json(project_path(args.config))
    groups = selected_groups(args, config)
    if args.max_groups is not None:
        if args.max_groups < 1:
            raise ValueError("--max-groups must be positive.")
        if len(groups) > args.max_groups:
            raise ValueError(f"Request contains {len(groups)} groups, exceeding --max-groups={args.max_groups}.")
    part_b0_reviews = load_part_b0_reviews(project_path(args.part_b0_review) if args.part_b0_review else None)
    explicit_part_b = load_review_decisions(project_path(args.part_b_review) if args.part_b_review else None)
    pilot_reviews = verified_pilot_decisions(PROJECT_ROOT)
    polygons = load_json(project_path(args.polygon_json) if args.polygon_json else None)
    ambient_payload = load_json(project_path(args.ambient_json) if args.ambient_json else None)
    temperature_overrides = parse_key_paths(args.temperature_npy, "--temperature-npy")
    label_overrides = parse_key_paths(args.normal_labels_npy, "--normal-labels-npy")
    label_manifests = parse_key_paths(args.normal_review_manifest, "--normal-review-manifest")
    part_c_reviews = parse_key_paths(args.part_c_review, "--part-c-review")
    cover_names, cover_ids, cover_mapping_path = cover_mapping()
    output_root = project_path(config["canonical_output_root"])
    index = ResultIndex(project_path(config["result_index"]))
    pilot_ids = set(pilot_image_ids(PROJECT_ROOT))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_directory = project_path(config["run_output_root"]) / f"run_{stamp}"
    run_directory.mkdir(parents=True, exist_ok=True)
    summaries: list[GroupRunSummary] = []
    successful_manifests: list[Path] = []

    for group in groups:
        image_id = image_identifier(Path(group.thermal_path))
        group_dir = run_directory / "groups" / image_id
        polygon_input = polygon_payload_for_image(polygons, image_id)
        selected_part_b = explicit_part_b.get(group.group_id) or explicit_part_b.get(image_id)
        selected_b0 = part_b0_reviews.get(group.group_id) or part_b0_reviews.get(image_id)
        group_configuration = {
            "schema_version": config.get("schema_version", "0.2.0"),
            "processing_version": config.get("processing_version", "heat-index-urop-0.3"),
            "part_b0": config.get("part_b0", {}),
            "part_b0_review": selected_b0.value if selected_b0 else "",
            "part_b_review": selected_part_b.to_dict() if selected_part_b else {},
            "part_c_review": part_c_reviews.get(image_id).resolve().as_posix() if image_id in part_c_reviews else "",
            "polygon": polygon_input,
            "surface_cover": args.surface_cover,
            "target_name": args.target_name,
            "target_id": args.target_id,
            "luhk": args.luhk,
            "luhk_provenance": args.luhk_provenance,
            "ambient": ambient_for_image(ambient_payload, image_id),
        }
        group_config_hash = configuration_hash(group_configuration)
        source_paths = [Path(group.visible_path), Path(group.thermal_path), cover_mapping_path]
        for mapping in (temperature_overrides, label_overrides, label_manifests, part_c_reviews):
            if image_id in mapping:
                source_paths.append(mapping[image_id])
        if args.tat3_params_csv:
            source_paths.append(project_path(args.tat3_params_csv))
        if args.sdk_config and project_path(args.sdk_config).is_file():
            source_paths.append(project_path(args.sdk_config))
        hashes = source_hashes(source_paths)
        dependencies = {
            "group_configuration": group_config_hash,
            "surface_cover_mapping": sha256_file(cover_mapping_path),
        }
        cache = index.check(
            image_id,
            source_file_hashes=hashes,
            configuration_hash_value=group_config_hash,
            dependency_fingerprints=dependencies,
        )
        if cache.compatible:
            successful_manifests.append(Path(cache.manifest_path))
            summaries.append(GroupRunSummary(
                group.group_id, image_id, ProcessingRoute.CACHE, ProcessingStatus.CACHE_HIT,
                reason="compatible_canonical_result", canonical_manifest_path=cache.manifest_path, cache_hit=True,
            ))
            continue

        override_shape = None
        if image_id in temperature_overrides and temperature_overrides[image_id].is_file():
            override_shape = tuple(np.load(temperature_overrides[image_id], mmap_mode="r", allow_pickle=False).shape)
        validation = validate_group(group, temperature_shape=override_shape)
        image_id = validation.image_id
        part_a_path = write_validation_record(validation, group_dir / "part_a.json")
        if args.validate_only:
            summaries.append(GroupRunSummary(
                group.group_id, image_id, ProcessingRoute.INCOMPLETE,
                ProcessingStatus.READY if not validation.fatal_errors else ProcessingStatus.FAILED,
                reason=";".join(validation.errors or validation.warnings) or "validated",
                part_a_record_path=part_a_path.resolve().as_posix(),
            ))
            continue
        part_a_route = route_after_part_a(validation)
        if part_a_route.status == ProcessingStatus.FAILED:
            summaries.append(GroupRunSummary(
                group.group_id, image_id, part_a_route.route, part_a_route.status, part_a_route.reason,
                part_a_record_path=part_a_path.resolve().as_posix(),
            ))
            continue

        part_b0 = None
        part_b = None
        route = part_a_route
        if part_a_route.reason == "run_part_b0":
            part_b0 = triage_content_correspondence(
                group_id=group.group_id,
                image_id=image_id,
                visible_path=Path(validation.visible_path),
                thermal_path=Path(validation.thermal_path),
                output_directory=group_dir / "part_b0",
                thresholds=config.get("part_b0", {}).get("thresholds", {}),
            )
            if validation.pairing_uncertain and selected_b0 is None:
                part_b0.triage_state = ContentTriageState.NEEDS_MANUAL_REVIEW
                part_b0.reasons.append("part_a_pairing_uncertainty_requires_explicit_part_b0_review")
            if selected_b0 is None and image_id in pilot_reviews:
                selected_b0 = ManualReviewStatus.ACCEPTED
            part_b0 = apply_part_b0_review(part_b0, selected_b0)
            write_part_b0_result(part_b0, group_dir / "part_b0" / "part_b0.json")
            route = route_after_part_b0(part_b0)
            if route.status in {ProcessingStatus.AWAITING_PART_B0_REVIEW, ProcessingStatus.CANCELLED}:
                summaries.append(GroupRunSummary(
                    group.group_id, image_id, route.route, route.status, route.reason,
                    part_a_record_path=part_a_path.resolve().as_posix(),
                    part_b0_record_path=(group_dir / "part_b0" / "part_b0.json").resolve().as_posix(),
                ))
                continue
            if route.reason.endswith("run_full_part_b") or route.reason == "part_b0_match_candidate_run_full_part_b":
                final_review = resolve_decision(
                    group_id=group.group_id,
                    image_id=image_id,
                    explicit=explicit_part_b,
                    verified_pilot=pilot_reviews,
                )
                part_b = run_full_part_b(
                    group_id=group.group_id,
                    image_id=image_id,
                    visible_path=Path(validation.visible_path),
                    thermal_path=Path(validation.thermal_path),
                    part_b0=part_b0,
                    output_directory=group_dir / "part_b",
                    review_decision=final_review,
                )
                route = route_group(part_b, thermal_valid=validation.thermal_valid)
                if route.status in {ProcessingStatus.AWAITING_PART_B_REVIEW, ProcessingStatus.CANCELLED}:
                    summaries.append(GroupRunSummary(
                        group.group_id, image_id, route.route, route.status, route.reason,
                        part_a_record_path=part_a_path.resolve().as_posix(),
                        part_b0_record_path=(group_dir / "part_b0" / "part_b0.json").resolve().as_posix(),
                        part_b_record_path=(group_dir / "part_b" / "part_b.json").resolve().as_posix(),
                    ))
                    continue

        try:
            native_shape = (
                int(validation.thermal_camera_metadata["height"]),
                int(validation.thermal_camera_metadata["width"]),
            )
            if route.route == ProcessingRoute.NORMAL_VT and image_id in pilot_ids:
                manifest, manifest_path = adapt_pilot_image(
                    PROJECT_ROOT,
                    image_id,
                    output_root=output_root,
                    configuration_hash_value=group_config_hash,
                    source_file_hashes_value=hashes,
                )
                manifest.dependency_fingerprints = dependencies
                manifest.part_a = validation.to_dict()
                manifest.part_b0 = part_b0.to_dict() if part_b0 else {}
                manifest.part_b = part_b.to_dict() if part_b else {}
                temporary = manifest_path.with_suffix(".json.tmp")
                temporary.write_text(json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
                temporary.replace(manifest_path)
            elif route.route == ProcessingRoute.NORMAL_VT:
                temperature = temperature_for_group(
                    image_id=image_id,
                    thermal_path=Path(validation.thermal_path),
                    native_shape=native_shape,
                    overrides=temperature_overrides,
                    ambient_payload=ambient_payload,
                    args=args,
                )
                if image_id in label_overrides:
                    if image_id not in label_manifests:
                        raise ValueError("normal_part_c_unreviewed_label_override_rejected")
                    labels, known, review_metadata = load_reviewed_label_override(
                        labels_path=label_overrides[image_id],
                        manifest_path=label_manifests[image_id],
                        image_id=image_id,
                        expected_shape=native_shape,
                    )
                    shadow = None
                    review_path = label_manifests[image_id]
                else:
                    part_c_result = run_reviewed_part_c(
                        image_id=image_id,
                        pair_id=validation.pair_id,
                        visible_path=Path(validation.visible_path),
                        thermal_path=Path(validation.thermal_path),
                        accepted_crop=part_b.candidate_crop if part_b else [],
                        output_directory=group_dir / "part_c",
                        class_mapping=cover_names,
                        review_artifact_path=part_c_reviews.get(image_id),
                        launch_gui=args.launch_part_c_gui,
                    )
                    if part_c_result is None:
                        summaries.append(GroupRunSummary(
                            group.group_id, image_id, ProcessingRoute.AWAITING_REVIEW,
                            ProcessingStatus.AWAITING_PART_C_REVIEW, "part_c_superpixel_review_not_accepted",
                            part_a_record_path=part_a_path.resolve().as_posix(),
                            part_b0_record_path=(group_dir / "part_b0" / "part_b0.json").resolve().as_posix(),
                            part_b_record_path=(group_dir / "part_b" / "part_b.json").resolve().as_posix(),
                        ))
                        continue
                    labels, known, shadow = part_c_result.labels, part_c_result.known_mask, part_c_result.shadow_mask
                    review_metadata = part_c_result.review_metadata
                    review_path = part_c_result.review_artifact_path
                derived = {"part_c_review": sha256_file(review_path)}
                manifest, manifest_path = write_canonical_result(
                    output_root=output_root,
                    image_id=image_id,
                    group_id=group.group_id,
                    pair_id=validation.pair_id,
                    dataset_id=validation.dataset_id,
                    visible_path=validation.visible_path,
                    thermal_path=validation.thermal_path,
                    temperature=temperature.matrix,
                    labels=labels,
                    known_mask=known,
                    processing_route=ProcessingRoute.NORMAL_VT,
                    source_method=SourceMethod.VISIBLE_REVIEW,
                    review_status=ManualReviewStatus.ACCEPTED,
                    qa_status=qa_enum(temperature.qa_status),
                    configuration_hash=group_config_hash,
                    source_file_hashes=hashes,
                    dependency_fingerprints=dependencies,
                    derived_input_hashes=derived,
                    surface_cover_names=cover_names,
                    shadow_mask=shadow,
                    temperature_metadata={**temperature.metadata, "capture_time": validation.capture_time},
                    ambient_metadata=ambient_for_image(ambient_payload, image_id),
                    validation_status=validation.validation_status.value,
                    part_a=validation.to_dict(),
                    part_b0=part_b0.to_dict() if part_b0 else {},
                    part_b=part_b.to_dict() if part_b else {},
                    annotation_review=review_metadata,
                    scene_correspondence=part_b.scene_correspondence.value if part_b else "indeterminate",
                    coverage_class=part_b.coverage_class.value if part_b else "indeterminate",
                    notes=args.notes,
                )
            elif route.route == ProcessingRoute.THERMAL_POLYGON:
                status = str(polygon_input.get("review_status", "")).casefold()
                if status in {"cancelled", "canceled"}:
                    summaries.append(GroupRunSummary(
                        group.group_id, image_id, ProcessingRoute.CANCELLED, ProcessingStatus.CANCELLED,
                        "polygon_annotation_cancelled", part_a_record_path=part_a_path.resolve().as_posix(),
                    ))
                    continue
                temperature = temperature_for_group(
                    image_id=image_id,
                    thermal_path=Path(validation.thermal_path),
                    native_shape=native_shape,
                    overrides=temperature_overrides,
                    ambient_payload=ambient_payload,
                    args=args,
                )
                target_name = str(polygon_input.get("target_name", args.target_name)).strip()
                target_id = str(polygon_input.get("target_id", args.target_id)).strip()
                surface_value = str(polygon_input.get("surface_cover", args.surface_cover))
                class_id, class_name = resolve_cover(surface_value, cover_names, cover_ids)
                luhk = resolve_luhk_context(
                    str(polygon_input.get("luhk", args.luhk)),
                    str(polygon_input.get("luhk_provenance", args.luhk_provenance)),
                )
                if not target_name:
                    raise ValueError("Part C* requires a target name.")
                coordinates = polygon_input.get("coordinates", [])
                confidence = str(polygon_input.get("reviewer_confidence", args.reviewer_confidence))
                notes = str(polygon_input.get("notes", args.notes))
                if not coordinates:
                    annotation = PolygonAnnotationUI(
                        Path(validation.thermal_path),
                        class_name,
                        target_name=target_name,
                        luhk_category=luhk.category,
                        luhk_code=luhk.code,
                        luhk_provenance=luhk.provenance.value,
                        reviewer_confidence=confidence,
                    ).run()
                    if annotation.cancelled or not annotation.accepted:
                        summaries.append(GroupRunSummary(
                            group.group_id, image_id, ProcessingRoute.CANCELLED, ProcessingStatus.CANCELLED,
                            "polygon_annotation_cancelled", part_a_record_path=part_a_path.resolve().as_posix(),
                        ))
                        continue
                    coordinates = [[x, y] for x, y in annotation.coordinates]
                labels, known, luhk_labels, luhk_known, target_mask = polygon_context_arrays(
                    coordinates, temperature.matrix.shape, class_id, luhk.code
                )
                annotation_review = {
                    "review_status": "accepted",
                    "reviewer_confidence": confidence,
                    "notes": notes,
                    "coordinates": coordinates,
                    "thermal_dimensions": list(native_shape),
                    "temperature_dimensions": list(temperature.matrix.shape),
                    "surface_cover_provenance": SourceMethod.THERMAL_POLYGON_USER_ANNOTATION.value,
                    "luhk_provenance": luhk.provenance.value,
                    "known_pixel_count": int(known.sum()),
                    "unknown_pixel_count": int(known.size - known.sum()),
                }
                manifest, manifest_path = write_canonical_result(
                    output_root=output_root,
                    image_id=image_id,
                    group_id=group.group_id,
                    pair_id=validation.pair_id,
                    dataset_id=validation.dataset_id,
                    visible_path=validation.visible_path,
                    thermal_path=validation.thermal_path,
                    temperature=temperature.matrix,
                    labels=labels,
                    known_mask=known,
                    target_mask=target_mask,
                    luhk_labels=luhk_labels,
                    luhk_known_mask=luhk_known,
                    processing_route=ProcessingRoute.THERMAL_POLYGON,
                    source_method=SourceMethod.THERMAL_POLYGON_USER_ANNOTATION,
                    review_status=ManualReviewStatus.ACCEPTED,
                    qa_status=qa_enum(temperature.qa_status),
                    configuration_hash=group_config_hash,
                    source_file_hashes=hashes,
                    dependency_fingerprints=dependencies,
                    surface_cover_names=cover_names,
                    surface_cover_class_id=class_id,
                    surface_cover_category=class_name,
                    target_id=target_id,
                    target_name=target_name,
                    polygon_coordinates=coordinates,
                    reviewer_confidence=confidence,
                    luhk_category=luhk.category,
                    luhk_code=luhk.code,
                    luhk_provenance=luhk.provenance.value,
                    temperature_metadata={**temperature.metadata, "capture_time": validation.capture_time},
                    ambient_metadata=ambient_for_image(ambient_payload, image_id),
                    validation_status=validation.validation_status.value,
                    part_a=validation.to_dict(),
                    part_b0=part_b0.to_dict() if part_b0 else {},
                    part_b=part_b.to_dict() if part_b else {},
                    annotation_review=annotation_review,
                    scene_correspondence=part_b.scene_correspondence.value if part_b else "rejected",
                    coverage_class=part_b.coverage_class.value if part_b else "no_usable_overlap",
                    exclusions=["outside_polygon:target_context_unknown:not_target_analysis_eligible"],
                    notes=notes,
                )
            else:
                raise ValueError(f"Unsupported terminal route: {route.route.value}")

            if manifest.processing_status == ProcessingStatus.SUCCESS and manifest.qa_status != QAStatus.FAIL:
                attach_extreme_outputs(manifest, manifest_path)
                index.register(manifest_path, manifest)
                successful_manifests.append(manifest_path)
                status = ProcessingStatus.SUCCESS
                reason = "canonical_result_created"
            else:
                status = ProcessingStatus.FAILED
                reason = "temperature_qa_failed_excluded_from_part_e"
            summaries.append(GroupRunSummary(
                group.group_id, image_id, manifest.processing_route, status, reason,
                canonical_manifest_path=manifest_path.resolve().as_posix(),
                part_a_record_path=part_a_path.resolve().as_posix(),
                part_b0_record_path=(group_dir / "part_b0" / "part_b0.json").resolve().as_posix() if part_b0 else "",
                part_b_record_path=(group_dir / "part_b" / "part_b.json").resolve().as_posix() if part_b else "",
            ))
        except (OSError, ValueError, RuntimeError) as exc:
            summaries.append(GroupRunSummary(
                group.group_id, image_id, ProcessingRoute.INCOMPLETE, ProcessingStatus.INCOMPLETE,
                reason=f"{type(exc).__name__}:{exc}", part_a_record_path=part_a_path.resolve().as_posix(),
            ))

    index.save()
    run_summary_path = run_directory / "run_summary.json"
    write_run_summary(run_summary_path, summaries)
    if successful_manifests and not args.no_part_e and not args.validate_only:
        part_e = config["part_e"]
        aggregate_canonical_results(
            successful_manifests,
            output_parquet=project_path(part_e["canonical_parquet"]),
            summary_csv=project_path(part_e["summary_csv"]),
            write_full_csv=args.write_full_pixel_csv or bool(part_e.get("write_full_pixel_csv", False)),
            dashboard_directory=project_path(part_e.get("dashboard_directory", "outputs/part_e/source_dashboard")),
        )
        if bool(part_e.get("formal_enabled", False)):
            run_formal_part_e(
                successful_manifests,
                output_root=project_path(part_e.get("formal_output_root", "outputs/part_e/schema_0_2")),
                run_summary_path=run_summary_path,
                resume=True,
                dry_run=args.part_e_dry_run,
            )
    print(f"Groups requested: {len(groups)}")
    for summary in summaries:
        print(f"{summary.group_id}: {summary.status.value} via {summary.route.value} - {summary.reason}")
    print(f"Run summary: {display_path(run_summary_path)}")
    failed = sum(row.status in {ProcessingStatus.FAILED, ProcessingStatus.INCOMPLETE} for row in summaries)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
