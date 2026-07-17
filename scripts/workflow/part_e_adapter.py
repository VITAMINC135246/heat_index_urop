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
from .models import CanonicalManifest, GroupRunSummary, ProcessingStatus, QAStatus


os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parents[2] / ".matplotlib-cache"))

PROVENANCE_COLUMNS = [
    "measurement_type",
    "temperature_source",
    "source_method",
    "surface_cover_provenance",
    "luhk_provenance",
    "label_known",
    "analysis_eligible",
    "exclusion_reason",
    "target_name",
    "qa_status",
    "annotation_review_status",
]


def _compatible_frame(frame: pd.DataFrame, manifest: CanonicalManifest) -> pd.DataFrame:
    work = frame.copy()
    defaults: dict[str, object] = {
        "measurement_type": manifest.measurement_type.value,
        "temperature_source": manifest.temperature_source,
        "source_method": manifest.source_method.value,
        "surface_cover_provenance": manifest.surface_cover_provenance,
        "luhk_provenance": manifest.luhk_provenance,
        "target_name": manifest.target_name or "",
        "qa_status": manifest.qa_status.value,
        "annotation_review_status": manifest.review_status.value,
    }
    for column, value in defaults.items():
        if column not in work.columns:
            work[column] = value
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
        work["luhk_class_code"] = luhk_values
        work["luhk_class_name"] = luhk_values
        luhk_known = work.get("luhk_known")
        work["luhk_label_valid"] = (
            luhk_known.astype(bool)
            if isinstance(luhk_known, pd.Series)
            else pd.Series(False, index=work.index, dtype=bool)
        )
    defaults = {
        "flight_id": manifest.group_id,
        "capture_datetime": str(manifest.temperature_metadata.get("capture_time", "")),
        "luhk_cell_id": "",
        "luhk_class_code": str(manifest.luhk_code or ""),
        "luhk_class_name": manifest.luhk_category or "",
        "luhk_label_valid": False,
    }
    for column, value in defaults.items():
        if column not in work.columns:
            work[column] = value
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
                "source_method": manifest.source_method.value,
                "surface_cover_provenance": manifest.surface_cover_provenance,
                "luhk_provenance": manifest.luhk_provenance,
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
                "target_name": manifest.target_name or "",
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
        "measurement_type", "temperature_source", "source_method", "surface_cover_provenance",
        "luhk_provenance", "target_name", "qa_status",
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
            "awaiting_review": [row.image_id for row in rows if row.status in {ProcessingStatus.AWAITING_PART_B0_REVIEW, ProcessingStatus.AWAITING_PART_B_REVIEW}],
            "excluded": [row.image_id for row in rows if row.status == ProcessingStatus.EXCLUDED],
            "incomplete": [row.image_id for row in rows if row.status == ProcessingStatus.INCOMPLETE],
        },
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)
