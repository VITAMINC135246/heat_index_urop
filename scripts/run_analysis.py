#!/usr/bin/env python3
"""Run the modular heat-index-urop version 0.1 local workflow.

Examples
--------
Selected-file mode::

    python scripts/run_analysis.py --surface-cover grass_low_vegetation selected \
        --group path/to/image_V.JPG path/to/image_T.JPG

Dataset mode::

    python scripts/run_analysis.py dataset --dataset 20260202_Thermal_HKUST

Automatic Part B scores are never final acceptance. Explicit decisions may be
provided with ``--part-b-review``; otherwise valid thermal images use Part C*.
"""

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

from scripts.workflow.canonical_result import UNKNOWN_LABEL_ID, write_canonical_result
from scripts.workflow.input_validation import discover_dataset_groups, image_identifier, validate_group
from scripts.workflow.models import (
    GroupInput,
    GroupRunSummary,
    ManualReviewStatus,
    ProcessingRoute,
    ProcessingStatus,
    QAStatus,
    SourceMethod,
)
from scripts.workflow.part_b_review import load_review_decisions, resolve_decision, verified_pilot_decisions
from scripts.workflow.part_e_adapter import aggregate_canonical_results, write_run_summary
from scripts.workflow.pilot_adapter import adapt_pilot_image, pilot_image_ids
from scripts.workflow.polygon_annotation import PolygonAnnotationUI, labelled_polygon_arrays
from scripts.workflow.result_index import ResultIndex, configuration_hash, source_hashes
from scripts.workflow.routing import route_group
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


def cover_mapping() -> tuple[dict[int, str], dict[str, int]]:
    path = PROJECT_ROOT / "data" / "annotations" / "part_c" / "surface_cover_class_mapping.xlsx"
    table = pd.read_excel(path)
    by_id = {int(row.class_id): str(row.class_name) for row in table.itertuples(index=False)}
    by_name = {name.casefold(): class_id for class_id, name in by_id.items() if class_id not in {0, 9}}
    return by_id, by_name


def resolve_cover(value: str, by_id: dict[int, str], by_name: dict[str, int]) -> tuple[int, str]:
    text = value.strip()
    if not text:
        raise ValueError("Part C* requires --surface-cover.")
    try:
        class_id = int(text)
    except ValueError:
        class_id = by_name.get(text.casefold(), UNKNOWN_LABEL_ID)
    if class_id not in by_id or class_id in {0, 9}:
        raise ValueError(f"Unknown or non-physical surface-cover category: {value!r}")
    return class_id, by_id[class_id]


def legacy_temperature(image_id: str) -> TemperatureResult | None:
    summary_path = (
        PROJECT_ROOT / "outputs" / "part_d" / "summaries" / "part_d_tat3_parameter_temperature_extraction_summary.csv"
    )
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
    result = load_temperature_override(path)
    result.metadata.update(
        {
            "extraction_method": str(row.get("extraction_method", "legacy_part_d")),
            "ambient_temperature_c": row.get("ambient_temperature_c", ""),
            "legacy_validation_status": row.get("validation_status", ""),
        }
    )
    return result


def temperature_for_group(
    *,
    image_id: str,
    thermal_path: Path,
    overrides: dict[str, Path],
    args: argparse.Namespace,
) -> TemperatureResult:
    if image_id in overrides:
        return load_temperature_override(overrides[image_id])
    legacy = legacy_temperature(image_id)
    if legacy is not None:
        return legacy
    if not args.tat3_params_csv:
        raise ValueError(
            "temperature_matrix_unavailable: provide --temperature-npy IMAGE_ID=PATH or --tat3-params-csv with DJI SDK options"
        )
    parameters = load_parameter_row(project_path(args.tat3_params_csv), image_id)
    irp = resolve_irp_exe(
        irp_exe=args.irp_exe,
        sdk_root=args.sdk_root,
        sdk_config_path=project_path(args.sdk_config) if args.sdk_config else None,
    )
    return extract_temperature(
        thermal_path=thermal_path,
        image_id=image_id,
        parameters=parameters,
        work_directory=PROJECT_ROOT / "data" / "processed" / "part_d" / "temperature_matrices" / "sdk_raw",
        irp_exe=irp,
        keep_raw=args.keep_sdk_raw,
    )


