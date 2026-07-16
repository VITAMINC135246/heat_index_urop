#!/usr/bin/env python3
"""Author five per-image workbook skeletons before the full Pixel_Data COM import."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from excel_workbook_common import run_builder
from part_e_pixel_common import ensure_output_directories, load_config, project_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/part_e_delta_t_analysis.json")
    parser.add_argument("--image-id", help="Build only the selected pilot image workbook.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    ensure_output_directories(config)
    summary = pd.read_csv(project_path(config["outputs"]["tables"]) / "part_e_full_pixel_summary_by_image.csv")
    canonical = project_path(config["outputs"]["canonical_parquet"])
    image_sample = pd.read_parquet(project_path(config["outputs"]["sample_directory"]) / "part_e_sample_image_comparison.parquet")
    source_dir = project_path(config["outputs"]["excel_source_directory"])
    output_dir = project_path(config["outputs"]["pixel_workbooks"])
    preview_dir = project_path(config["outputs"]["part_e_root"]) / "workbook_previews"
    payload_dir = preview_dir / "payloads"
    source_dir.mkdir(parents=True, exist_ok=True); output_dir.mkdir(parents=True, exist_ok=True)

    image_ids = [args.image_id] if args.image_id else list(config["pilot_image_ids"])
    unknown = sorted(set(image_ids).difference(map(str, config["pilot_image_ids"])))
    if unknown:
        raise ValueError(f"Unknown pilot image ID(s): {unknown}")
    for image_id in image_ids:
        row = summary.loc[summary["image_id"].eq(image_id)].iloc[0]
        table = pq.read_table(
            canonical,
            filters=[("image_id", "=", image_id)],
            columns=["pixel_uid", "thermal_row", "thermal_col", "temperature_c", "ambient_temperature_c", "delta_t_c"],
        )
        pixels = table.to_pandas()
        positions = np.linspace(0, len(pixels) - 1, int(config["excel"]["qa_formula_spotchecks_per_image"]), dtype=int)
        qa_rows = []
        for position in positions:
            pixel = pixels.iloc[position]
            qa_rows.append({
                "source_excel_row": int(position) + 2,
                "pixel_uid": str(pixel["pixel_uid"]),
                "thermal_row": int(pixel["thermal_row"]), "thermal_col": int(pixel["thermal_col"]),
                "temperature_c": float(pixel["temperature_c"]), "ambient_temperature_c": float(pixel["ambient_temperature_c"]),
                "delta_t_c": float(pixel["delta_t_c"]),
            })
        sample_csv = source_dir / f"{image_id}_analysis_sample.csv"
        image_sample.loc[image_sample["image_id"].eq(image_id)].sort_values(["thermal_row", "thermal_col"]).to_csv(sample_csv, index=False, encoding="utf-8-sig")
        summary_rows = [
            ["image_id", image_id], ["image dimensions", f"{int(row['image_height'])} × {int(row['image_width'])}"],
            ["total pixel count", int(row["total_pixel_count"])], ["finite pixel count", int(row["finite_pixel_count"])],
            ["accepted pixel count", int(row["accepted_pixel_count"])], ["LUHK-labelled pixel count", int(row["luhk_labelled_pixel_count"])],
            ["cover-labelled pixel count", int(row["cover_labelled_pixel_count"])], ["shadow-known pixel count", int(row["shadow_known_pixel_count"])],
            ["ambient_temperature_c", float(row["ambient_temperature_c"])], ["temperature mean (°C)", float(row["temperature_mean_c"])],
            ["temperature median (°C)", float(row["temperature_median_c"])], ["temperature minimum (°C)", float(row["temperature_min_c"])],
            ["temperature maximum (°C)", float(row["temperature_max_c"])], ["ΔT mean (°C)", float(row["delta_t_mean_c"])],
            ["ΔT median (°C)", float(row["delta_t_median_c"])], ["ΔT minimum (°C)", float(row["delta_t_min_c"])],
            ["ΔT maximum (°C)", float(row["delta_t_max_c"])], ["generation timestamp UTC", str(row["generation_timestamp_utc"])],
            ["Git commit at generation", str(row["git_commit_at_generation"])],
        ]
        payload = {
            "mode": "pixel", "image_id": image_id,
            "output": str(output_dir / f"{image_id}_pixel_delta_t.xlsx"),
            "preview_dir": str(preview_dir / image_id),
            "analysis_sample_csv": str(sample_csv), "summary_rows": summary_rows, "qa_rows": qa_rows,
            "chart_data": {
                "temperature_mean_c": float(row["temperature_mean_c"]),
                "ambient_temperature_c": float(row["ambient_temperature_c"]),
                "delta_t_mean_c": float(row["delta_t_mean_c"]),
            },
        }
        run_builder(payload, payload_dir / f"{image_id}.json")
        print(f"Artifact-tool skeleton complete: {image_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
