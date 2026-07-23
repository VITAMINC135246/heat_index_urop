#!/usr/bin/env python3
"""Benchmark v0.1 workload components without regenerating pilot data."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.workflow.input_validation import GroupInput, validate_group
from scripts.workflow.polygon_annotation import rasterize_polygon


def timed(function: Callable[[], Any]) -> tuple[Any, float]:
    start = time.perf_counter()
    result = function()
    return result, time.perf_counter() - start


def file_size(path: Path) -> int:
    return path.stat().st_size if path.is_file() else 0


def percentile(values: list[float], value: float) -> float:
    return float(np.percentile(np.asarray(values, dtype=float), value)) if values else 0.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-pilot-groups", type=int, default=5)
    parser.add_argument("--polygon-repetitions", type=int, default=100)
    parser.add_argument("--manual-review-seconds-per-group", type=float)
    parser.add_argument("--interaction-budget-minutes", type=float)
    parser.add_argument("--storage-budget-gb", type=float)
    parser.add_argument("--output", help="Default: ignored outputs/runs benchmark JSON.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.max_pilot_groups < 1 or args.polygon_repetitions < 1:
        raise ValueError("Benchmark counts must be positive.")
    pairs = pd.read_excel(PROJECT_ROOT / "data" / "metadata" / "part_b_pilot_pairs.xlsx").head(args.max_pilot_groups)
    part_d = pd.read_csv(
        PROJECT_ROOT / "outputs" / "part_d" / "summaries" / "part_d_tat3_parameter_temperature_extraction_summary.csv",
        keep_default_na=False,
    )
    validation_seconds: list[float] = []
    matrix_load_seconds: list[float] = []
    matrix_bytes: list[int] = []
    for _, pair in pairs.iterrows():
        group = GroupInput(
            group_id=str(pair["pair_id"]),
            visible_path=str(PROJECT_ROOT / str(pair["v_path"])),
            thermal_path=str(PROJECT_ROOT / str(pair["t_path"])),
            dataset_id="pilot",
        )
        _, duration = timed(lambda group=group: validate_group(group))
        validation_seconds.append(duration)
        rows = part_d.loc[part_d["image_id"].astype(str).eq(str(pair["image_id"]))]
        if len(rows) == 1:
            matrix_path = PROJECT_ROOT / str(rows.iloc[0]["npy_path"])
            if matrix_path.is_file():
                matrix, load_duration = timed(lambda path=matrix_path: np.load(path))
                matrix_load_seconds.append(load_duration)
                matrix_bytes.append(int(matrix.nbytes))

    polygon_seconds: list[float] = []
    for _ in range(args.polygon_repetitions):
        _, duration = timed(
            lambda: rasterize_polygon([(50, 50), (590, 60), (580, 450), (60, 440)], (512, 640))
        )
        polygon_seconds.append(duration)

    canonical_path = PROJECT_ROOT / "data" / "processed" / "part_e" / "part_e_pixel_delta_t.parquet"
    parquet_read_seconds = summary_seconds = 0.0
    parquet_rows = 0
    if canonical_path.is_file():
        frame, parquet_read_seconds = timed(
            lambda: pd.read_parquet(canonical_path, columns=["image_id", "temperature_c", "delta_t_c"])
        )
        parquet_rows = len(frame)
        _, summary_seconds = timed(
            lambda: frame.groupby("image_id", observed=True)[["temperature_c", "delta_t_c"]].agg(["count", "mean", "median"])
        )

    pixel_csvs = list((PROJECT_ROOT / "data" / "processed" / "part_e" / "excel_source").glob("*_pixel_data.csv"))
    pixel_workbooks = list((PROJECT_ROOT / "outputs" / "part_e" / "excel" / "pixel_workbooks").glob("*.xlsx"))
    canonical_directories = [
        path for path in (PROJECT_ROOT / "data" / "processed" / "images").glob("*")
        if path.is_dir() and (path / "manifest.json").is_file()
    ]
    canonical_directory_bytes = [
        sum(file_size(path) for path in directory.rglob("*") if path.is_file())
        for directory in canonical_directories
    ]
    result: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "machine_observations": {
            "pilot_groups_benchmarked": len(pairs),
            "part_a_validation_seconds_median": statistics.median(validation_seconds) if validation_seconds else 0.0,
            "part_a_validation_seconds_p95": percentile(validation_seconds, 95),
            "temperature_npy_load_seconds_median": statistics.median(matrix_load_seconds) if matrix_load_seconds else 0.0,
            "temperature_matrix_bytes_median": int(statistics.median(matrix_bytes)) if matrix_bytes else 0,
            "polygon_rasterization_seconds_median": statistics.median(polygon_seconds),
            "polygon_rasterization_seconds_p95": percentile(polygon_seconds, 95),
            "canonical_parquet_bytes": file_size(canonical_path),
            "canonical_parquet_rows": parquet_rows,
            "canonical_parquet_selected_column_read_seconds": parquet_read_seconds,
            "image_summary_seconds": summary_seconds,
            "full_pixel_csv_count": len(pixel_csvs),
            "full_pixel_csv_bytes_total": sum(file_size(path) for path in pixel_csvs),
            "full_pixel_csv_bytes_median": int(statistics.median([file_size(path) for path in pixel_csvs])) if pixel_csvs else 0,
            "per_image_workbook_count": len(pixel_workbooks),
            "per_image_workbook_bytes_total": sum(file_size(path) for path in pixel_workbooks),
            "canonical_result_count": len(canonical_directories),
            "canonical_result_bytes_median": (
                int(statistics.median(canonical_directory_bytes)) if canonical_directory_bytes else 0
            ),
        },
        "limit_policy": {
            "x_request_limit": "derive separately for unattended and interactive routes; do not use retained-result count",
            "x_compute_inputs": [
                "Part A p95", "Part B candidate p95", "SDK extraction p95", "Part E p95", "peak working memory",
                "manual Part B or polygon review seconds per group",
            ],
            "y_retention_limit": "derive from canonical NPY+Parquet bytes and a configured disk budget; optional CSV/Excel excluded",
        },
    }
    if args.manual_review_seconds_per_group and args.interaction_budget_minutes:
        result["limit_policy"]["interactive_x_from_supplied_budget"] = max(
            1, int((args.interaction_budget_minutes * 60) // args.manual_review_seconds_per_group)
        )
    if args.storage_budget_gb and (canonical_directory_bytes or matrix_bytes):
        canonical_bytes_per_image = (
            int(statistics.median(canonical_directory_bytes))
            if canonical_directory_bytes
            else int(statistics.median(matrix_bytes)) + file_size(canonical_path) // max(len(pairs), 1)
        )
        result["limit_policy"]["retained_y_from_supplied_budget"] = int(
            (args.storage_budget_gb * (1024**3)) // max(canonical_bytes_per_image, 1)
        )
    output = Path(args.output) if args.output else (
        PROJECT_ROOT / "outputs" / "runs" / f"benchmark_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    if not output.is_absolute():
        output = PROJECT_ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"Benchmark JSON: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
