#!/usr/bin/env python3
"""Generate provisional Part E descriptive summary tables."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from part_e.part_e_common import (  # noqa: E402
    PART_E_SUMMARY_DIR,
    PART_E_TABLE_DIR,
    PROVISIONAL_NOTICE,
    read_dataset,
    relative_posix,
    round_float,
    write_csv,
    write_markdown,
)


CELL_DATA = PART_E_TABLE_DIR / "part_e_cell_delta_t_observations_all_finite.csv"
COVER_DATA = PART_E_TABLE_DIR / "part_e_surface_cover_delta_t_observations_all_finite.csv"
SUMMARY_MD = PART_E_SUMMARY_DIR / "part_e_summary_tables_build_summary.md"


def numeric_series(df: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(df[column], errors="coerce").dropna()


def summarize(df: pd.DataFrame, group_cols: list[str], value_col: str) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    valid = df.loc[pd.to_numeric(df.get("analysis_valid", 0), errors="coerce").fillna(0).astype(int).eq(1)].copy()
    if valid.empty:
        return pd.DataFrame()
    grouped = valid.groupby(group_cols, dropna=False, sort=True)
    for keys, group in grouped:
        if not isinstance(keys, tuple):
            keys = (keys,)
        values = numeric_series(group, value_col)
        row = {column: key for column, key in zip(group_cols, keys)}
        n = int(values.size)
        row.update(
            {
                "observation_count": len(group),
                "numeric_observation_count": n,
                "image_count": group["image_id"].nunique() if "image_id" in group.columns else "",
                "unique_cell_count": group["cell_id"].nunique() if "cell_id" in group.columns else "",
                "mean_delta_t_c": round_float(values.mean()) if n else "",
                "median_delta_t_c": round_float(values.median()) if n else "",
                "std_delta_t_c": round_float(values.std(ddof=1)) if n > 1 else (0.0 if n == 1 else ""),
                "min_delta_t_c": round_float(values.min()) if n else "",
                "max_delta_t_c": round_float(values.max()) if n else "",
                "q1_delta_t_c": round_float(values.quantile(0.25)) if n else "",
                "q3_delta_t_c": round_float(values.quantile(0.75)) if n else "",
                "iqr_delta_t_c": round_float(values.quantile(0.75) - values.quantile(0.25)) if n else "",
                "p05_delta_t_c": round_float(values.quantile(0.05)) if n else "",
                "p95_delta_t_c": round_float(values.quantile(0.95)) if n else "",
                "standard_error_delta_t_c": round_float(values.std(ddof=1) / np.sqrt(n)) if n > 1 else "",
                "qa_warning_count": int(pd.to_numeric(group.get("qa_warning_flag", 0), errors="coerce").fillna(0).sum()),
                "provisional_result_note": PROVISIONAL_NOTICE,
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


def sensitivity_comparison(cell: pd.DataFrame) -> pd.DataFrame:
    sensitivity_files = sorted(PART_E_TABLE_DIR.glob("part_e_cell_delta_t_observations_sensitivity_excluding_below_*c.csv"))
    if not sensitivity_files:
        return pd.DataFrame(
            [
                {
                    "analysis_variant": "all_finite",
                    "comparison_status": "not_generated",
                    "notes": "No explicit sensitivity threshold was configured for this run.",
                }
            ]
        )
    rows = []
    main = cell.loc[pd.to_numeric(cell["analysis_valid"], errors="coerce").fillna(0).astype(int).eq(1)].copy()
    main_values = pd.to_numeric(main["delta_t_mean_c"], errors="coerce")
    for path in sensitivity_files:
        other = pd.read_csv(path, keep_default_na=False)
        valid = other.loc[pd.to_numeric(other["analysis_valid"], errors="coerce").fillna(0).astype(int).eq(1)].copy()
        merged = main[["observation_id", "delta_t_mean_c"]].merge(
            valid[["observation_id", "delta_t_mean_c"]],
            on="observation_id",
            how="inner",
            suffixes=("_all_finite", "_sensitivity"),
        )
        diff = pd.to_numeric(merged["delta_t_mean_c_sensitivity"], errors="coerce") - pd.to_numeric(
            merged["delta_t_mean_c_all_finite"], errors="coerce"
        )
        rows.append(
            {
                "analysis_variant": str(valid["analysis_variant"].iloc[0]) if not valid.empty else path.stem,
                "comparison_status": "generated",
                "all_finite_valid_observations": len(main),
                "sensitivity_valid_observations": len(valid),
                "paired_observation_count": len(merged),
                "all_finite_mean_delta_t_c": round_float(main_values.mean()) if len(main_values) else "",
                "sensitivity_mean_delta_t_c": round_float(pd.to_numeric(valid["delta_t_mean_c"], errors="coerce").mean()) if not valid.empty else "",
                "paired_mean_difference_sensitivity_minus_all_finite_c": round_float(diff.mean()) if not diff.empty else "",
                "paired_median_difference_sensitivity_minus_all_finite_c": round_float(diff.median()) if not diff.empty else "",
                "notes": "Sensitivity analysis is not corrected ground truth.",
            }
        )
    return pd.DataFrame(rows)


def main() -> int:
    cell = read_dataset(CELL_DATA, "cell-level Part E dataset")
    cover = read_dataset(COVER_DATA, "cell-by-surface-cover Part E dataset")
    outputs: list[Path] = []

    summary_specs = [
        (cell, ["luhk_original_class"], "delta_t_mean_c", PART_E_TABLE_DIR / "part_e_luhk_original_class_summary.csv"),
        (cell, ["luhk_aggregated_class"], "delta_t_mean_c", PART_E_TABLE_DIR / "part_e_luhk_aggregated_class_summary.csv"),
        (cell, ["image_id"], "delta_t_mean_c", PART_E_TABLE_DIR / "part_e_image_level_summary.csv"),
        (cell, ["acquisition_datetime"], "delta_t_mean_c", PART_E_TABLE_DIR / "part_e_acquisition_time_summary.csv"),
        (cell, ["flight_id"], "delta_t_mean_c", PART_E_TABLE_DIR / "part_e_flight_summary.csv"),
        (cell, ["dominant_physical_surface_cover_class"], "delta_t_mean_c", PART_E_TABLE_DIR / "part_e_dominant_surface_cover_summary.csv"),
        (cover, ["physical_surface_cover_class"], "class_delta_t_mean_c", PART_E_TABLE_DIR / "part_e_surface_cover_summary.csv"),
        (cover, ["luhk_aggregated_class", "physical_surface_cover_class"], "class_delta_t_mean_c", PART_E_TABLE_DIR / "part_e_luhk_surface_cover_summary.csv"),
        (cover, ["image_id", "physical_surface_cover_class"], "class_delta_t_mean_c", PART_E_TABLE_DIR / "part_e_image_surface_cover_summary.csv"),
    ]
    for df, groups, value, path in summary_specs:
        out = summarize(df, groups, value)
        write_csv(path, out)
        outputs.append(path)

    sensitivity = sensitivity_comparison(cell)
    sensitivity_path = PART_E_TABLE_DIR / "part_e_sensitivity_analysis_comparison.csv"
    write_csv(sensitivity_path, sensitivity)
    outputs.append(sensitivity_path)

    lines = [
        "# Part E Descriptive Summary Tables",
        "",
        f"**Provisional-result rule:** {PROVISIONAL_NOTICE}",
        "",
        f"- Cell input: `{relative_posix(CELL_DATA)}`",
        f"- Cell-cover input: `{relative_posix(COVER_DATA)}`",
        "",
        "## Tables Written",
        "",
    ]
    lines.extend(f"- `{relative_posix(path)}`" for path in outputs)
    write_markdown(SUMMARY_MD, lines)
    print(f"Summary tables written: {len(outputs)}")
    print(f"Summary report: {relative_posix(SUMMARY_MD)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
