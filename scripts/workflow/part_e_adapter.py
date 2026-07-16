"""Common Part E ingestion for successful schema-0.1 per-image results."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .canonical_result import load_manifest
from .models import CanonicalManifest, GroupRunSummary, ProcessingStatus


PROVENANCE_COLUMNS = [
    "source_method",
    "label_provenance",
    "label_known",
    "analysis_eligible",
    "exclusion_reason",
    "target_name",
    "annotation_review_status",
]


def _compatible_frame(frame: pd.DataFrame, manifest: CanonicalManifest) -> pd.DataFrame:
    work = frame.copy()
    for column in PROVENANCE_COLUMNS:
        if column not in work.columns:
            raise ValueError(f"Canonical pixels for {manifest.image_id} are missing {column}.")
    ambient = manifest.temperature_metadata.get("ambient_temperature_c")
    try:
        ambient_value = float(ambient)
    except (TypeError, ValueError):
        ambient_value = np.nan
    work["ambient_temperature_c"] = np.float32(ambient_value)
    work["delta_t_c"] = (pd.to_numeric(work["temperature_c"], errors="coerce") - ambient_value).astype("float32")
    if not np.isfinite(ambient_value):
        work["delta_t_c"] = np.float32(np.nan)
    work["pixel_accepted"] = work["temperature_is_finite"].astype(bool)
    work["surface_cover_valid"] = work["analysis_eligible"].astype(bool)
    work["surface_cover_review_status"] = work["annotation_review_status"].astype(str)
    defaults: dict[str, object] = {
        "flight_id": manifest.group_id,
        "capture_datetime": str(manifest.temperature_metadata.get("capture_time", "")),
        "luhk_cell_id": "",
        "luhk_class_code": -1,
        "luhk_class_name": "",
        "luhk_label_valid": False,
    }
    for column, value in defaults.items():
        if column not in work.columns:
            work[column] = value
    return work


def read_canonical_pixels(manifest_path: Path) -> tuple[CanonicalManifest, pd.DataFrame]:
    manifest = load_manifest(manifest_path)
    if manifest.processing_status != ProcessingStatus.SUCCESS:
        raise ValueError(f"Only successful canonical results may enter Part E: {manifest.image_id}")
    artifact = manifest.artifacts.get("pixels")
    if artifact is None:
        raise ValueError(f"Canonical result has no pixels.parquet artifact: {manifest.image_id}")
    pixels_path = Path(artifact.path)
    if not pixels_path.is_absolute():
        pixels_path = manifest_path.parent / pixels_path
    return manifest, _compatible_frame(pd.read_parquet(pixels_path), manifest)


def aggregate_canonical_results(
    manifest_paths: Iterable[Path],
    *,
    output_parquet: Path,
    summary_csv: Path,
    write_full_csv: bool = False,
) -> pd.DataFrame:
    output_parquet.parent.mkdir(parents=True, exist_ok=True)
    summary_csv.parent.mkdir(parents=True, exist_ok=True)
    writer: pq.ParquetWriter | None = None
    summaries: list[dict[str, object]] = []
    total_rows = 0
    full_csv_frames: list[pd.DataFrame] = []
    try:
        for manifest_path in manifest_paths:
            manifest, frame = read_canonical_pixels(manifest_path)
            table = pa.Table.from_pandas(frame, preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(output_parquet, table.schema, compression="zstd", use_dictionary=True)
            elif table.schema != writer.schema:
                table = table.cast(writer.schema)
            writer.write_table(table, row_group_size=65536)
            total_rows += len(frame)
            eligible = frame["analysis_eligible"].astype(bool)
            finite = frame["temperature_is_finite"].astype(bool)
            finite_temperature = pd.to_numeric(frame.loc[finite, "temperature_c"], errors="coerce")
            eligible_temperature = pd.to_numeric(frame.loc[finite & eligible, "temperature_c"], errors="coerce")
            eligible_delta_t = pd.to_numeric(frame.loc[finite & eligible, "delta_t_c"], errors="coerce")
            summaries.append(
                {
                    "image_id": manifest.image_id,
                    "group_id": manifest.group_id,
                    "processing_route": manifest.processing_route.value,
                    "source_method": manifest.source_method.value,
                    "qa_status": manifest.qa_status.value,
                    "total_pixel_count": len(frame),
                    "finite_pixel_count": int(finite.sum()),
                    "label_known_pixel_count": int(frame["label_known"].astype(bool).sum()),
                    "analysis_eligible_pixel_count": int(eligible.sum()),
                    "excluded_pixel_count": int((~eligible).sum()),
                    "finite_temperature_mean_c": float(finite_temperature.mean()),
                    "eligible_temperature_mean_c": float(eligible_temperature.mean()),
                    "eligible_temperature_median_c": float(eligible_temperature.median()),
                    "eligible_delta_t_mean_c": float(eligible_delta_t.mean()),
                    "target_name": manifest.target_name or "",
                    "surface_cover_category": manifest.surface_cover_category or "",
                }
            )
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
        pd.concat(full_csv_frames, ignore_index=True).to_csv(
            output_parquet.with_suffix(".csv"), index=False, encoding="utf-8-sig"
        )
    return summary


def write_run_summary(path: Path, rows: list[GroupRunSummary]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "groups": [row.to_dict() for row in rows],
        "counts": {
            status.value: sum(row.status == status for row in rows)
            for status in ProcessingStatus
        },
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
