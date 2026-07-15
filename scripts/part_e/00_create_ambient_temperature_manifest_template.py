#!/usr/bin/env python3
"""Create the Part E ambient-temperature input template and readiness report."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from part_e.part_e_common import (  # noqa: E402
    AMBIENT_COLUMNS,
    AMBIENT_MANIFEST,
    AMBIENT_TEMPLATE,
    PART_D_TAT3_PILOT_PARAMS_CSV,
    PART_E_SUMMARY_DIR,
    PART_E_TABLE_DIR,
    PROVISIONAL_NOTICE,
    relative_posix,
    load_ambient_manifest,
    load_image_records,
    write_csv,
    write_markdown,
)


INPUT_INVENTORY_CSV = PART_E_TABLE_DIR / "part_e_input_path_inventory.csv"
MISSING_AMBIENT_CSV = PART_E_TABLE_DIR / "part_e_missing_ambient_temperature_inputs.csv"
READINESS_MD = PART_E_SUMMARY_DIR / "part_e_ambient_temperature_readiness_report.md"
ROUND1_SUMMARY_MD = PART_E_SUMMARY_DIR / "part_e_round1_delta_t_analysis_summary.md"


def build_template(records: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in records.sort_values("image_id").iterrows():
        ambient = str(row.get("ambient_temperature_c", "")).strip()
        has_tat3_ambient = pd.to_numeric(pd.Series([ambient]), errors="coerce").notna().iloc[0]
        rows.append(
            {
                "image_id": row["image_id"],
                "acquisition_datetime": row.get("acquisition_datetime", ""),
                "ambient_temperature_c": ambient if has_tat3_ambient else "",
                "ambient_source": "tat3_exported_report_parameter" if has_tat3_ambient else "",
                "ambient_source_id": relative_posix(PART_D_TAT3_PILOT_PARAMS_CSV) if has_tat3_ambient else "",
                "ambient_observation_datetime": row.get("tat3_report_capture_datetime", "") if has_tat3_ambient else "",
                "ambient_time_difference_minutes": 0 if has_tat3_ambient else "",
                "ambient_matching_method": "same_image_tat3_parameter" if has_tat3_ambient else "not_selected_missing_source",
                "ambient_qa_status": "tat3_parameter_ingested" if has_tat3_ambient else "missing_external_record",
                "ambient_notes": (
                    "Seeded from Part D TAT3 parameter ingest. Replace only with a documented project-approved source."
                    if has_tat3_ambient
                    else "Fill from a documented external or recorded ambient-temperature source. Do not infer from the thermal matrix."
                ),
            }
        )
    return pd.DataFrame(rows, columns=AMBIENT_COLUMNS)


def input_inventory(records: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "pair_id",
        "image_id",
        "flight_id",
        "acquisition_datetime",
        "t_path",
        "npy_path",
        "class_mask_thermal_grid_npy_path",
        "shadow_mask_thermal_grid_npy_path",
        "metadata_json_path",
        "part_c_qa_status",
        "part_d_qa_status",
    ]
    return records[columns].copy()


def existing_ambient_note() -> str:
    try:
        ambient = load_ambient_manifest(AMBIENT_MANIFEST)
    except Exception:
        return "No existing standardized Part E ambient manifest was ready."
    populated = ambient["ambient_temperature_c"].astype(str).str.strip().ne("").sum()
    return f"Existing standardized Part E ambient manifest rows found: {len(ambient)}; populated ambient values: {populated}."


def write_reports(records: pd.DataFrame, template: pd.DataFrame) -> None:
    inventory = input_inventory(records)
    write_csv(INPUT_INVENTORY_CSV, inventory)
    write_csv(MISSING_AMBIENT_CSV, template)

    pilot_ids = ", ".join(records["image_id"].astype(str).tolist())
    try:
        ambient_manifest = load_ambient_manifest(AMBIENT_MANIFEST)
        numeric_count = pd.to_numeric(ambient_manifest["ambient_temperature_c"], errors="coerce").notna().sum()
        ready_for_provisional = numeric_count == len(records)
    except Exception:
        numeric_count = 0
        ready_for_provisional = False
    status_lines = (
        [
            "- Ambient-temperature input is ready for a provisional user-provided Part E run.",
            "- The five pilot images have one numeric image-level ambient scalar each.",
            "- The values are sourced from the Part D TAT3 parameter ingest; replace only if a documented project-approved ambient source supersedes them.",
        ]
        if ready_for_provisional
        else [
            "- Ambient-temperature input is not ready for delta-T calculation.",
            f"- Seed values should come from `{relative_posix(PART_D_TAT3_PILOT_PARAMS_CSV)}` or another explicitly approved source.",
            "- No placeholder numerical ambient temperatures should be written.",
        ]
    )
    readiness_lines = [
        "# Part E Ambient-Temperature Readiness Report",
        "",
        f"**Provisional-result rule:** {PROVISIONAL_NOTICE}",
        "",
        "## Status",
        "",
        *status_lines,
        "- The deprecated Part D placeholder SDK setting `ambient_temperature_c = 25 C` is not used by the active extraction workflow.",
        f"- {existing_ambient_note()}",
        f"- Numeric ambient values currently present: {numeric_count}/{len(records)}.",
        "",
        "## Pilot Images",
        "",
        f"- Images requiring one documented ambient-temperature value each: {pilot_ids}",
        "",
        "## Files Created",
        "",
        f"- Ambient input template: `{relative_posix(AMBIENT_TEMPLATE)}`",
        f"- Standardized working manifest: `{relative_posix(AMBIENT_MANIFEST)}`",
        f"- Input path inventory: `{relative_posix(INPUT_INVENTORY_CSV)}`",
        f"- Missing ambient input table: `{relative_posix(MISSING_AMBIENT_CSV)}`",
        "",
        "## Required Ambient Columns",
        "",
    ]
    readiness_lines.extend(f"- `{column}`" for column in AMBIENT_COLUMNS)
    readiness_lines.extend(
        [
            "",
            "## Rule Before Running Delta-T",
            "",
            "Each pilot image must have exactly one documented, numeric `ambient_temperature_c` with a non-missing `ambient_qa_status`, source, source ID if available, observation datetime, time difference, and matching method.",
            "",
            "Do not calculate final Part E delta-T outputs until those five values are supplied.",
        ]
    )
    write_markdown(READINESS_MD, readiness_lines)

    cell_dataset = PART_E_TABLE_DIR / "part_e_cell_delta_t_observations_all_finite.csv"
    cover_dataset = PART_E_TABLE_DIR / "part_e_surface_cover_delta_t_observations_all_finite.csv"
    if ready_for_provisional and cell_dataset.is_file() and cover_dataset.is_file():
        return

    summary_lines = [
        "# Part E Round 1 Provisional Delta-T Analysis Summary",
        "",
        f"> {PROVISIONAL_NOTICE}",
        "",
        "## Current Outcome",
        "",
        "Part E Round 1 code and input templates have been prepared. Numeric delta-T datasets and figures are generated only after the local ambient manifest contains one documented image-level ambient value for every pilot image.",
        "",
        "## Delta-T Formula",
        "",
        "`delta_t_c(i, c) = mean_surface_temperature_c(i, c) - ambient_temperature_c(i)`",
        "",
        "`delta_t_c(i, c, s) = mean_surface_temperature_c(i, c, s) - ambient_temperature_c(i)`",
        "",
        "Thermal pixels are first aggregated to LUHK-aligned 10 m cells, or to cell-by-physical-surface-cover observations. Pixels are not treated as independent statistical observations.",
        "",
        "## Ambient Matching Source And Method",
        "",
        f"Current seed source: `{relative_posix(PART_D_TAT3_PILOT_PARAMS_CSV)}`. Replace only if a documented project-approved ambient source supersedes the TAT3 parameter values.",
        "",
        "## Pilot Input Inventory",
        "",
        f"- Number of pilot thermal images: {len(records)}",
        f"- Input inventory: `{relative_posix(INPUT_INVENTORY_CSV)}`",
        f"- Ambient readiness report: `{relative_posix(READINESS_MD)}`",
        "",
        "## Results Not Yet Generated",
        "",
        "- Cell-level delta-T observations: not generated.",
        "- Cell-by-surface-cover delta-T observations: not generated.",
        "- LUHK, surface-cover, and image-level summaries: not generated.",
        "- Exploratory statistical tests: not run.",
        "- Part E figures: not generated.",
        "- Sensitivity analysis: not generated.",
        "",
        "## Unresolved Limitations",
        "",
        "- Apparent-temperature extrema still require physical plausibility review.",
        "- Ambient-temperature source choice should be documented before final reporting.",
        "- Shadow masks are structurally present, but the current five pilot masks contain no `shadow_flag = 1` pixels.",
        "",
        "## Reproducibility Commands",
        "",
        "```powershell",
        ".\\.venv\\Scripts\\python.exe scripts\\part_e\\00_create_ambient_temperature_manifest_template.py",
        ".\\.venv\\Scripts\\python.exe scripts\\part_e\\01_build_cell_delta_t_dataset.py",
        ".\\.venv\\Scripts\\python.exe scripts\\part_e\\02_build_surface_cover_delta_t_dataset.py",
        ".\\.venv\\Scripts\\python.exe scripts\\part_e\\03_generate_summary_tables.py",
        ".\\.venv\\Scripts\\python.exe scripts\\part_e\\04_run_exploratory_statistics.py",
        ".\\.venv\\Scripts\\python.exe scripts\\part_e\\05_create_figures.py",
        "```",
        "",
        "The dataset, summary, statistics, and figure commands intentionally stop until the ambient manifest contains exactly one documented ambient-temperature value per image.",
        "",
        "## Recommended Professor-Report Interpretation",
        "",
        "Report that Part E has been reframed as provisional pilot delta-T statistical analysis and visualization, and that any numeric delta-T findings must cite the selected ambient-temperature source and remaining apparent-temperature plausibility limitations.",
    ]
    write_markdown(ROUND1_SUMMARY_MD, summary_lines)


def main() -> int:
    records = load_image_records()
    template = build_template(records)
    AMBIENT_TEMPLATE.parent.mkdir(parents=True, exist_ok=True)
    template.to_csv(AMBIENT_TEMPLATE, index=False)
    if not AMBIENT_MANIFEST.exists():
        template.to_csv(AMBIENT_MANIFEST, index=False)
    write_reports(records, template)
    print(f"Pilot images: {len(records)}")
    print(f"Ambient template: {relative_posix(AMBIENT_TEMPLATE)}")
    print(f"Working ambient manifest: {relative_posix(AMBIENT_MANIFEST)}")
    print(f"Readiness report: {relative_posix(READINESS_MD)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
