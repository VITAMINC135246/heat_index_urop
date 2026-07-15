#!/usr/bin/env python3
"""Build provisional cell-by-physical-surface-cover delta-T observations."""

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


COVER_OUTPUT = PART_E_TABLE_DIR / "part_e_surface_cover_delta_t_observations_all_finite.csv"
COVER_AUDIT_OUTPUT = PART_E_TABLE_DIR / "part_e_surface_cover_delta_t_exclusion_audit.csv"
BUILD_SUMMARY_MD = PART_E_SUMMARY_DIR / "part_e_surface_cover_delta_t_dataset_build_summary.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ambient-manifest", type=Path, default=AMBIENT_MANIFEST)
    parser.add_argument("--min-valid-pixels", type=int, default=30)
    parser.add_argument("--min-class-fraction", type=float, default=0.01)
    parser.add_argument("--sensitivity-exclude-below-c", type=float, default=None)
    return parser.parse_args()


def sensitivity_output_path(threshold: float) -> Path:
    threshold_name = str(threshold).replace("-", "minus_").replace(".", "p")
    return PART_E_TABLE_DIR / f"part_e_surface_cover_delta_t_observations_sensitivity_excluding_below_{threshold_name}c.csv"


def analysis_mask(temps: np.ndarray, threshold: float | None) -> np.ndarray:
    mask = np.isfinite(temps)
    if threshold is not None:
        mask &= temps >= threshold
    return mask


def valid_classified_mask(pixel_mask: np.ndarray, class_mask: np.ndarray, class_names: dict[int, str]) -> np.ndarray:
    result = np.zeros(pixel_mask.shape, dtype=bool)
    for class_id in np.unique(class_mask[pixel_mask]).tolist():
        if is_analysis_cover_class(int(class_id), class_names):
            result |= pixel_mask & (class_mask == int(class_id))
    return result


def build_variant(
    records: pd.DataFrame,
    ambient: pd.DataFrame,
    grid: pd.DataFrame,
    footprints: pd.DataFrame,
    class_names: dict[int, str],
    min_valid_pixels: int,
    min_class_fraction: float,
    sensitivity_threshold: float | None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    ambient_by_image = ambient.set_index("image_id").to_dict(orient="index")
    rows: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    variant = "all_finite" if sensitivity_threshold is None else f"sensitivity_exclude_below_{sensitivity_threshold:g}c"

    for _, record in records.sort_values("image_id").iterrows():
        image_id = str(record["image_id"])
        temps = load_temperature_matrix(record)
        class_mask, shadow_mask = load_part_c_masks(record)
        mapping = build_pixel_cell_mapping(grid, footprints, str(record["pair_id"]), temps.shape)
        valid_temp = analysis_mask(temps, sensitivity_threshold)
        ambient_row = ambient_by_image[image_id]
        ambient_c = float(ambient_row["ambient_temperature_c"])

        for cell_index, cell in mapping.cells.iterrows():
            cell_pixels = mapping.cell_index == cell_index
            if int(cell_pixels.sum()) == 0:
                continue
            valid_classified = valid_classified_mask(cell_pixels, class_mask, class_names)
            valid_classified_count = int(valid_classified.sum())
            for class_id_raw in sorted(np.unique(class_mask[cell_pixels]).tolist()):
                class_id = int(class_id_raw)
                cover_pixels = cell_pixels & (class_mask == class_id)
                class_pixel_count = int(cover_pixels.sum())
                if class_pixel_count == 0:
                    continue
                cover_valid_temp = cover_pixels & valid_temp
                values = temps[cover_valid_temp]
                valid_temp_count = int(cover_valid_temp.sum())
                finite_cover = cover_pixels & np.isfinite(temps)
                stats = values_stats(values)
                class_fraction = class_pixel_count / valid_classified_count if valid_classified_count else 0.0
                temp_coverage = valid_temp_count / class_pixel_count if class_pixel_count else 0.0
                below0_count = int((finite_cover & (temps < 0)).sum())
                below5_count = int((finite_cover & (temps < -5)).sum())
                below10_count = int((finite_cover & (temps < -10)).sum())
                shadow_fraction = float((shadow_mask[cover_pixels] == 1).mean()) if class_pixel_count else 0.0

                reasons: list[str] = []
                if not is_analysis_cover_class(class_id, class_names):
                    reasons.append("non_analysis_physical_surface_cover_class")
                if valid_temp_count == 0:
                    reasons.append("no_valid_temperature_pixels_after_variant_rule")
                if valid_temp_count < min_valid_pixels and class_fraction < min_class_fraction:
                    reasons.append("below_minimum_valid_pixels_and_class_fraction")
                analysis_valid = int(not reasons)
                observation_id = f"{image_id}__{cell['global_cell_id']}__cover_{class_id}"
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
                    "luhk_original_code": cell["luhk_raw_code"],
                    "luhk_original_class": cell["luhk_raw_code"],
                    "luhk_aggregated_class": cell["luhk_category_name"],
                    "physical_surface_cover_class_id": class_id,
                    "physical_surface_cover_class": class_name(class_id, class_names),
                    "class_pixel_count": class_pixel_count,
                    "valid_classified_pixel_count_in_cell": valid_classified_count,
                    "class_fraction_of_valid_classified_pixels": round_float(class_fraction),
                    "class_thermal_pixel_count": class_pixel_count,
                    "class_valid_temperature_count": valid_temp_count,
                    "class_temperature_coverage_fraction": round_float(temp_coverage),
                    "class_mean_surface_temperature_c": stats["mean"],
                    "class_median_surface_temperature_c": stats["median"],
                    "class_std_surface_temperature_c": stats["std"],
                    "class_min_surface_temperature_c": stats["min"],
                    "class_max_surface_temperature_c": stats["max"],
                    "class_below_0_c_pixel_count": below0_count,
                    "class_below_0_c_pixel_fraction": round_float(below0_count / class_pixel_count),
                    "class_below_minus_5_c_pixel_count": below5_count,
                    "class_below_minus_5_c_pixel_fraction": round_float(below5_count / class_pixel_count),
                    "class_below_minus_10_c_pixel_count": below10_count,
                    "class_below_minus_10_c_pixel_fraction": round_float(below10_count / class_pixel_count),
                    "class_shadow_pixel_count": int((shadow_mask[cover_pixels] == 1).sum()),
                    "class_shadow_fraction": round_float(shadow_fraction),
                    "ambient_temperature_c": round_float(ambient_c),
                    "ambient_source": ambient_row["ambient_source"],
                    "ambient_source_id": ambient_row["ambient_source_id"],
                    "ambient_observation_datetime": ambient_row["ambient_observation_datetime"],
                    "ambient_time_difference_minutes": ambient_row["ambient_time_difference_minutes"],
                    "ambient_matching_method": ambient_row["ambient_matching_method"],
                    "ambient_qa_status": ambient_row["ambient_qa_status"],
                    "class_delta_t_mean_c": round_float(float(stats["mean"]) - ambient_c) if stats["mean"] != "" else "",
                    "class_delta_t_median_c": round_float(float(stats["median"]) - ambient_c) if stats["median"] != "" else "",
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
                            "physical_surface_cover_class_id": class_id,
                            "physical_surface_cover_class": row["physical_surface_cover_class"],
                            "exclusion_reason": row["exclusion_reason"],
                            "class_pixel_count": class_pixel_count,
                            "class_valid_temperature_count": valid_temp_count,
                            "class_fraction_of_valid_classified_pixels": row["class_fraction_of_valid_classified_pixels"],
                        }
                    )
    df = pd.DataFrame(rows)
    audit = pd.DataFrame(audit_rows)
    stats = {
        "variant": variant,
        "observation_count": len(df),
        "analysis_valid_count": int(df["analysis_valid"].sum()) if not df.empty else 0,
        "audit_count": len(audit),
    }
    return df, audit, stats