def qa_enum(status: str) -> QAStatus:
    return QAStatus(status) if status in {item.value for item in QAStatus} else QAStatus.WARN


def polygon_coordinates(payload: dict[str, Any], image_id: str) -> tuple[list[list[float]], bool]:
    value = payload.get(image_id)
    if value is None:
        return [], False
    if isinstance(value, list):
        return value, False
    if not isinstance(value, dict):
        raise ValueError(f"Polygon JSON entry for {image_id} must be coordinates or an object.")
    status = str(value.get("review_status", "accepted")).casefold()
    if status in {"cancelled", "canceled"}:
        return [], True
    if status != "accepted":
        raise ValueError(f"Polygon JSON review_status must be accepted or cancelled for {image_id}.")
    coordinates = value.get("coordinates", [])
    if not isinstance(coordinates, list):
        raise ValueError(f"Polygon coordinates must be a list for {image_id}.")
    return coordinates, False


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/workflow_v0_1.json")
    parser.add_argument("--part-b-review", help="JSON file keyed by group_id or image_id with explicit manual decisions.")
    parser.add_argument("--polygon-json", help="Optional non-interactive accepted/cancelled polygon decisions by image_id.")
    parser.add_argument("--surface-cover", default="", help="Required physical class name or ID for Part C*.")
    parser.add_argument("--target-name", default="")
    parser.add_argument("--reviewer-confidence", choices=["", "low", "medium", "high"], default="")
    parser.add_argument("--temperature-npy", action="append", help="IMAGE_ID=PATH override; repeatable.")
    parser.add_argument("--normal-labels-npy", action="append", help="IMAGE_ID=PATH reviewed normal-Part-C labels.")
    parser.add_argument("--known-mask-npy", action="append", help="Optional IMAGE_ID=PATH known-mask override.")
    parser.add_argument("--shadow-mask-npy", action="append", help="Optional IMAGE_ID=PATH shadow mask.")
    parser.add_argument("--tat3-params-csv", default="")
    parser.add_argument("--sdk-config", default="config/part_d_sdk.local.json")
    parser.add_argument("--sdk-root", default="")
    parser.add_argument("--irp-exe", default="")
    parser.add_argument("--keep-sdk-raw", action="store_true")
    parser.add_argument("--max-groups", type=int, help="Optional safety limit established by the caller/benchmark.")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--no-part-e", action="store_true")
    parser.add_argument("--write-full-pixel-csv", action="store_true")
    subparsers = parser.add_subparsers(dest="mode", required=True)
    selected = subparsers.add_parser("selected", help="Process explicit V/T groups.")
    selected.add_argument("--group", nargs=2, metavar=("VISIBLE", "THERMAL"), action="append", required=True)
    selected.add_argument("--dataset-id", default="selected")
    dataset = subparsers.add_parser("dataset", help="Process every eligible V/T group in a dataset.")
    dataset.add_argument("--dataset", required=True, help="Dataset name below dataset_root or an absolute directory.")
    dataset.add_argument("--dataset-id", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = project_path(args.config)
    config = load_json(config_path)
    groups = selected_groups(args, config)
    if args.max_groups is not None:
        if args.max_groups < 1:
            raise ValueError("--max-groups must be positive.")
        if len(groups) > args.max_groups:
            raise ValueError(f"Request contains {len(groups)} groups, exceeding --max-groups={args.max_groups}.")
    explicit_reviews = load_review_decisions(project_path(args.part_b_review) if args.part_b_review else None)
    pilot_reviews = verified_pilot_decisions(PROJECT_ROOT)
    polygons = load_json(project_path(args.polygon_json) if args.polygon_json else None)
    temperature_overrides = parse_key_paths(args.temperature_npy, "--temperature-npy")
    label_overrides = parse_key_paths(args.normal_labels_npy, "--normal-labels-npy")
    known_overrides = parse_key_paths(args.known_mask_npy, "--known-mask-npy")
    shadow_overrides = parse_key_paths(args.shadow_mask_npy, "--shadow-mask-npy")
    cover_names, cover_ids = cover_mapping()
    processing_configuration = {
        "workflow": config,
        "surface_cover": args.surface_cover,
        "target_name": args.target_name,
        "reviewer_confidence": args.reviewer_confidence,
        "part_b_review": load_json(project_path(args.part_b_review)) if args.part_b_review else {},
        "polygon_input": polygons,
    }
    config_hash = configuration_hash(processing_configuration)
    output_root = project_path(config["canonical_output_root"])
    index = ResultIndex(project_path(config["result_index"]))
    summaries: list[GroupRunSummary] = []
    successful_manifests: list[Path] = []
    pilot_ids = set(pilot_image_ids(PROJECT_ROOT))

    for group in groups:
        image_id = image_identifier(Path(group.thermal_path))
        source_paths = [Path(group.visible_path), Path(group.thermal_path)]
        for mapping in (temperature_overrides, label_overrides, known_overrides, shadow_overrides):
            if image_id in mapping:
                source_paths.append(mapping[image_id])
        hashes = source_hashes(source_paths)
        cache = index.check(
            image_id,
            source_file_hashes=hashes,
            configuration_hash_value=config_hash,
        )
        if cache.compatible:
            successful_manifests.append(Path(cache.manifest_path))
            summaries.append(
                GroupRunSummary(
                    group.group_id, image_id, ProcessingRoute.CACHE, ProcessingStatus.CACHE_HIT,
                    reason="compatible_canonical_result", canonical_manifest_path=cache.manifest_path, cache_hit=True,
                )
            )
            continue

        validation = validate_group(group)
        image_id = validation.image_id
        if args.validate_only:
            summaries.append(
                GroupRunSummary(
                    group.group_id, image_id, ProcessingRoute.INCOMPLETE,
                    ProcessingStatus.READY if not validation.errors else ProcessingStatus.FAILED,
                    reason=";".join(validation.errors or validation.warnings) or "validated",
                )
            )
            continue
        if not validation.thermal_valid:
            summaries.append(
                GroupRunSummary(group.group_id, image_id, ProcessingRoute.FAILED, ProcessingStatus.FAILED,
                                reason="missing_or_invalid_thermal_image")
            )
            continue
        decision = resolve_decision(
            group_id=group.group_id,
            image_id=image_id,
            explicit=explicit_reviews,
            verified_pilot=pilot_reviews,
        )
        route = route_group(decision, thermal_valid=validation.thermal_valid)
        if route.status in {ProcessingStatus.FAILED, ProcessingStatus.CANCELLED}:
            summaries.append(GroupRunSummary(group.group_id, image_id, route.route, route.status, route.reason))
            continue
        try:
            if route.route == ProcessingRoute.NORMAL_VT and image_id in pilot_ids:
                manifest, manifest_path = adapt_pilot_image(
                    PROJECT_ROOT,
                    image_id,
                    output_root=output_root,
                    configuration_hash_value=config_hash,
                    source_file_hashes_value=hashes,
                )
            elif route.route == ProcessingRoute.NORMAL_VT:
                if image_id not in label_overrides:
                    raise ValueError("normal_part_c_outputs_unavailable: provide --normal-labels-npy IMAGE_ID=PATH")
                temperature = temperature_for_group(
                    image_id=image_id,
                    thermal_path=Path(validation.thermal_path),
                    overrides=temperature_overrides,
                    args=args,
                )
                raw_labels = np.load(label_overrides[image_id]).astype(np.int16)
                known = (
                    np.load(known_overrides[image_id]).astype(bool)
                    if image_id in known_overrides
                    else ~np.isin(raw_labels, [UNKNOWN_LABEL_ID, 0, 9])
                )
                labels = raw_labels.copy()
                labels[~known] = UNKNOWN_LABEL_ID
                shadow = np.load(shadow_overrides[image_id]) if image_id in shadow_overrides else None
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
                    configuration_hash=config_hash,
                    source_file_hashes=hashes,
                    surface_cover_names=cover_names,
                    shadow_mask=shadow,
                    temperature_metadata={**temperature.metadata, "capture_time": validation.capture_time},
                    validation_status=validation.validation_status.value,
                    scene_correspondence=decision.scene_correspondence.value,
                    coverage_class=decision.coverage_class.value,
                    notes=decision.notes,
                )
            else:
                class_id, class_name = resolve_cover(args.surface_cover, cover_names, cover_ids)
                coordinates, cancelled = polygon_coordinates(polygons, image_id)
                if not coordinates and not cancelled:
                    annotation = PolygonAnnotationUI(
                        Path(validation.thermal_path),
                        class_name,
                        target_name=args.target_name,
                        reviewer_confidence=args.reviewer_confidence,
                    ).run()
                    cancelled = annotation.cancelled or not annotation.accepted
                    coordinates = [[x, y] for x, y in annotation.coordinates]
                if cancelled:
                    summaries.append(
                        GroupRunSummary(group.group_id, image_id, ProcessingRoute.CANCELLED,
                                        ProcessingStatus.CANCELLED, "polygon_annotation_cancelled")
                    )
                    continue
                temperature = temperature_for_group(
                    image_id=image_id,
                    thermal_path=Path(validation.thermal_path),
                    overrides=temperature_overrides,
                    args=args,
                )
                labels, known = labelled_polygon_arrays(coordinates, temperature.matrix.shape, class_id)
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
                    processing_route=ProcessingRoute.THERMAL_POLYGON,
                    source_method=SourceMethod.THERMAL_POLYGON_USER_ANNOTATION,
                    review_status=ManualReviewStatus.ACCEPTED,
                    qa_status=qa_enum(temperature.qa_status),
                    configuration_hash=config_hash,
                    source_file_hashes=hashes,
                    surface_cover_names=cover_names,
                    surface_cover_class_id=class_id,
                    surface_cover_category=class_name,
                    target_name=args.target_name,
                    polygon_coordinates=coordinates,
                    reviewer_confidence=args.reviewer_confidence,
                    temperature_metadata={**temperature.metadata, "capture_time": validation.capture_time},
                    validation_status=validation.validation_status.value,
                    scene_correspondence=decision.scene_correspondence.value,
                    coverage_class=decision.coverage_class.value,
                    exclusions=["outside_polygon:label_unknown:not_target_analysis_eligible"],
                    notes=decision.notes,
                )
            index.register(manifest_path, manifest)
            successful_manifests.append(manifest_path)
            summaries.append(
                GroupRunSummary(
                    group.group_id, image_id, manifest.processing_route, manifest.processing_status,
                    reason="canonical_result_created", canonical_manifest_path=manifest_path.resolve().as_posix(),
                )
            )
        except (OSError, ValueError, RuntimeError) as exc:
            summaries.append(
                GroupRunSummary(
                    group.group_id, image_id, ProcessingRoute.INCOMPLETE, ProcessingStatus.INCOMPLETE,
                    reason=f"{type(exc).__name__}:{exc}",
                )
            )

    index.save()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_summary_path = project_path(config["run_output_root"]) / f"run_{stamp}.json"
    write_run_summary(run_summary_path, summaries)
    if successful_manifests and not args.no_part_e and not args.validate_only:
        part_e = config["part_e"]
        aggregate_canonical_results(
            successful_manifests,
            output_parquet=project_path(part_e["canonical_parquet"]),
            summary_csv=project_path(part_e["summary_csv"]),
            write_full_csv=args.write_full_pixel_csv or bool(part_e.get("write_full_pixel_csv", False)),
        )
    print(f"Groups requested: {len(groups)}")
    for summary in summaries:
        print(f"{summary.group_id}: {summary.status.value} via {summary.route.value} - {summary.reason}")
    print(f"Run summary: {display_path(run_summary_path)}")
    failed = sum(row.status == ProcessingStatus.FAILED for row in summaries)
    incomplete = sum(row.status == ProcessingStatus.INCOMPLETE for row in summaries)
    return 1 if failed or incomplete else 0


if __name__ == "__main__":
    raise SystemExit(main())
