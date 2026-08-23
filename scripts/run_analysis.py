#!/usr/bin/env python3
"""Run the persistent heat-index-urop version 0.3 A-E workflow."""

from __future__ import annotations

import argparse
import json
import os
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
from scripts.workflow.capture_time import (
    CAPTURE_TIME_RESOLVER_VERSION,
    DJI_METADATA_PATH,
)
from scripts.workflow.extreme_temperature import extreme_summary, plot_pixel_extremes
from scripts.workflow.input_validation import (
    discover_dataset_groups,
    image_identifier,
    validate_group,
    write_validation_record,
)
from scripts.workflow.luhk_context import (
    LUHK_CATEGORIES,
    LUHK_LOOKUP_VERSION,
    load_native_luhk_result,
    resolve_luhk_context,
)
from scripts.workflow.models import (
    ArtifactReference,
    ContentTriageState,
    CoverageClass,
    GroupInput,
    GroupRunSummary,
    LUHKProvenance,
    ManualReviewStatus,
    ProcessingRoute,
    ProcessingStatus,
    QAStatus,
    SceneCorrespondence,
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
from scripts.workflow.pilot_adapter import adapt_pilot_image, pilot_image_ids, pilot_source_paths
from scripts.workflow.polygon_annotation import polygon_context_arrays, run_polygon_gui_subprocess
from scripts.workflow.result_index import ResultIndex, configuration_hash, sha256_file, source_hashes
from scripts.workflow.routing import finalize_part_b, route_after_part_a, route_after_part_b0, route_group
from scripts.workflow.temperature_extraction import (
    TemperatureResult,
    extract_temperature,
    load_parameter_row,
    load_report_parameter_row,
    load_temperature_override,
    resolve_irp_exe,
)
from scripts.workflow.temporal_analysis import TemporalAnalysisPlan, parse_temporal_plan
from scripts.workflow.temporal_interactive import collect_temporal_plan


PILOT_TAT3_PARAMETERS = (
    PROJECT_ROOT / "outputs" / "part_d" / "qa" / "tat3_parameter_audit" / "part_d_tat3_pilot_parameters.csv"
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


def prompt_review(label: str) -> ManualReviewStatus:
    while True:
        answer = input(f"{label} [a=accept / r=reject to polygon / c=cancel]: ").strip().casefold()
        if answer in {"a", "accept", "accepted"}:
            return ManualReviewStatus.ACCEPTED
        if answer in {"r", "reject", "rejected"}:
            return ManualReviewStatus.REJECTED
        if answer in {"c", "cancel", "cancelled", "canceled"}:
            return ManualReviewStatus.CANCELLED
        print("Please enter a, r, or c.", flush=True)


def prompt_text(label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{label}{suffix}: ").strip()
    return value or default


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


def report_ambient(parameters: dict[str, Any]) -> dict[str, Any]:
    if not parameters:
        return {}
    return {
        "ambient_temperature_c": parameters.get("ambient_temperature_c"),
        "source": "TAT3 exported ambient parameter",
        "definition": "TAT3 exported ambient parameter; not independently validated meteorological air temperature",
        "source_record": parameters.get("source_report", ""),
        "timezone": "Asia/Hong_Kong",
        "validation_status": "provisional_user_supplied_report_parameter",
    }


def tat3_report_paths(args: argparse.Namespace) -> list[Path]:
    """Return repeatable report inputs while accepting legacy string Namespaces."""

    values = getattr(args, "tat3_report", [])
    if isinstance(values, (str, Path)):
        values = [values] if str(values).strip() else []
    return [project_path(value) for value in values if str(value).strip()]


def report_parameters_for_image(args: argparse.Namespace, image_id: str) -> dict[str, Any]:
    """Select exactly one matching image entry across one or more TAT3 reports."""

    matches: list[dict[str, Any]] = []
    reports = tat3_report_paths(args)
    for report in reports:
        try:
            matches.append(load_report_parameter_row(report, image_id))
        except ValueError as exc:
            if "found 0" not in str(exc):
                raise
    if len(matches) != 1:
        raise ValueError(
            f"Expected exactly one TAT3 report entry for {image_id} across {len(reports)} report(s); "
            f"found {len(matches)}."
        )
    return matches[0]


def ambient_context(args: argparse.Namespace, payload: dict[str, Any], image_id: str) -> dict[str, Any]:
    explicit = ambient_for_image(payload, image_id)
    if explicit:
        return explicit
    if tat3_report_paths(args):
        try:
            return report_ambient(report_parameters_for_image(args, image_id))
        except ValueError:
            return {}
    return {}


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
    if tat3_report_paths(args):
        parameters = report_parameters_for_image(args, image_id)
    elif args.tat3_params_csv:
        parameters = load_parameter_row(project_path(args.tat3_params_csv), image_id)
    elif image_id in set(pilot_image_ids(PROJECT_ROOT)) and PILOT_TAT3_PARAMETERS.is_file():
        parameters = load_parameter_row(PILOT_TAT3_PARAMETERS, image_id)
    else:
        raise ValueError(
            "temperature_matrix_unavailable: provide --temperature-npy, --tat3-report, "
            "or --tat3-params-csv with DJI SDK options"
        )
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
    parser.add_argument(
        "--tat3-report",
        action="append",
        default=[],
        help="TAT3 DOCX report; repeat for multiple reports. Exactly one entry must match each extracted thermal image.",
    )
    parser.add_argument("--sdk-config", default="config/part_d_sdk.local.json")
    parser.add_argument("--sdk-root", default="")
    parser.add_argument("--irp-exe", default="")
    parser.add_argument("--keep-sdk-raw", action="store_true")
    parser.add_argument("--max-groups", type=int)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--no-part-e", action="store_true")
    parser.add_argument("--part-e-dry-run", action="store_true")
    parser.add_argument(
        "--temporal",
        choices=["no", "yes", "ask"],
        default="no",
        help="Opt in to confirmed same-location temporal analysis; ordinary users should use ask.",
    )
    parser.add_argument(
        "--temporal-plan",
        default="",
        help="Developer/programmatic temporal plan. Ordinary users are prompted and do not author this file.",
    )
    parser.add_argument("--write-full-pixel-csv", action="store_true")
    parser.add_argument("--polygon-image-id", action="append", default=[], help="Route this image to Part C* without a review JSON.")
    parser.add_argument(
        "--reprocess-image-id",
        action="append",
        default=[],
        help="Ignore a compatible cache for this image so an accepted annotation can be revised.",
    )
    parser.add_argument("--require-all-success", action="store_true", help="Return failure unless every requested image succeeds or is a cache hit.")
    parser.add_argument("--interactive", action="store_true", help="Ask for review/context decisions at workflow gates.")
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


def write_user_run_report(
    path: Path,
    *,
    summaries: list[GroupRunSummary],
    run_summary_path: Path,
    output_root: Path,
    part_e_outputs: dict[str, str],
    part_e_root: Path | None,
) -> Path:
    lines = [
        "# User workflow result",
        "",
        "## Image results",
        "",
        "| Image | Status | Route | Result |",
        "|---|---|---|---|",
    ]
    for row in summaries:
        lines.append(f"| {row.image_id} | {row.status.value} | {row.route.value} | {row.reason} |")
    source_summary_value = part_e_outputs.get("source_summary", "")
    source_summary_path = Path(source_summary_value) if source_summary_value else None
    if source_summary_path and source_summary_path.is_file():
        analysis = pd.read_csv(source_summary_path)
        lines.extend(
            [
                "",
                "## Analysis summary",
                "",
                f"- Images included in Part E: {analysis['image_id'].nunique()}",
                f"- Analysis-eligible pixels: {int(analysis['analysis_eligible_pixel_count'].sum()):,}",
                f"- Excluded pixels: {int(analysis['excluded_pixel_count'].sum()):,}",
                "- Weighting/interpretation: pixels describe each image; only explicitly confirmed same-location captures may form a temporal series.",
                "",
                "| Image | Source | Eligible pixels | Mean temperature °C | Mean ΔT °C | LUHK source | LUHK-known pixels | QA |",
                "|---|---|---:|---:|---:|---|---:|---|",
            ]
        )
        for row in analysis.itertuples(index=False):
            delta = pd.to_numeric(getattr(row, "eligible_delta_t_mean_c", None), errors="coerce")
            delta_text = "unavailable" if pd.isna(delta) else f"{float(delta):.3f}"
            luhk_count = int(getattr(row, "luhk_known_pixel_count", 0))
            luhk_source = str(getattr(row, "luhk_provenance", "unknown"))
            lines.append(
                f"| {row.image_id} | {row.source_method} / {row.measurement_type} | "
                f"{int(row.analysis_eligible_pixel_count):,} | {float(row.eligible_temperature_mean_c):.3f} | "
                f"{delta_text} | {luhk_source} | {luhk_count:,} | {row.qa_status} |"
            )
        lines.extend(
            [
                "",
                "LUHK and visible-image surface cover are separate variables. "
                "`official_luhk_lookup` is read-only official context; `user_supplied_luhk` is accepted target-scoped context; "
                "`unknown` means that no defensible lookup was available.",
            ]
        )
    lines.extend(temporal_user_summary_lines(part_e_outputs, part_e_root))
    lines.extend(
        [
            "",
            "## Output locations",
            "",
            f"- Run summary: `{run_summary_path.resolve().as_posix()}`",
            f"- Canonical image results: `{output_root.resolve().as_posix()}`",
        ]
    )
    if part_e_root:
        lines.extend(
            [
                f"- Spectrum figures: `{(part_e_root / 'figures' / 'spectrum').resolve().as_posix()}`",
                f"- Spatial figures: `{(part_e_root / 'figures' / 'spatial').resolve().as_posix()}`",
                f"- Temporal results: `{(part_e_root / 'temporal').resolve().as_posix()}`",
                f"- Statistical tables: `{(part_e_root / 'tables').resolve().as_posix()}`",
                f"- Part E QA: `{part_e_outputs.get('qa', (part_e_root / 'qa').resolve().as_posix())}`",
            ]
        )
    else:
        lines.append("- Part E: not run (no accepted/cached canonical inputs, validation-only, or explicitly disabled).")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def temporal_user_summary_lines(part_e_outputs: dict[str, str], part_e_root: Path | None) -> list[str]:
    """Return the primary temporal result in readable form, without raw-JSON inspection."""

    lines = ["", "## Temporal result", ""]
    manifest_value = part_e_outputs.get("temporal_run_manifest", "")
    manifest_path = Path(manifest_value) if manifest_value else None
    if manifest_path is None and part_e_root:
        candidate = part_e_root / "temporal" / "temporal_run_manifest.json"
        manifest_path = candidate if candidate.is_file() else None
    if manifest_path is None or not manifest_path.is_file():
        lines.append("Temporal stage was not run.")
        return lines
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not bool(payload.get("temporal_requested", False)):
        lines.append("Temporal analysis was not requested.")
        return lines
    groups = payload.get("groups", [])
    if not groups:
        lines.append("Temporal analysis was requested, but no same-location temporal group was confirmed.")
        return lines
    temporal_root = manifest_path.parent
    for group in groups:
        group_id = str(group.get("temporal_group_id", "unnamed-group"))
        eligible = int(group.get("eligible_capture_count", 0))
        submitted = int(group.get("submitted_capture_count", 0))
        lines.extend(
            [
                f"### {group_id}",
                "",
                f"- Location/target: `{group.get('location_id', '')}` / `{group.get('target_id', '')}`",
                f"- Captures: {eligible} eligible of {submitted} submitted",
                f"- Result status: `{group.get('trend_status', 'not_available')}`",
                f"- Sampling coverage: `{group.get('sampling_coverage_status', 'not_available')}`",
            ]
        )
        peak_path = temporal_root / group_id / "tables" / "peak_to_trough_statistics.csv"
        if bool(group.get("temporal_series_available", False)) and peak_path.is_file():
            peaks = pd.read_csv(peak_path)
            available = peaks.loc[peaks["available"].astype(bool)] if "available" in peaks else peaks.iloc[0:0]
            representative = (
                available.loc[available["primary_representative"].astype(bool)]
                if "primary_representative" in available
                else available.iloc[0:0]
            )
            for row in representative.itertuples(index=False):
                lines.extend(
                    [
                        f"- Observed representative maximum: {float(row.observed_max_c):.3f} °C at "
                        f"{row.observed_max_time_local} (`{row.observed_max_image_id}`)",
                        f"- Observed representative minimum: {float(row.observed_min_c):.3f} °C at "
                        f"{row.observed_min_time_local} (`{row.observed_min_image_id}`)",
                        f"- Observed representative peak-to-trough difference: "
                        f"{float(row.observed_peak_to_trough_range_c):.3f} °C",
                    ]
                )
            absolute = (
                available.loc[available["statistic"].astype(str).eq("absolute_pixel")]
                if "statistic" in available
                else available.iloc[0:0]
            )
            for row in absolute.itertuples(index=False):
                lines.append(
                    f"- Absolute observed pixel max–min difference: "
                    f"{float(row.observed_peak_to_trough_range_c):.3f} °C "
                    f"({float(row.observed_min_c):.3f}–{float(row.observed_max_c):.3f} °C)"
                )
        elif eligible == 1:
            lines.append(
                "- Only one eligible capture is available; no temporal trend or peak-to-trough difference can be estimated."
            )
        else:
            reasons = group.get("exclusion_reasons", {})
            readable = "; ".join(f"{key}: {value}" for key, value in reasons.items())
            lines.append("- No compatible temporal series is available." + (f" Reasons: {readable}" if readable else ""))
        lines.append(
            f"- Detailed readable report: `{(temporal_root / group_id / 'temporal_summary.md').resolve().as_posix()}`"
        )
    lines.append(
        "Observed extrema describe only the sampled observation window; they are not claimed as the true daily maximum or minimum."
    )
    return lines


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
    reprocess_ids = set(args.reprocess_image_id)

    print(f"Workflow started: {len(groups)} image group(s)", flush=True)
    print(f"Run workspace: {display_path(run_directory)}", flush=True)

    for group_number, group in enumerate(groups, start=1):
        image_id = image_identifier(Path(group.thermal_path))
        print(f"[{group_number}/{len(groups)}] {image_id}: validating inputs (Part A)", flush=True)
        group_dir = run_directory / "groups" / image_id
        polygon_input = polygon_payload_for_image(polygons, image_id)
        selected_part_b = explicit_part_b.get(group.group_id) or explicit_part_b.get(image_id)
        selected_b0 = part_b0_reviews.get(group.group_id) or part_b0_reviews.get(image_id)
        if image_id in set(args.polygon_image_id):
            selected_b0 = ManualReviewStatus.REJECTED
        explicit_polygon_route = (
            image_id in set(args.polygon_image_id)
            or selected_b0 == ManualReviewStatus.REJECTED
        )
        normal_luhk_relevant = not explicit_polygon_route
        polygon_context_relevant = image_id in set(args.polygon_image_id) or bool(polygon_input) or image_id not in pilot_ids
        group_configuration = {
            "schema_version": config.get("schema_version", "0.2.0"),
            "processing_version": config.get("processing_version", "heat-index-urop-0.3.2"),
            "part_b0": config.get("part_b0", {}),
            "part_b0_review": selected_b0.value if selected_b0 else "",
            "part_b_review": selected_part_b.to_dict() if selected_part_b else {},
            "part_c_review": part_c_reviews.get(image_id).resolve().as_posix() if image_id in part_c_reviews else "",
            "polygon": polygon_input if polygon_context_relevant else {},
            "surface_cover": args.surface_cover if polygon_context_relevant else "",
            "target_name": args.target_name if polygon_context_relevant else "",
            "target_id": args.target_id if polygon_context_relevant else "",
            "luhk": args.luhk if polygon_context_relevant else "",
            "luhk_provenance": args.luhk_provenance if polygon_context_relevant else "unknown",
            "ambient": ambient_context(args, ambient_payload, image_id),
            "normal_luhk_lookup_version": LUHK_LOOKUP_VERSION if normal_luhk_relevant else "not_applicable",
        }
        group_config_hash = configuration_hash(group_configuration)
        source_paths = [Path(group.visible_path), Path(group.thermal_path), cover_mapping_path]
        capture_time_dependency_paths = [
            DJI_METADATA_PATH,
            PROJECT_ROOT / "scripts" / "workflow" / "capture_time.py",
        ]
        source_paths.extend(path for path in capture_time_dependency_paths if path.is_file())
        luhk_dependency_paths = [
            PROJECT_ROOT / "data" / "processed" / "grids" / "pilot_luhk_aligned_10m_grid_cells.xlsx",
            PROJECT_ROOT / "data" / "processed" / "footprints" / "image_footprints.xlsx",
            PROJECT_ROOT / "data" / "luhk" / "LUMHK_RasterGrid_2024.tif",
            PROJECT_ROOT / "scripts" / "workflow" / "luhk_context.py",
        ]
        if normal_luhk_relevant:
            source_paths.extend(path for path in luhk_dependency_paths if path.is_file())
        for mapping in (label_overrides, label_manifests, part_c_reviews):
            if image_id in mapping:
                source_paths.append(mapping[image_id])
        if image_id in temperature_overrides:
            source_paths.append(temperature_overrides[image_id])
            if args.ambient_json:
                source_paths.append(project_path(args.ambient_json))
        elif image_id in pilot_ids:
            source_paths.extend(pilot_source_paths(PROJECT_ROOT, image_id))
        else:
            if tat3_report_paths(args):
                source_paths.extend(tat3_report_paths(args))
            elif args.tat3_params_csv:
                source_paths.append(project_path(args.tat3_params_csv))
            if args.sdk_config and project_path(args.sdk_config).is_file():
                source_paths.append(project_path(args.sdk_config))
        hashes = source_hashes(source_paths)
        dependencies = {
            "group_configuration": group_config_hash,
            "surface_cover_mapping": sha256_file(cover_mapping_path),
            "capture_time_resolver_version": CAPTURE_TIME_RESOLVER_VERSION,
            **{
                f"capture_time_input:{path.name}": sha256_file(path)
                for path in capture_time_dependency_paths
                if path.is_file()
            },
            "normal_luhk_lookup_version": LUHK_LOOKUP_VERSION if normal_luhk_relevant else "not_applicable",
            **{
                f"normal_luhk_input:{path.name}": sha256_file(path)
                for path in luhk_dependency_paths
                if normal_luhk_relevant and path.is_file()
            },
        }
        cache = index.check(
            image_id,
            source_file_hashes=hashes,
            configuration_hash_value=group_config_hash,
            dependency_fingerprints=dependencies,
        )
        if cache.compatible and image_id not in reprocess_ids:
            print(f"[{group_number}/{len(groups)}] {image_id}: compatible canonical result found (cache hit)", flush=True)
            successful_manifests.append(Path(cache.manifest_path))
            summaries.append(GroupRunSummary(
                group.group_id, image_id, ProcessingRoute.CACHE, ProcessingStatus.CACHE_HIT,
                reason="compatible_canonical_result", canonical_manifest_path=cache.manifest_path, cache_hit=True,
            ))
            continue
        if cache.compatible and image_id in reprocess_ids:
            print(f"[{group_number}/{len(groups)}] {image_id}: reprocessing requested; compatible cache will be replaced", flush=True)

        override_shape = None
        if image_id in temperature_overrides and temperature_overrides[image_id].is_file():
            override_shape = tuple(np.load(temperature_overrides[image_id], mmap_mode="r", allow_pickle=False).shape)
        validation = validate_group(
            group,
            temperature_shape=override_shape,
            default_timezone=str(config.get("part_e", {}).get("temporal_timezone", "Asia/Hong_Kong")),
        )
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
            print(f"[{group_number}/{len(groups)}] {image_id}: checking visible/thermal correspondence (Part B0)", flush=True)
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
            if args.interactive and selected_b0 is None and part_b0.triage_state == ContentTriageState.NEEDS_MANUAL_REVIEW:
                print(
                    f"Part B0 needs your decision: score={part_b0.overall_score:.3f}, "
                    f"confidence={part_b0.confidence}, reasons={'; '.join(part_b0.reasons)}",
                    flush=True,
                )
                selected_b0 = prompt_review("Does the visible image show the same scene as the thermal image?")
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
                print(f"[{group_number}/{len(groups)}] {image_id}: refining visible/thermal alignment (Part B)", flush=True)
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
                if args.interactive and route.status == ProcessingStatus.AWAITING_PART_B_REVIEW:
                    print(f"Part B candidate review image: {part_b.review_evidence_path}", flush=True)
                    if os.name == "nt" and Path(part_b.review_evidence_path).is_file():
                        os.startfile(part_b.review_evidence_path)  # type: ignore[attr-defined]
                    decision = prompt_review(
                        "After viewing the contact sheet, is correspondence accepted with full thermal coverage?"
                    )
                    part_b.manual_review_status = decision
                    if decision == ManualReviewStatus.ACCEPTED:
                        part_b.scene_correspondence = SceneCorrespondence.ACCEPTED
                        part_b.coverage_class = CoverageClass.THERMAL_FULLY_SUPPORTED_BY_VISIBLE
                        print("Part B accepted; continuing to normal Part C.", flush=True)
                    elif decision == ManualReviewStatus.REJECTED:
                        part_b.scene_correspondence = SceneCorrespondence.REJECTED
                        part_b.coverage_class = CoverageClass.NO_USABLE_OVERLAP
                        print("Part B rejected; continuing to Part C* polygon extraction.", flush=True)
                    part_b = finalize_part_b(part_b)
                    (group_dir / "part_b" / "part_b.json").write_text(
                        json.dumps(part_b.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
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
                print(
                    f"[{group_number}/{len(groups)}] {image_id}: resolving temperature through the common Part D entrance; "
                    "reusing accepted pilot Part C labels",
                    flush=True,
                )
                temperature = temperature_for_group(
                    image_id=image_id,
                    thermal_path=Path(validation.thermal_path),
                    native_shape=native_shape,
                    overrides=temperature_overrides,
                    ambient_payload=ambient_payload,
                    args=args,
                )
                legacy_matrix_path = (
                    PROJECT_ROOT
                    / "data"
                    / "processed"
                    / "part_d"
                    / "temperature_matrices"
                    / f"{image_id}_temperature_celsius.npy"
                )
                if not legacy_matrix_path.is_file():
                    legacy_matrix_path.parent.mkdir(parents=True, exist_ok=True)
                    temporary_matrix = legacy_matrix_path.with_suffix(".npy.tmp")
                    with temporary_matrix.open("wb") as handle:
                        np.save(handle, temperature.matrix.astype(np.float32, copy=False), allow_pickle=False)
                        handle.flush()
                        os.fsync(handle.fileno())
                    temporary_matrix.replace(legacy_matrix_path)
                    print(
                        f"[{group_number}/{len(groups)}] {image_id}: persisted reusable Part D matrix: "
                        f"{display_path(legacy_matrix_path)}",
                        flush=True,
                    )
                    hashes = source_hashes(source_paths)
                manifest, manifest_path = adapt_pilot_image(
                    PROJECT_ROOT,
                    image_id,
                    output_root=output_root,
                    configuration_hash_value=group_config_hash,
                    source_file_hashes_value=hashes,
                    dependency_fingerprints_value=dependencies,
                    part_a=validation.to_dict(),
                    temperature_result=temperature,
                )
                manifest.dependency_fingerprints = dependencies
                manifest.part_a = validation.to_dict()
                manifest.part_b0 = part_b0.to_dict() if part_b0 else {}
                manifest.part_b = part_b.to_dict() if part_b else {}
                temporary = manifest_path.with_suffix(".json.tmp")
                temporary.write_text(json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
                temporary.replace(manifest_path)
            elif route.route == ProcessingRoute.NORMAL_VT:
                print(f"[{group_number}/{len(groups)}] {image_id}: extracting temperature and opening Part C review", flush=True)
                normal_luhk = load_native_luhk_result(
                    PROJECT_ROOT,
                    image_id=image_id,
                    pair_id=validation.pair_id,
                    shape=native_shape,
                )
                if normal_luhk.available:
                    print(
                        f"[{group_number}/{len(groups)}] {image_id}: official LUHK context mapped to "
                        f"{normal_luhk.known_pixel_count:,} native pixels (approximate footprint)",
                        flush=True,
                    )
                else:
                    print(
                        f"[{group_number}/{len(groups)}] {image_id}: LUHK unavailable: "
                        f"{normal_luhk.unavailable_reason}",
                        flush=True,
                    )
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
                    part_c_outcome = run_reviewed_part_c(
                        image_id=image_id,
                        pair_id=validation.pair_id,
                        visible_path=Path(validation.visible_path),
                        thermal_path=Path(validation.thermal_path),
                        accepted_crop=part_b.candidate_crop if part_b else [],
                        output_directory=group_dir / "part_c",
                        class_mapping=cover_names,
                        luhk_result=normal_luhk,
                        review_artifact_path=part_c_reviews.get(image_id),
                        launch_gui=args.launch_part_c_gui or args.interactive,
                    )
                    if part_c_outcome.status == "cancelled":
                        summaries.append(GroupRunSummary(
                            group.group_id, image_id, ProcessingRoute.CANCELLED,
                            ProcessingStatus.CANCELLED, "part_c_superpixel_review_cancelled",
                            part_a_record_path=part_a_path.resolve().as_posix(),
                            part_b0_record_path=(group_dir / "part_b0" / "part_b0.json").resolve().as_posix(),
                            part_b_record_path=(group_dir / "part_b" / "part_b.json").resolve().as_posix(),
                        ))
                        continue
                    part_c_result = part_c_outcome.result
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
                    luhk_labels=normal_luhk.labels,
                    luhk_known_mask=normal_luhk.known_mask,
                    luhk_class_names=normal_luhk.category_names,
                    luhk_cell_ids=normal_luhk.cell_ids,
                    luhk_raw_codes=normal_luhk.raw_codes,
                    luhk_provenance=normal_luhk.provenance.value,
                    luhk_metadata={
                        **normal_luhk.metadata,
                        "status": normal_luhk.status,
                        "unavailable_reason": normal_luhk.unavailable_reason,
                        "spatial_uncertainty": normal_luhk.spatial_uncertainty,
                        "source_paths": normal_luhk.source_paths,
                        "category_names_by_code": LUHK_CATEGORIES,
                    },
                    temperature_metadata={
                        **temperature.metadata,
                        "capture_time": validation.capture_time,
                        "capture_datetime": validation.capture_datetime,
                        "capture_time_local": validation.capture_time_local,
                        "capture_time_utc": validation.capture_time_utc,
                        "capture_timezone": validation.capture_timezone,
                        "capture_time_source": validation.capture_time_source,
                        "timezone_assumption": validation.timezone_assumption,
                        "capture_time_valid": validation.capture_time_valid,
                    },
                    ambient_metadata=ambient_context(args, ambient_payload, image_id),
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
                print(f"[{group_number}/{len(groups)}] {image_id}: extracting temperature for Part C* polygon", flush=True)
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
                if args.interactive and not surface_value:
                    surface_value = prompt_text("Surface-cover category", "grass_low_vegetation")
                class_id, class_name = resolve_cover(surface_value, cover_names, cover_ids)
                luhk_value = str(polygon_input.get("luhk", args.luhk))
                provenance_value = str(polygon_input.get("luhk_provenance", args.luhk_provenance))
                if args.interactive and not luhk_value:
                    luhk_value = prompt_text("LUHK category", "GIC / open space")
                    provenance_value = "user_supplied_luhk"
                luhk = resolve_luhk_context(
                    luhk_value,
                    provenance_value,
                )
                if args.interactive and not target_name:
                    target_name = prompt_text("Target name", image_id)
                if not target_name:
                    raise ValueError("Part C* requires a target name.")
                coordinates = polygon_input.get("coordinates", [])
                confidence = str(polygon_input.get("reviewer_confidence", args.reviewer_confidence))
                notes = str(polygon_input.get("notes", args.notes))
                if not coordinates:
                    print(f"[{group_number}/{len(groups)}] {image_id}: opening football-field polygon GUI", flush=True)
                    annotation = run_polygon_gui_subprocess(
                        request_path=group_dir / "part_c_star" / "polygon_gui_request.json",
                        result_path=group_dir / "part_c_star" / "polygon_gui_result.json",
                        thermal_image_path=Path(validation.thermal_path),
                        visible_image_path=(
                            Path(validation.visible_path)
                            if validation.visible_valid and Path(validation.visible_path).is_file()
                            else None
                        ),
                        surface_cover_category=class_name,
                        target_name=target_name,
                        luhk_category=luhk.category,
                        luhk_code=luhk.code,
                        luhk_provenance=luhk.provenance.value,
                        reviewer_confidence=confidence,
                    )
                    if annotation.cancelled:
                        summaries.append(GroupRunSummary(
                            group.group_id, image_id, ProcessingRoute.CANCELLED, ProcessingStatus.CANCELLED,
                            "polygon_annotation_cancelled", part_a_record_path=part_a_path.resolve().as_posix(),
                        ))
                        continue
                    if not annotation.accepted:
                        summaries.append(GroupRunSummary(
                            group.group_id, image_id, ProcessingRoute.AWAITING_REVIEW,
                            ProcessingStatus.AWAITING_PART_C_REVIEW,
                            "polygon_annotation_closed_without_acceptance",
                            part_a_record_path=part_a_path.resolve().as_posix(),
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
                    temperature_metadata={
                        **temperature.metadata,
                        "capture_time": validation.capture_time,
                        "capture_datetime": validation.capture_datetime,
                        "capture_time_local": validation.capture_time_local,
                        "capture_time_utc": validation.capture_time_utc,
                        "capture_timezone": validation.capture_timezone,
                        "capture_time_source": validation.capture_time_source,
                        "timezone_assumption": validation.timezone_assumption,
                        "capture_time_valid": validation.capture_time_valid,
                    },
                    ambient_metadata=ambient_context(args, ambient_payload, image_id),
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
    temporal_plan: TemporalAnalysisPlan = TemporalAnalysisPlan(temporal_requested=False)
    if successful_manifests:
        if args.temporal_plan:
            temporal_plan = parse_temporal_plan(project_path(args.temporal_plan))
            if args.temporal == "no" and temporal_plan.temporal_requested:
                print("Temporal analysis was requested by the supplied programmatic plan.", flush=True)
        elif args.temporal == "no":
            print("Temporal analysis was not requested.", flush=True)
        elif args.temporal in {"ask", "yes"}:
            if not args.interactive:
                if args.temporal == "yes":
                    raise ValueError("Temporal analysis requires --interactive confirmation or --temporal-plan.")
                print("Temporal analysis was not requested because this run is non-interactive.", flush=True)
            else:
                temporal_plan = collect_temporal_plan(
                    successful_manifests,
                    requested=True if args.temporal == "yes" else None,
                )
    part_e_outputs: dict[str, str] = {}
    part_e_root: Path | None = None
    if successful_manifests and not args.no_part_e and not args.validate_only:
        part_e = config["part_e"]
        formal_enabled = bool(part_e.get("formal_enabled", False))
        if formal_enabled:
            # A workflow run must never inherit figures or tables from an
            # earlier selection.  Keep the configured directory as a stable
            # collection root, but make every result set run-scoped.
            formal_collection_root = project_path(
                part_e.get("formal_output_root", "outputs/part_e/schema_0_2")
            )
            part_e_root = formal_collection_root / run_directory.name
            aggregate_root = part_e_root / "input_aggregate"
            aggregate_parquet = aggregate_root / "part_e_multi_source_pixels.parquet"
            aggregate_summary = aggregate_root / "source_summary.csv"
            aggregate_dashboard = aggregate_root / "source_dashboard"
        else:
            # Preserve the schema-0.2 public/configured aggregate paths for
            # callers that use Part E ingestion without the formal report
            # pipeline.  Only formal result collections need per-run scoping;
            # silently moving these legacy outputs breaks existing API users.
            aggregate_root = run_directory / "part_e_input"
            aggregate_parquet = project_path(
                part_e.get("canonical_parquet", aggregate_root / "part_e_multi_source_pixels.parquet")
            )
            aggregate_summary = project_path(
                part_e.get("summary_csv", aggregate_root / "source_summary.csv")
            )
            aggregate_dashboard = project_path(
                part_e.get("dashboard_directory", aggregate_root / "source_dashboard")
            )
        print(f"Part E: aggregating {len(successful_manifests)} accepted/cached image(s)", flush=True)
        aggregate_canonical_results(
            successful_manifests,
            output_parquet=aggregate_parquet,
            summary_csv=aggregate_summary,
            write_full_csv=args.write_full_pixel_csv or bool(part_e.get("write_full_pixel_csv", False)),
            dashboard_directory=aggregate_dashboard,
        )
        if formal_enabled:
            print("Part E: running spectrum, spatial, statistical, and temporal stages", flush=True)
            part_e_outputs = run_formal_part_e(
                successful_manifests,
                output_root=part_e_root,
                run_summary_path=run_summary_path,
                resume=True,
                dry_run=args.part_e_dry_run,
                temporal_timezone=str(part_e.get("temporal_timezone", "Asia/Hong_Kong")),
                temporal_plan=temporal_plan,
            )
            if (
                part_e_outputs.get("stage_stdout", "").strip()
                and part_e_outputs.get("stage_output_streamed") != "true"
            ):
                print(part_e_outputs["stage_stdout"].strip(), flush=True)
            print("Part E: complete", flush=True)
            if temporal_plan.temporal_requested:
                print(
                    f"Temporal stage completed for {len(temporal_plan.groups)} explicitly confirmed group(s).",
                    flush=True,
                )
            else:
                print("PART E single-capture and spatial analysis completed; temporal analysis was not requested.", flush=True)
            for line in temporal_user_summary_lines(part_e_outputs, part_e_root):
                readable = line.lstrip("- ").strip()
                if readable and (
                    readable.startswith("Temporal analysis")
                    or readable.startswith("Only one eligible")
                    or readable.startswith("Observed representative")
                    or readable.startswith("Absolute observed")
                    or readable.startswith("No compatible temporal")
                    or readable.startswith("Detailed readable report")
                ):
                    print(readable, flush=True)
    else:
        print("Part E: not run because no accepted/cached canonical image was available or it was disabled", flush=True)
    user_report_path = write_user_run_report(
        run_directory / "USER_RESULTS.md",
        summaries=summaries,
        run_summary_path=run_summary_path,
        output_root=output_root,
        part_e_outputs=part_e_outputs,
        part_e_root=part_e_root,
    )
    print(f"Groups requested: {len(groups)}")
    for summary in summaries:
        print(f"{summary.group_id}: {summary.status.value} via {summary.route.value} - {summary.reason}")
    print(f"Run summary: {display_path(run_summary_path)}")
    print(f"User result guide: {display_path(user_report_path)}")
    print(f"Canonical results: {display_path(output_root)}")
    if part_e_root:
        print(f"Spectrum figures: {display_path(part_e_root / 'figures' / 'spectrum')}")
        print(f"Spatial figures: {display_path(part_e_root / 'figures' / 'spatial')}")
        print(f"Temporal results: {display_path(part_e_root / 'temporal')}")
        print(f"Statistical tables: {display_path(part_e_root / 'tables')}")
        print(f"Part E QA: {part_e_outputs.get('qa', display_path(part_e_root / 'qa'))}")
    failed = sum(row.status in {ProcessingStatus.FAILED, ProcessingStatus.INCOMPLETE} for row in summaries)
    if args.require_all_success:
        failed += sum(row.status not in {ProcessingStatus.SUCCESS, ProcessingStatus.CACHE_HIT} for row in summaries)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