def validate_dataset(df: pd.DataFrame) -> list[str]:
    problems: list[str] = []
    if df.duplicated(["image_id", "cell_id", "physical_surface_cover_class_id", "analysis_variant"]).any():
        problems.append("duplicate image_id + cell_id + physical_surface_cover_class_id + analysis_variant rows found")
    if df["physical_surface_cover_class"].astype(str).str.casefold().eq("shadow").any():
        problems.append("shadow appears as a physical surface-cover class")
    numeric = df.loc[df["class_delta_t_mean_c"].astype(str).str.strip().ne("")]
    if not numeric.empty:
        lhs = numeric["class_delta_t_mean_c"].astype(float)
        rhs = numeric["class_mean_surface_temperature_c"].astype(float) - numeric["ambient_temperature_c"].astype(float)
        if not np.allclose(lhs, rhs, atol=1e-6):
            problems.append("class_delta_t_mean_c arithmetic check failed")
    return problems


def write_summary(stats: list[dict[str, Any]], validation_problems: list[str], min_pixels: int, min_fraction: float) -> None:
    lines = [
        "# Part E Cell-By-Surface-Cover Delta-T Dataset Build Summary",
        "",
        f"**Provisional-result rule:** {PROVISIONAL_NOTICE}",
        "",
        f"- Minimum valid class temperature pixels: {min_pixels}",
        f"- Minimum class fraction of valid classified pixels: {min_fraction}",
        "",
        "## Variants Built",
        "",
    ]
    for item in stats:
        lines.append(
            f"- `{item['variant']}`: observations={item['observation_count']}, analysis_valid={item['analysis_valid_count']}, audit_exclusions={item['audit_count']}"
        )
    lines.extend(["", "## Validation", ""])
    if validation_problems:
        lines.extend(f"- FAIL: {problem}" for problem in validation_problems)
    else:
        lines.append("- PASS: primary keys, taxonomy, and delta-T arithmetic checks passed.")
    lines.extend(
        [
            "",
            "## Outputs",
            "",
            f"- Main all-finite cell-cover dataset: `{relative_posix(COVER_OUTPUT)}`",
            f"- Cell-cover exclusion audit: `{relative_posix(COVER_AUDIT_OUTPUT)}`",
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
        args.min_valid_pixels,
        args.min_class_fraction,
        None,
    )
    write_csv(COVER_OUTPUT, main_df)
    write_csv(COVER_AUDIT_OUTPUT, main_audit)
    stats.append(main_stats)
    validation_problems.extend(validate_dataset(main_df))

    if args.sensitivity_exclude_below_c is not None:
        sensitivity_df, sensitivity_audit, sensitivity_stats = build_variant(
            records,
            ambient,
            grid,
            footprints,
            class_names,
            args.min_valid_pixels,
            args.min_class_fraction,
            args.sensitivity_exclude_below_c,
        )
        sensitivity_path = sensitivity_output_path(args.sensitivity_exclude_below_c)
        audit_path = PART_E_TABLE_DIR / f"{safe_name(sensitivity_path.stem)}_exclusion_audit.csv"
        write_csv(sensitivity_path, sensitivity_df)
        write_csv(audit_path, sensitivity_audit)
        stats.append(sensitivity_stats)
        validation_problems.extend(validate_dataset(sensitivity_df))

    write_summary(stats, validation_problems, args.min_valid_pixels, args.min_class_fraction)
    print(f"Cell-cover observations: {len(main_df)}")
    print(f"Analysis-valid observations: {int(main_df['analysis_valid'].sum())}")
    print(f"Output: {relative_posix(COVER_OUTPUT)}")
    return 1 if validation_problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
