"""Schema-0.2 ingestion and source-stratified handoff to formal Part E."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .canonical_result import load_manifest
from .capture_time import select_capture_time_bundle
from .models import CanonicalManifest, GroupRunSummary, ProcessingStatus, QAStatus


os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parents[2] / ".matplotlib-cache"))

PROVENANCE_COLUMNS = [
    "measurement_type",
    "temperature_source",
    "temperature_definition",
    "source_method",
    "surface_cover_provenance",
    "luhk_provenance",
    "label_known",
    "analysis_eligible",
    "exclusion_reason",
    "target_id",
    "target_name",
    "location_id",
    "location_name",
    "qa_status",
    "annotation_review_status",
]


def _polygon_area_px2(coordinates: list[list[float]]) -> float:
    """Return shoelace area for an accepted native-grid polygon."""

    if len(coordinates) < 3:
        return float("nan")
    points = np.asarray(coordinates, dtype=float)
    if points.ndim != 2 or points.shape[1] != 2 or not np.isfinite(points).all():
        return float("nan")
    x_values = points[:, 0]
    y_values = points[:, 1]
    return float(abs(np.dot(x_values, np.roll(y_values, 1)) - np.dot(y_values, np.roll(x_values, 1))) / 2.0)


def _compatible_frame(frame: pd.DataFrame, manifest: CanonicalManifest) -> pd.DataFrame:
    work = frame.copy()
    temperature_metadata = manifest.temperature_metadata or {}
    part_a = manifest.part_a or {}
    manifest_capture = {
        "capture_datetime": manifest.capture_datetime,
        "capture_time_local": manifest.capture_time_local,
        "capture_time_utc": manifest.capture_time_utc,
        "capture_timezone": manifest.capture_timezone,
        "capture_time_source": manifest.capture_time_source,
        "timezone_assumption": manifest.timezone_assumption,
        "capture_time_valid": manifest.capture_time_valid,
    }
    capture = select_capture_time_bundle(
        (manifest_capture, ""),
        (temperature_metadata, ""),
        (part_a, "part_a_capture_time_fallback"),
        missing_timezone=str(manifest.capture_timezone or part_a.get("capture_timezone") or ""),
    )
    defaults: dict[str, object] = {
        "measurement_type": manifest.measurement_type.value,
        "temperature_source": manifest.temperature_source,
        "temperature_definition": str(
            manifest.temperature_metadata.get("temperature_definition")
            or manifest.temperature_metadata.get("definition")
            or manifest.temperature_metadata.get("measurement_definition", "")
        ),
        "source_method": manifest.source_method.value,
        "surface_cover_provenance": manifest.surface_cover_provenance,
        "luhk_provenance": manifest.luhk_provenance,
        "target_id": manifest.target_id or "",
        "target_name": manifest.target_name or "",
        "location_id": manifest.location_id or "",
        "location_name": manifest.location_name or "",
        "qa_status": manifest.qa_status.value,
        "annotation_review_status": manifest.review_status.value,
    }
    for column, value in defaults.items():
        if column not in work.columns:
            work[column] = value
    if "target_mask" not in work.columns:
        # Legacy normal results used analysis_eligible as their effective
        # full-grid target definition. Keep that fallback explicit.
        work["target_mask"] = work.get("analysis_eligible", pd.Series(False, index=work.index)).astype(bool)
    for column in PROVENANCE_COLUMNS:
        if column not in work.columns:
            raise ValueError(f"Canonical pixels for {manifest.image_id} are missing {column}.")
    ambient = manifest.temperature_metadata.get("ambient_temperature_c", manifest.ambient_metadata.get("ambient_temperature_c"))
    try:
        ambient_value = float(ambient)
    except (TypeError, ValueError):
        ambient_value = np.nan
    work["ambient_temperature_c"] = np.float32(ambient_value)
    work["delta_t_c"] = (pd.to_numeric(work["temperature_c"], errors="coerce") - ambient_value).astype("float32")
    if not np.isfinite(ambient_value):
        work["delta_t_c"] = np.float32(np.nan)
    work["delta_temperature_available"] = bool(np.isfinite(ambient_value))
    work["pixel_accepted"] = work["temperature_is_finite"].astype(bool)
    work["surface_cover_valid"] = work["analysis_eligible"].astype(bool)
    work["surface_cover_review_status"] = work["annotation_review_status"].astype(str)
    if "luhk_label" in work:
        luhk_values = work["luhk_label"].astype(str)
        if "luhk_class_code" not in work:
            work["luhk_class_code"] = luhk_values
        if "luhk_class_name" not in work:
            names = dict((manifest.luhk_metadata or {}).get("category_names_by_code", {}))
            work["luhk_class_name"] = luhk_values.map(names).fillna(luhk_values)
        luhk_known = work.get("luhk_known")
        if "luhk_label_valid" not in work:
            work["luhk_label_valid"] = (
                luhk_known.astype(bool)
                if isinstance(luhk_known, pd.Series)
                else pd.Series(False, index=work.index, dtype=bool)
            )
    target_artifact = manifest.artifacts.get("target_mask")
    total_pixels = int(manifest.image_height) * int(manifest.image_width)
    target_count = int(manifest.target_pixel_count)
    if target_count <= 0:
        target_count = int(work["target_mask"].astype(bool).sum())
    polygon_area = _polygon_area_px2(manifest.polygon_coordinates)
    if target_artifact is None or not target_artifact.sha256:
        roi_evidence = "legacy_effective_target_mask_without_artifact_fingerprint"
    elif manifest.selection_scope == "user_accepted_thermal_polygon":
        roi_evidence = "accepted_manual_polygon_with_target_mask_fingerprint"
    else:
        roi_evidence = "full_native_grid_with_target_mask_fingerprint"
    defaults = {
        "flight_id": manifest.group_id,
        "ambient_source": str(manifest.ambient_metadata.get("source", "")),
        "ambient_definition": str(
            manifest.ambient_metadata.get("temperature_definition")
            or manifest.ambient_metadata.get("definition")
            or manifest.ambient_metadata.get("measurement_definition", "")
        ),
        "canonical_schema_version": manifest.schema_version,
        "processing_version": manifest.processing_version,
        "selection_scope": manifest.selection_scope,
        "roi_id": manifest.target_id or manifest.selection_scope,
        "roi_definition": (
            f"accepted_target_polygon:{manifest.target_id or manifest.target_name or manifest.image_id}"
            if manifest.selection_scope == "user_accepted_thermal_polygon"
            else "full_native_thermal_grid_with_reviewed_surface_cover"
        ),
        "roi_method": (
            "accepted_manual_thermal_polygon"
            if manifest.selection_scope == "user_accepted_thermal_polygon"
            else "accepted_visible_image_surface_cover_review"
        ),
        "temperature_unit": str(temperature_metadata.get("temperature_unit", temperature_metadata.get("unit", "degC"))),
        "gps_latitude": part_a.get("gps_latitude"),
        "gps_longitude": part_a.get("gps_longitude"),
        "spatial_processing_method": str(manifest.part_b.get("final_alignment_status", manifest.coverage_class)),
        "spatial_registration_id": str(manifest.part_b.get("spatial_registration_id", "")),
        "ambient_unit": str(manifest.ambient_metadata.get("unit", "degC")),
        "ambient_data_qa_status": str(
            manifest.ambient_metadata.get("validation_status")
            or manifest.ambient_metadata.get("qa_status")
            or "unavailable"
        ),
        "ambient_provenance": str(
            manifest.ambient_metadata.get("provenance")
            or ("canonical_manifest_ambient_metadata" if manifest.ambient_metadata else "unavailable")
        ),
        "ambient_source_record": str(
            manifest.ambient_metadata.get("source_record")
            or manifest.ambient_metadata.get("source_path")
            or manifest.temperature_metadata.get("source_report", "")
        ),
        "ambient_timezone": str(manifest.ambient_metadata.get("timezone", "")),
        "ambient_notes": str(manifest.ambient_metadata.get("notes", "")),
        "image_height": manifest.image_height,
        "image_width": manifest.image_width,
        "luhk_cell_id": "",
        "luhk_class_code": str(manifest.luhk_code or ""),
        "luhk_class_name": manifest.luhk_category or "",
        "luhk_label_valid": False,
    }
    for column, value in defaults.items():
        if column not in work.columns:
            work[column] = value
    for column, value in {
        "roi_mask_sha256": str(target_artifact.sha256 if target_artifact else ""),
        "roi_polygon_area_px2": polygon_area,
        "roi_target_pixel_count": target_count,
        "roi_target_coverage_fraction": float(target_count / total_pixels) if total_pixels else float("nan"),
        "roi_comparability_evidence": roi_evidence,
    }.items():
        work[column] = value
    # Capture time is a provenance bundle, not a set of independently fillable
    # columns.  Replace legacy blank or stale pixel values atomically from the
    # first valid canonical source selected above.
    for column in (
        "capture_datetime",
        "capture_time_local",
        "capture_time_utc",
        "capture_timezone",
        "capture_time_source",
        "timezone_assumption",
        "capture_time_valid",
    ):
        work[column] = capture[column]
    if "shadow_flag" not in work.columns:
        work["shadow_flag"] = pd.array([pd.NA] * len(work), dtype="Int8")
    if "shadow_valid" not in work.columns:
        work["shadow_valid"] = False
    return work


def read_canonical_pixels(manifest_path: Path) -> tuple[CanonicalManifest, pd.DataFrame]:
    manifest = load_manifest(manifest_path)
    if manifest.processing_status != ProcessingStatus.SUCCESS or manifest.qa_status == QAStatus.FAIL:
        raise ValueError(f"Only successful non-failed-QA results may enter Part E: {manifest.image_id}")
    artifact = manifest.artifacts.get("pixels")
    if artifact is None:
        raise ValueError(f"Canonical result has no pixels.parquet artifact: {manifest.image_id}")
    pixels_path = Path(artifact.path)
    if not pixels_path.is_absolute():
        pixels_path = manifest_path.parent / pixels_path
    return manifest, _compatible_frame(pd.read_parquet(pixels_path), manifest)


def manifest_paths_from_run_summary(path: Path) -> list[Path]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    paths = []
    for row in payload.get("groups", []):
        if row.get("status") not in {"success", "cache_hit"}:
            continue
        value = str(row.get("canonical_manifest_path", ""))
        if value:
            paths.append(Path(value))
    return paths


def aggregate_canonical_results(
    manifest_paths: Iterable[Path],
    *,
    output_parquet: Path,
    summary_csv: Path,
    write_full_csv: bool = False,
    dashboard_directory: Path | None = None,
    write_explicit_pooled_sensitivity: bool = False,
) -> pd.DataFrame:
    output_parquet.parent.mkdir(parents=True, exist_ok=True)
    summary_csv.parent.mkdir(parents=True, exist_ok=True)
    writer: pq.ParquetWriter | None = None
    summaries: list[dict[str, object]] = []
    image_level: list[dict[str, object]] = []
    full_csv_frames: list[pd.DataFrame] = []
    try:
        for manifest_path in manifest_paths:
            manifest, frame = read_canonical_pixels(manifest_path)
            for column in frame.select_dtypes(include="category").columns:
                frame[column] = frame[column].astype(str)
            table = pa.Table.from_pandas(frame, preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(output_parquet, table.schema, compression="zstd", use_dictionary=True)
            elif table.schema != writer.schema:
                try:
                    table = table.cast(writer.schema)
                except (pa.ArrowInvalid, pa.ArrowNotImplementedError) as exc:
                    raise ValueError(f"Canonical pixel schema differs for {manifest.image_id}: {exc}") from exc
            writer.write_table(table, row_group_size=65536)
            eligible = frame["analysis_eligible"].astype(bool)
            finite = frame["temperature_is_finite"].astype(bool)
            finite_temperature = pd.to_numeric(frame.loc[finite, "temperature_c"], errors="coerce")
            eligible_temperature = pd.to_numeric(frame.loc[finite & eligible, "temperature_c"], errors="coerce")
            eligible_delta_t = pd.to_numeric(frame.loc[finite & eligible, "delta_t_c"], errors="coerce")
            summary_row = {
                "image_id": manifest.image_id,
                "group_id": manifest.group_id,
                "processing_route": manifest.processing_route.value,
                "measurement_type": manifest.measurement_type.value,
                "temperature_source": manifest.temperature_source,
                "temperature_definition": str(frame["temperature_definition"].iloc[0]),
                "source_method": manifest.source_method.value,
                "surface_cover_provenance": manifest.surface_cover_provenance,
                "luhk_provenance": manifest.luhk_provenance,
                "luhk_known_pixel_count": int(frame.get("luhk_label_valid", pd.Series(False, index=frame.index)).astype(bool).sum()),
                "qa_status": manifest.qa_status.value,
                "total_pixel_count": len(frame),
                "finite_pixel_count": int(finite.sum()),
                "label_known_pixel_count": int(frame["label_known"].astype(bool).sum()),
                "analysis_eligible_pixel_count": int(eligible.sum()),
                "excluded_pixel_count": int((~eligible).sum()),
                "unknown_label_pixel_count": int((~frame["label_known"].astype(bool)).sum()),
                "finite_temperature_mean_c": float(finite_temperature.mean()),
                "eligible_temperature_mean_c": float(eligible_temperature.mean()),
                "eligible_temperature_median_c": float(eligible_temperature.median()),
                "eligible_delta_t_mean_c": float(eligible_delta_t.mean()),
                "missing_ambient": bool(not frame["delta_temperature_available"].any()),
                "capture_datetime": str(frame["capture_datetime"].iloc[0]),
                "capture_time_local": str(frame["capture_time_local"].iloc[0]),
                "capture_time_utc": str(frame["capture_time_utc"].iloc[0]),
                "capture_time_source": str(frame["capture_time_source"].iloc[0]),
                "capture_timezone": str(frame["capture_timezone"].iloc[0]),
                "timezone_assumption": str(frame["timezone_assumption"].iloc[0]),
                "capture_time_valid": bool(frame["capture_time_valid"].iloc[0]),
                "ambient_source": str(frame["ambient_source"].iloc[0]),
                "ambient_definition": str(frame["ambient_definition"].iloc[0]),
                "target_id": manifest.target_id or "",
                "target_name": manifest.target_name or "",
                "location_id": manifest.location_id or "",
                "location_name": manifest.location_name or "",
                "roi_mask_sha256": str(frame["roi_mask_sha256"].iloc[0]),
                "roi_polygon_area_px2": float(frame["roi_polygon_area_px2"].iloc[0]),
                "roi_target_pixel_count": int(frame["roi_target_pixel_count"].iloc[0]),
                "roi_target_coverage_fraction": float(frame["roi_target_coverage_fraction"].iloc[0]),
                "roi_comparability_evidence": str(frame["roi_comparability_evidence"].iloc[0]),
                "surface_cover_category": manifest.surface_cover_category or "",
            }
            summaries.append(summary_row)
            image_level.append(summary_row)
            if write_full_csv:
                full_csv_frames.append(frame)
    finally:
        if writer is not None:
            writer.close()
    if writer is None:
        raise ValueError("No compatible successful canonical results were supplied to Part E.")
    summary = pd.DataFrame(summaries)
    summary.to_csv(summary_csv, index=False, encoding="utf-8-sig")
    if write_full_csv:
        pd.concat(full_csv_frames, ignore_index=True).to_csv(output_parquet.with_suffix(".csv"), index=False, encoding="utf-8-sig")
    if dashboard_directory is not None:
        write_source_dashboard(summary, dashboard_directory, write_explicit_pooled_sensitivity)
    return summary


def write_source_dashboard(summary: pd.DataFrame, directory: Path, include_pooled: bool = False) -> None:
    """Compare image-level summaries without weighting images by pixel count."""
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    directory.mkdir(parents=True, exist_ok=True)
    strata = [
        "measurement_type", "temperature_source", "temperature_definition", "source_method", "surface_cover_provenance",
        "luhk_provenance", "target_id", "target_name", "qa_status",
    ]
    grouped = (
        summary.groupby(strata, dropna=False, observed=True)
        .agg(
            image_count=("image_id", "nunique"),
            equal_image_mean_temperature_c=("eligible_temperature_mean_c", "mean"),
            equal_image_mean_delta_t_c=("eligible_delta_t_mean_c", "mean"),
            eligible_pixel_count=("analysis_eligible_pixel_count", "sum"),
        )
        .reset_index()
    )
    grouped["aggregation_policy"] = "equal_image_weighting; image/time is the temporal observation unit"
    grouped["interpretation"] = "exploratory"
    grouped.to_csv(directory / "part_e_source_stratified_dashboard.csv", index=False, encoding="utf-8-sig")
    labels = grouped["source_method"].astype(str) + "\n" + grouped["measurement_type"].astype(str)
    figure, axis = plt.subplots(figsize=(max(8, len(grouped) * 1.6), 5))
    axis.bar(np.arange(len(grouped)), grouped["equal_image_mean_temperature_c"].astype(float))
    axis.set_xticks(np.arange(len(grouped)), labels, rotation=25, ha="right")
    axis.set_ylabel("Equal-image mean eligible temperature (°C)")
    axis.set_title("Source-stratified comparison (images weighted equally; exploratory)")
    figure.tight_layout()
    figure.savefig(directory / "part_e_source_stratified_dashboard.png", dpi=180)
    figure.savefig(directory / "part_e_source_stratified_dashboard.pdf")
    plt.close(figure)
    if include_pooled:
        compatible = summary.loc[~summary["missing_ambient"].astype(bool)].copy()
        pooled = pd.DataFrame(
            [
                {
                    "result_name": "explicit_pooled_sensitivity_equal_image_weighted",
                    "image_count": int(compatible["image_id"].nunique()),
                    "equal_image_mean_delta_t_c": float(compatible["eligible_delta_t_mean_c"].mean()),
                    "source_composition_json": json.dumps(compatible["source_method"].value_counts().to_dict(), sort_keys=True),
                    "warning": "Optional sensitivity output; source-stratified results remain primary.",
                }
            ]
        )
        pooled.to_csv(directory / "part_e_explicit_pooled_sensitivity.csv", index=False, encoding="utf-8-sig")


def write_run_summary(path: Path, rows: list[GroupRunSummary]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "groups": [row.to_dict() for row in rows],
        "counts": {status.value: sum(row.status == status for row in rows) for status in ProcessingStatus},
        "part_e_inclusion": {
            "included": [row.image_id for row in rows if row.status in {ProcessingStatus.SUCCESS, ProcessingStatus.CACHE_HIT}],
            "failed": [row.image_id for row in rows if row.status == ProcessingStatus.FAILED],
            "cancelled": [row.image_id for row in rows if row.status == ProcessingStatus.CANCELLED],
            "awaiting_review": [
                row.image_id
                for row in rows
                if row.status in {
                    ProcessingStatus.AWAITING_PART_B0_REVIEW,
                    ProcessingStatus.AWAITING_PART_B_REVIEW,
                    ProcessingStatus.AWAITING_PART_C_REVIEW,
                }
            ],
            "excluded": [row.image_id for row in rows if row.status == ProcessingStatus.EXCLUDED],
            "incomplete": [row.image_id for row in rows if row.status == ProcessingStatus.INCOMPLETE],
        },
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)
