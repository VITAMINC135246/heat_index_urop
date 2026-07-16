#!/usr/bin/env python3
"""Build the canonical one-row-per-thermal-pixel Part E Parquet dataset."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from part_e_pixel_common import (
    EXPECTED_SHAPE,
    build_image_records,
    build_luhk_pixel_labels,
    class_mapping,
    ensure_output_directories,
    git_info,
    load_config,
    load_masks,
    load_source_tables,
    load_temperature,
    project_path,
    relative,
    write_csv,
)


CANONICAL_COLUMNS = [
    "image_id", "flight_id", "capture_datetime", "thermal_row", "thermal_col", "pixel_x", "pixel_y", "pixel_uid",
    "temperature_c", "ambient_temperature_c", "delta_t_c", "temperature_is_finite", "pixel_accepted",
    "ambient_source", "ambient_validation_status", "pixel_policy",
    "luhk_cell_id", "luhk_grid_row", "luhk_grid_col", "luhk_class_code", "luhk_class_name",
    "luhk_assignment_method", "luhk_label_valid",
    "surface_cover_class_id", "surface_cover_class", "surface_cover_valid", "surface_cover_review_status",
    "shadow_flag", "shadow_valid", "location", "relative_altitude_m", "gps_latitude", "gps_longitude",
    "solar_azimuth", "solar_elevation", "pair_id", "spatial_label_uncertainty",
]


SCHEMA = pa.schema([
    pa.field("image_id", pa.string()), pa.field("flight_id", pa.string()), pa.field("capture_datetime", pa.string()),
    pa.field("thermal_row", pa.int16()), pa.field("thermal_col", pa.int16()), pa.field("pixel_x", pa.int16()), pa.field("pixel_y", pa.int16()), pa.field("pixel_uid", pa.string()),
    pa.field("temperature_c", pa.float32()), pa.field("ambient_temperature_c", pa.float32()), pa.field("delta_t_c", pa.float32()),
    pa.field("temperature_is_finite", pa.bool_()), pa.field("pixel_accepted", pa.bool_()),
    pa.field("ambient_source", pa.string()), pa.field("ambient_validation_status", pa.string()), pa.field("pixel_policy", pa.string()),
    pa.field("luhk_cell_id", pa.string()), pa.field("luhk_grid_row", pa.int32()), pa.field("luhk_grid_col", pa.int32()),
    pa.field("luhk_class_code", pa.int16()), pa.field("luhk_class_name", pa.string()), pa.field("luhk_assignment_method", pa.string()), pa.field("luhk_label_valid", pa.bool_()),
    pa.field("surface_cover_class_id", pa.int16()), pa.field("surface_cover_class", pa.string()), pa.field("surface_cover_valid", pa.bool_()), pa.field("surface_cover_review_status", pa.string()),
    pa.field("shadow_flag", pa.int8()), pa.field("shadow_valid", pa.bool_()), pa.field("location", pa.string()),
    pa.field("relative_altitude_m", pa.float32()), pa.field("gps_latitude", pa.float64()), pa.field("gps_longitude", pa.float64()),
    pa.field("solar_azimuth", pa.float32()), pa.field("solar_elevation", pa.float32()), pa.field("pair_id", pa.string()), pa.field("spatial_label_uncertainty", pa.string()),
])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/part_e_delta_t_analysis.json")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def scalar(value: object, default: float = np.nan) -> float:
    try:
        result = float(value)
        return result if np.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def build_image_frame(record: pd.Series, tables: dict[str, pd.DataFrame], config: dict) -> pd.DataFrame:
    image_id = str(record["image_id"])
    temperature = load_temperature(record)
    cover_mask, shadow_mask = load_masks(record)
    luhk = build_luhk_pixel_labels(record, tables)
    cover_names = class_mapping(tables)
    rows = np.repeat(np.arange(EXPECTED_SHAPE[0], dtype=np.int16), EXPECTED_SHAPE[1])
    cols = np.tile(np.arange(EXPECTED_SHAPE[1], dtype=np.int16), EXPECTED_SHAPE[0])
    flat_temperature = temperature.ravel(order="C")
    finite = np.isfinite(flat_temperature)
    ambient = np.float32(record["ambient_temperature_c"])
    delta_t = (flat_temperature - ambient).astype(np.float32, copy=False)
    delta_t[~finite] = np.nan

    mapped = np.asarray(luhk["mapped"], dtype=bool).ravel(order="C")
    luhk_code = np.asarray(luhk["class_code"], dtype=np.int16).ravel(order="C")
    luhk_cell = np.asarray(luhk["cell_id"], dtype=object).ravel(order="C")
    luhk_name = np.asarray(luhk["class_name"], dtype=object).ravel(order="C")
    luhk_row = np.asarray(luhk["luhk_row"], dtype=np.int32).ravel(order="C")
    luhk_col = np.asarray(luhk["luhk_col"], dtype=np.int32).ravel(order="C")
    luhk_cell[~mapped] = ""
    luhk_name[~mapped] = ""
    luhk_code[~mapped] = -1
    luhk_row[~mapped] = -1
    luhk_col[~mapped] = -1

    cover_id = cover_mask.astype(np.int16, copy=False).ravel(order="C")
    cover_valid = ~np.isin(cover_id, [0, 9])
    cover_name = np.array([cover_names.get(int(value), "unknown_or_unlabelled") for value in cover_id], dtype=object)
    cover_name[~cover_valid] = "unknown_or_unlabelled"
    review_status = np.where(cover_valid, str(record.get("manual_review_status", "all_reviewed")), "unlabelled_or_excluded")

    if shadow_mask is None:
        shadow_flag = pd.array([pd.NA] * flat_temperature.size, dtype="Int8")
        shadow_valid = np.zeros(flat_temperature.size, dtype=bool)
    else:
        shadow_flag = pd.array(shadow_mask.astype(np.int8, copy=False).ravel(order="C"), dtype="Int8")
        shadow_valid = np.ones(flat_temperature.size, dtype=bool)

    pixel_uid = np.array(
        [f"{image_id}__r{int(row):03d}_c{int(col):03d}" for row, col in zip(rows, cols)],
        dtype=object,
    )
    n = flat_temperature.size
    spatial_uncertainty = str(record.get("spatial_uncertainty_notes", "")) or (
        "Approximate north-up metadata footprint; yaw not applied."
    )
    frame = pd.DataFrame({
        "image_id": np.repeat(image_id, n),
        "flight_id": np.repeat(str(record["flight_id"]), n),
        "capture_datetime": np.repeat(str(record["capture_datetime"]), n),
        "thermal_row": rows,
        "thermal_col": cols,
        "pixel_x": cols,
        "pixel_y": rows,
        "pixel_uid": pixel_uid,
        "temperature_c": flat_temperature,
        "ambient_temperature_c": np.repeat(ambient, n).astype(np.float32),
        "delta_t_c": delta_t,
        "temperature_is_finite": finite,
        "pixel_accepted": finite.copy(),
        "ambient_source": np.repeat(config["ambient_source"], n),
        "ambient_validation_status": np.repeat(config["ambient_validation_status"], n),
        "pixel_policy": np.repeat(config["pixel_policy"], n),
        "luhk_cell_id": luhk_cell,
        "luhk_grid_row": luhk_row,
        "luhk_grid_col": luhk_col,
        "luhk_class_code": luhk_code,
        "luhk_class_name": luhk_name,
        "luhk_assignment_method": np.repeat(config["luhk_assignment"]["method"], n),
        "luhk_label_valid": mapped,
        "surface_cover_class_id": cover_id,
        "surface_cover_class": cover_name,
        "surface_cover_valid": cover_valid,
        "surface_cover_review_status": review_status,
        "shadow_flag": shadow_flag,
        "shadow_valid": shadow_valid,
        "location": np.repeat("HKUST", n),
        "relative_altitude_m": np.repeat(np.float32(scalar(record.get("t_relative_altitude"))), n),
        "gps_latitude": np.repeat(scalar(record.get("gps_latitude")), n),
        "gps_longitude": np.repeat(scalar(record.get("gps_longitude")), n),
        "solar_azimuth": np.repeat(np.float32(np.nan), n),
        "solar_elevation": np.repeat(np.float32(np.nan), n),
        "pair_id": np.repeat(str(record["pair_id"]), n),
        "spatial_label_uncertainty": np.repeat(spatial_uncertainty, n),
    })
    return frame[CANONICAL_COLUMNS]


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    ensure_output_directories(config)
    target = project_path(config["outputs"]["canonical_parquet"])
    if target.exists() and not (args.overwrite or config.get("overwrite", False)):
        raise FileExistsError(f"Canonical output exists and overwrite is disabled: {target}")
    tables = load_source_tables(config)
    records = build_image_records(config, tables)
    excel_source_dir = project_path(config["outputs"]["excel_source_directory"])
    excel_source_dir.mkdir(parents=True, exist_ok=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    writer = pq.ParquetWriter(target, SCHEMA, compression="zstd", use_dictionary=True)
    summaries: list[dict[str, object]] = []
    generated = datetime.now(timezone.utc).isoformat()
    git = git_info()
    try:
        for _, record in records.iterrows():
            frame = build_image_frame(record, tables, config)
            image_id = str(record["image_id"])
            if frame["pixel_uid"].duplicated().any():
                raise ValueError(f"Duplicate pixel_uid detected for {image_id}.")
            accepted = frame["pixel_accepted"].astype(bool)
            if not np.allclose(
                frame.loc[accepted, "temperature_c"].to_numpy(float) - frame.loc[accepted, "ambient_temperature_c"].to_numpy(float),
                frame.loc[accepted, "delta_t_c"].to_numpy(float),
                atol=2e-6,
            ):
                raise ValueError(f"Pixel delta-T arithmetic failed for {image_id}.")
            table = pa.Table.from_pandas(frame, schema=SCHEMA, preserve_index=False, safe=False)
            writer.write_table(table, row_group_size=65536)
            frame.to_csv(excel_source_dir / f"{image_id}_pixel_data.csv", index=False, encoding="utf-8-sig")
            finite_values = frame.loc[accepted, "temperature_c"].astype(float)
            delta_values = frame.loc[accepted, "delta_t_c"].astype(float)
            summaries.append({
                "image_id": image_id,
                "image_height": EXPECTED_SHAPE[0], "image_width": EXPECTED_SHAPE[1],
                "total_pixel_count": len(frame), "finite_pixel_count": int(accepted.sum()), "accepted_pixel_count": int(accepted.sum()),
                "luhk_labelled_pixel_count": int(frame["luhk_label_valid"].sum()),
                "cover_labelled_pixel_count": int(frame["surface_cover_valid"].sum()),
                "shadow_known_pixel_count": int(frame["shadow_valid"].sum()),
                "shadow_present_pixel_count": int((frame["shadow_flag"] == 1).sum()),
                "ambient_temperature_c": float(record["ambient_temperature_c"]),
                "temperature_mean_c": float(finite_values.mean()), "temperature_median_c": float(finite_values.median()),
                "temperature_min_c": float(finite_values.min()), "temperature_max_c": float(finite_values.max()),
                "delta_t_mean_c": float(delta_values.mean()), "delta_t_median_c": float(delta_values.median()),
                "delta_t_min_c": float(delta_values.min()), "delta_t_max_c": float(delta_values.max()),
                "generation_timestamp_utc": generated, "git_commit_at_generation": git["commit"],
            })
            print(f"Wrote {image_id}: {len(frame):,} pixels")
    finally:
        writer.close()
    summary = pd.DataFrame(summaries)
    write_csv(project_path(config["outputs"]["tables"]) / "part_e_full_pixel_summary_by_image.csv", summary)
    print(f"Canonical Parquet: {relative(target)} ({target.stat().st_size:,} bytes)")
    print(f"Total rows: {sum(item['total_pixel_count'] for item in summaries):,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
