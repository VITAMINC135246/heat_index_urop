#!/usr/bin/env python3
"""Build provisional LUHK-cell-level delta-T observations for Part E."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from part_e.part_e_common import (  # noqa: E402
    AMBIENT_MANIFEST,
    PART_E_SUMMARY_DIR,
    PART_E_TABLE_DIR,
    PROVISIONAL_NOTICE,
    AmbientInputError,
    build_pixel_cell_mapping,
    class_name,
    is_analysis_cover_class,
    load_class_mapping,
    load_footprints,
    load_image_records,
    load_part_c_masks,
    load_temperature_matrix,
    load_thermal_grid_cells,
    qa_warning_flag,
    relative_posix,
    round_float,
    safe_name,
    validate_ambient_manifest,
    values_stats,
    write_csv,
    write_markdown,
)


CELL_OUTPUT = PART_E_TABLE_DIR / "part_e_cell_delta_t_observations_all_finite.csv"
CELL_AUDIT_OUTPUT = PART_E_TABLE_DIR / "part_e_cell_delta_t_exclusion_audit.csv"
BUILD_SUMMARY_MD = PART_E_SUMMARY_DIR / "part_e_cell_delta_t_dataset_build_summary.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ambient-manifest", type=Path, default=AMBIENT_MANIFEST)
    parser.add_argument("--min-valid-coverage", type=float, default=0.5)
    parser.add_argument("--sensitivity-exclude-below-c", type=float, default=None)
    return parser.parse_args()


def sensitivity_output_path(threshold: float) -> Path:
    threshold_name = str(threshold).replace("-", "minus_").replace(".", "p")
    return PART_E_TABLE_DIR / f"part_e_cell_delta_t_observations_sensitivity_excluding_below_{threshold_name}c.csv"


def analysis_mask(temps: np.ndarray, threshold: float | None) -> np.ndarray:
    mask = np.isfinite(temps)
    if threshold is not None:
        mask &= temps >= threshold
    return mask


def dominant_cover(pixel_mask: np.ndarray, class_mask: np.ndarray, class_names: dict[int, str]) -> tuple[int | str, str, int, float]:
    if int(pixel_mask.sum()) == 0:
        return "", "", 0, 0.0
    classes, counts = np.unique(class_mask[pixel_mask], return_counts=True)
    valid = [
        (int(class_id), int(count))
        for class_id, count in zip(classes.tolist(), counts.tolist())
        if is_analysis_cover_class(int(class_id), class_names)
    ]
    if not valid:
        return "", "", 0, 0.0
    class_id, count = max(valid, key=lambda item: item[1])
    return class_id, class_name(class_id, class_names), count, count / int(pixel_mask.sum())


def build_variant(
    records: pd.DataFrame,
    ambient: pd.DataFrame,
    grid: pd.DataFrame,
    footprints: pd.DataFrame,
    class_names: dict[int, str],
    min_valid_coverage: float,
    sensitivity_threshold: float | None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    ambient_by_image = ambient.set_index("image_id").to_dict(orient="index")
    rows: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    mapping_stats: list[dict[str, Any]] = []
    variant = "all_finite" if sensitivity_threshold is None else f"sensitivity_exclude_below_{sensitivity_threshold:g}c"

    for _, record in records.sort_values("image_id").iterrows():
        image_id = str(record["image_id"])
        temps = load_temperature_matrix(record)
        class_mask, shadow_mask = load_part_c_masks(record)
        mapping = build_pixel_cell_mapping(grid, footprints, str(record["pair_id"]), temps.shape)
        valid_mask = analysis_mask(temps, sensitivity_threshold)
        ambient_row = ambient_by_image[image_id]
        ambient_c = float(ambient_row["ambient_temperature_c"])
        mapping_stats.append(
            {
                "image_id": image_id,
                "mapped_pixel_count": mapping.mapped_pixel_count,
                "unmapped_pixel_count": mapping.unmapped_pixel_count,
                "origin_x_2326": round_float(mapping.origin_x_2326),
                "origin_y_2326": round_float(mapping.origin_y_2326),
            }
        )

        for cell_index, cell in mapping.cells.iterrows():
            pixel_mask = mapping.cell_index == cell_index
            mapped_count = int(pixel_mask.sum())
            valid_pixels = pixel_mask & valid_mask
            values = temps[valid_pixels]
            valid_count = int(valid_pixels.sum())
            finite_in_cell = pixel_mask & np.isfinite(temps)
            below0_count = int((finite_in_cell & (temps < 0)).sum())
            below5_count = int((finite_in_cell & (temps < -5)).sum())
            below10_count = int((finite_in_cell & (temps < -10)).sum())
            coverage_fraction = valid_count / mapped_count if mapped_count else 0.0
            stats = values_stats(values)
            dominant_id, dominant_name, dominant_count, dominant_fraction = dominant_cover(pixel_mask, class_mask, class_names)
            shadow_fraction = float((shadow_mask[pixel_mask] == 1).mean()) if mapped_count else 0.0
            reasons: list[str] = []
            if mapped_count == 0:
                reasons.append("no_mapped_thermal_pixels")
            if valid_count == 0:
                reasons.append("no_valid_temperature_pixels_after_variant_rule")
            if mapped_count and coverage_fraction < min_valid_coverage:
                reasons.append("valid_temperature_coverage_below_threshold")
            analysis_valid = int(not reasons)
            observation_id = f"{image_id}__{cell['global_cell_id']}"
            row = {
                "observation_id": observation_id,
                "primary_key": observation_id,
                "analysis_variant": variant,
                "image_id": image_id,
                "flight_id": record.get("flight_id", ""),
                "pair_id": record.get("pair_id", ""),
                "acquisition_datetime": record.get("acquisition_datetime", ""),
                "cell_id": cell["global_cell_id"],
                "luhk_row": int(cell["luhk_row"]),
                "luhk_col": int(cell["luhk_col"]),
                "cell_center_x_2326": round_float(cell["cell_center_x_2326"]),
                "cell_center_y_2326": round_float(cell["cell_center_y_2326"]),
                "cell_min_x_2326": round_float(cell["cell_min_x_2326"]),
                "cell_max_x_2326": round_float(cell["cell_max_x_2326"]),
                "cell_min_y_2326": round_float(cell["cell_min_y_2326"]),
                "cell_max_y_2326": round_float(cell["cell_max_y_2326"]),
                "luhk_original_code": cell["luhk_raw_code"],
                "luhk_original_class": cell["luhk_raw_code"],
                "luhk_aggregated_class": cell["luhk_category_name"],
                "luhk_majority_fraction": 1.0,
                "mixed_luhk_flag": 0,
                "dominant_physical_surface_cover_class_id": dominant_id,
                "dominant_physical_surface_cover_class": dominant_name,
                "dominant_physical_surface_cover_pixel_count": dominant_count,
                "dominant_physical_surface_cover_fraction": round_float(dominant_fraction),
                "total_mapped_pixel_count": mapped_count,
                "valid_temperature_pixel_count": valid_count,
                "valid_temperature_coverage_fraction": round_float(coverage_fraction),
                "cell_thermal_coverage_fraction": round_float(cell["thermal_coverage_ratio"]),
                "mean_surface_temperature_c": stats["mean"],
                "median_surface_temperature_c": stats["median"],
                "std_surface_temperature_c": stats["std"],
                "min_surface_temperature_c": stats["min"],
                "max_surface_temperature_c": stats["max"],
                "p01_surface_temperature_c": stats["p01"],
                "p99_surface_temperature_c": stats["p99"],
                "below_0_c_pixel_count": below0_count,
                "below_0_c_pixel_fraction": round_float(below0_count / mapped_count if mapped_count else 0.0),
                "below_minus_5_c_pixel_count": below5_count,
                "below_minus_5_c_pixel_fraction": round_float(below5_count / mapped_count if mapped_count else 0.0),
                "below_minus_10_c_pixel_count": below10_count,
                "below_minus_10_c_pixel_fraction": round_float(below10_count / mapped_count if mapped_count else 0.0),
                "shadow_pixel_count": int((shadow_mask[pixel_mask] == 1).sum()) if mapped_count else 0,
                "shadow_fraction": round_float(shadow_fraction),
                "ambient_temperature_c": round_float(ambient_c),
                "ambient_source": ambient_row["ambient_source"],
                "ambient_source_id": ambient_row["ambient_source_id"],
                "ambient_observation_datetime": ambient_row["ambient_observation_datetime"],
                "ambient_time_difference_minutes": ambient_row["ambient_time_difference_minutes"],
                "ambient_matching_method": ambient_row["ambient_matching_method"],
                "ambient_qa_status": ambient_row["ambient_qa_status"],
                "delta_t_mean_c": round_float(float(stats["mean"]) - ambient_c) if stats["mean"] != "" else "",
                "delta_t_median_c": round_float(float(stats["median"]) - ambient_c) if stats["median"] != "" else "",
                "part_c_qa_status": record.get("part_c_qa_status", ""),
                "part_d_qa_status": record.get("part_d_qa_status", ""),
                "provisional_result_flag": 1,
                "provisional_result_note": PROVISIONAL_NOTICE,
                "analysis_valid": analysis_valid,
                "exclusion_reason": "; ".join(reasons),
                "qa_warning_flag": qa_warning_flag(record.get("part_c_qa_status", ""), record.get("part_d_qa_status", ""), ambient_row["ambient_qa_status"]),
            }
            rows.append(row)
            if not analysis_valid:
                audit_rows.append(
                    {
                        "observation_id": observation_id,
                        "analysis_variant": variant,
                        "image_id": image_id,
                        "cell_id": cell["global_cell_id"],
                        "exclusion_reason": row["exclusion_reason"],
                        "total_mapped_pixel_count": mapped_count,
                        "valid_temperature_pixel_count": valid_count,
                        "valid_temperature_coverage_fraction": row["valid_temperature_coverage_fraction"],
                    }
                )

    df = pd.DataFrame(rows)
    audit = pd.DataFrame(audit_rows)
    stats = {
        "variant": variant,
        "observation_count": len(df),
        "analysis_valid_count": int(df["analysis_valid"].sum()) if not df.empty else 0,
        "audit_count": len(audit),
        "mapping_stats": mapping_stats,
    }
    return df, audit, stats


def validate_dataset(df: pd.DataFrame) -> list[str]:
    problems: list[str] = []
    if df.duplicated(["image_id", "cell_id", "analysis_variant"]).any():
        problems.append("duplicate image_id + cell_id + analysis_variant rows found")
    numeric = df.loc[df["delta_t_mean_c"].astype(str).str.strip().ne("")]
    if not numeric.empty:
        lhs = numeric["delta_t_mean_c"].astype(float)
        rhs = numeric["mean_surface_temperature_c"].astype(float) - numeric["ambient_temperature_c"].astype(float)
        if not np.allclose(lhs, rhs, atol=1e-6):
            problems.append("delta_t_mean_c does not equal mean_surface_temperature_c - ambient_temperature_c")
    if (df["total_mapped_pixel_count"].astype(int) < 0).any():
        problems.append("negative mapped pixel count found")
    if (df["valid_temperature_pixel_count"].astype(int) < 0).any():
        problems.append("negative valid temperature pixel count found")
    return problems


def write_summary(stats: list[dict[str, Any]], validation_problems: list[str], min_valid_coverage: float) -> None:
    lines = [
        "# Part E Cell-Level Delta-T Dataset Build Summary",
        "",
        f"**Provisional-result rule:** {PROVISIONAL_NOTICE}",
        "",
        f"- Minimum valid temperature coverage fraction: {min_valid_coverage}",
        "",
        "## Variants Built",
        "",
    ]
    for item in stats:
        lines.extend(
            [
                f"- `{item['variant']}`: observations={item['observation_count']}, analysis_valid={item['analysis_valid_count']}, audit_exclusions={item['audit_count']}",
            ]
        )
    lines.extend(["", "## Validation", ""])
    if validation_problems:
        lines.extend(f"- FAIL: {problem}" for problem in validation_problems)
    else:
        lines.append("- PASS: no duplicate primary keys, non-negative counts, and delta-T arithmetic checks passed.")
    lines.extend(
        [
            "",
            "## Outputs",
            "",
            f"- Main all-finite cell dataset: `{relative_posix(CELL_OUTPUT)}`",
            f"- Cell exclusion audit: `{relative_posix(CELL_AUDIT_OUTPUT)}`",
        ]
    )
    write_markdown(BUILD_SUMMARY_MD, lines)


def main() -> int:
    args = parse_args()
    records = load_image_records()
    try:
        ambient = validate_ambient_manifest(records["image_id"].astype(str).tolist(), args.ambient_manifest)
    except AmbientInputError as exc:
        print(f"Ambient input not ready: {exc}", file=sys.stderr)
        print("Run scripts\\part_e\\00_create_ambient_temperature_manifest_template.py and fill the manifest.", file=sys.stderr)
        return 2

    grid = load_thermal_grid_cells()
    footprints = load_footprints()
    class_names = load_class_mapping()

    stats: list[dict[str, Any]] = []
    validation_problems: list[str] = []
    main_df, main_audit, main_stats = build_variant(
        records,
        ambient,
        grid,
        footprints,
        class_names,
        args.min_valid_coverage,
        None,
    )
    write_csv(CELL_OUTPUT, main_df)
    write_csv(CELL_AUDIT_OUTPUT, main_audit)
    stats.append(main_stats)
    validation_problems.extend(validate_dataset(main_df))

    if args.sensitivity_exclude_below_c is not None:
        sensitivity_df, sensitivity_audit, sensitivity_stats = build_variant(
            records,
            ambient,
            grid,
            footprints,
            class_names,
            args.min_valid_coverage,
            args.sensitivity_exclude_below_c,
        )
        sensitivity_path = sensitivity_output_path(args.sensitivity_exclude_below_c)
        audit_path = PART_E_TABLE_DIR / f"{safe_name(sensitivity_path.stem)}_exclusion_audit.csv"
        write_csv(sensitivity_path, sensitivity_df)
        write_csv(audit_path, sensitivity_audit)
        stats.append(sensitivity_stats)
        validation_problems.extend(validate_dataset(sensitivity_df))

    write_summary(stats, validation_problems, args.min_valid_coverage)
    print(f"Cell observations: {len(main_df)}")
    print(f"Analysis-valid observations: {int(main_df['analysis_valid'].sum())}")
    print(f"Output: {relative_posix(CELL_OUTPUT)}")
    return 1 if validation_problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
