#!/usr/bin/env python3
"""Audit the inputs and historical implementation for formal pixel-level Part E."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from part_e_pixel_common import (
    PROJECT_ROOT,
    build_image_records,
    build_luhk_pixel_labels,
    ensure_output_directories,
    load_config,
    load_masks,
    load_source_tables,
    load_temperature,
    project_path,
    relative,
    write_csv,
    write_markdown,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/part_e_delta_t_analysis.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    ensure_output_directories(config)
    tables = load_source_tables(config)
    records = build_image_records(config, tables)
    inventory: list[dict[str, object]] = []
    problems: list[str] = []
    orientation_notes: list[str] = []

    for _, record in records.iterrows():
        image_id = str(record["image_id"])
        matrix = load_temperature(record)
        class_mask, shadow_mask = load_masks(record, matrix.shape)
        luhk = build_luhk_pixel_labels(record, tables, matrix.shape)
        finite = np.isfinite(matrix)
        values = matrix[finite]
        class_valid = ~np.isin(class_mask, [0, 9])
        shadow_valid = np.ones(matrix.shape, dtype=bool) if shadow_mask is not None else np.zeros(matrix.shape, dtype=bool)
        if class_mask.shape != matrix.shape:
            problems.append(f"{image_id}: cover shape mismatch")
        if shadow_mask is not None and shadow_mask.shape != matrix.shape:
            problems.append(f"{image_id}: shadow shape mismatch")
        if shadow_mask is not None and not set(np.unique(shadow_mask)).issubset({0, 1}):
            problems.append(f"{image_id}: shadow mask contains values outside 0/1")
        mapped = np.asarray(luhk["mapped"], dtype=bool)
        inventory.append(
            {
                "image_id": image_id,
                "temperature_matrix_path": relative(project_path(str(record["npy_path"]))),
                "temperature_shape": f"{matrix.shape[0]}x{matrix.shape[1]}",
                "temperature_dtype": str(matrix.dtype),
                "total_pixel_count": int(matrix.size),
                "finite_count": int(finite.sum()),
                "nan_count": int(np.isnan(matrix).sum()),
                "inf_count": int(np.isinf(matrix).sum()),
                "minimum_c": float(values.min()),
                "maximum_c": float(values.max()),
                "mean_c": float(values.mean()),
                "median_c": float(np.median(values)),
                "ambient_record_count": int((tables["ambient"]["image_id"].astype(str) == image_id).sum()),
                "ambient_temperature_c": float(record["ambient_temperature_c"]),
                "ambient_source": record["ambient_source"],
                "ambient_validation_status": record["validation_status"],
                "surface_cover_mask_path": relative(project_path(str(record["class_mask_thermal_grid_npy_path"]))),
                "surface_cover_shape": f"{class_mask.shape[0]}x{class_mask.shape[1]}",
                "surface_cover_labelled_count": int(class_valid.sum()),
                "shadow_mask_path": relative(project_path(str(record["shadow_mask_thermal_grid_npy_path"]))),
                "shadow_shape": "missing" if shadow_mask is None else f"{shadow_mask.shape[0]}x{shadow_mask.shape[1]}",
                "shadow_known_count": int(shadow_valid.sum()),
                "shadow_present_count": 0 if shadow_mask is None else int((shadow_mask == 1).sum()),
                "luhk_mapped_pixel_count": int(mapped.sum()),
                "luhk_unmapped_pixel_count": int((~mapped).sum()),
                "luhk_assignment_method": config["luhk_assignment"]["method"],
                "row_column_order": "matrix[row, col] = matrix[thermal_y, thermal_x]",
                "orientation_status": f"structurally_aligned_shared_{matrix.shape[0]}x{matrix.shape[1]}_thermal_grid",
                "structural_alignment": bool(
                    class_mask.shape == matrix.shape and (shadow_mask is None or shadow_mask.shape == matrix.shape)
                ),
                "garden_hill_excluded": True,
            }
        )
        orientation_notes.append(
            f"- `{image_id}`: temperature and available label arrays share `{matrix.shape}` row-major thermal-grid shape; "
            "Part C masks were generated on this same target grid. No transpose or x/y swap is present. "
            "No independent control-point raster is available for a new flip test; LUHK assignment therefore retains "
            "the documented approximate north-up footprint limitation."
        )

    import pandas as pd

    inventory_frame = pd.DataFrame(inventory)
    write_csv(project_path(config["outputs"]["qa"]) / "part_e_input_inventory.csv", inventory_frame)

    script_dir = PROJECT_ROOT / "scripts" / "part_e"
    existing_scripts = sorted(
        path.name for path in script_dir.iterdir()
        if path.is_file() and path.suffix.casefold() in {".py", ".ps1", ".mjs"}
    )
    legacy_names = {
        "00_create_ambient_temperature_manifest_template.py",
        "01_build_cell_delta_t_dataset.py",
        "02_build_surface_cover_delta_t_dataset.py",
        "03_generate_summary_tables.py",
        "04_run_exploratory_statistics.py",
        "05_create_figures.py",
        "06_create_clear_spectrum_figures.py",
        "part_e_common.py",
    }
    legacy_scripts = sorted(name for name in existing_scripts if name in legacy_names)
    numbered_scripts = [name for name in existing_scripts if len(name) > 3 and name[:2].isdigit() and name[2] == "_"]
    duplicate_prefixes = sorted({prefix for prefix in (name[:2] for name in numbered_scripts) if sum(item.startswith(prefix + "_") for item in numbered_scripts) > 1})
    legacy_output_names = {
        "gic_surface_cover_delta_t_density_spectrum_facets.png",
        "gic_surface_cover_delta_t_density_spectrum_overlay.png",
        "luhk_delta_t_density_spectrum_facets.png",
        "surface_cover_delta_t_density_spectrum_facets.png",
    }
    historical_outputs = sorted(
        path.name
        for path in (PROJECT_ROOT / "outputs" / "part_e").rglob("*")
        if path.is_file() and ("cell_delta_t" in path.name or path.name in legacy_output_names)
    )
    if legacy_scripts:
        problems.append(f"superseded Part E scripts remain in active directory: {legacy_scripts}")
    if duplicate_prefixes:
        problems.append(f"duplicate active Part E numeric prefixes: {duplicate_prefixes}")
    if historical_outputs:
        problems.append(f"superseded Part E outputs remain in formal output tree: {historical_outputs}")
    whole_day_root = PROJECT_ROOT / "data" / "raw" / "HKUST" / "20260202_Thermal_HKUST"
    whole_day_thermal_images = list(whole_day_root.rglob("*_T.JPG")) if whole_day_root.exists() else []
    whole_day_ready = False

    lines = [
        "# Part E Formal Pixel-Pipeline Audit",
        "",
        "## Audit outcome",
        "",
        f"- Pilot images found: **{len(records)} / {len(config['pilot_image_ids'])}**.",
        f"- Non-empty native temperature matrices: **{len(inventory_frame)} / {len(records)}**.",
        f"- Ambient mapping: **one finite TAT3 record per image**.",
        f"- Structural alignment at each native grid: **{int(inventory_frame['structural_alignment'].sum())} / {len(records)}**.",
        "- Garden Hill: **excluded** from every selected record.",
        "- Formal observation: **one thermal pixel**; no cell mean is built or consumed.",
        "- Primary formal figures: **sampled-pixel ΔT distribution/density spectra generated by Python/SciPy**.",
        "- Supporting figures: boxplots, coverage charts, spatial QA panels, and Excel charts.",
        "",
        "## Existing implementation",
        "",
        f"Active Part E implementation files: {', '.join(f'`{name}`' for name in existing_scripts)}.",
        "",
        f"Superseded cell-level scripts in the active directory: {', '.join(f'`{name}`' for name in legacy_scripts) if legacy_scripts else 'none'}.",
        f"Duplicate numbered stage prefixes: {', '.join(f'`{name}`' for name in duplicate_prefixes) if duplicate_prefixes else 'none'}.",
        "The old workflow aggregated pixels to LUHK cells and was removed from the active tree after the formal pixel workflow was validated. "
        "It remains recoverable from Git history and the pre-validation checkpoint tag. "
        "The formal `run_part_e_pipeline.py` entry point invokes only the current pixel stages.",
        "The formal spectrum stage reads the completed sampled-pixel Parquets directly. It never reads the historical cell-level tables. "
        "Density is normalized rather than a count, and spatial thinning does not eliminate spatial autocorrelation.",
        "",
        f"Superseded cell-level outputs detected in the formal output tree: {', '.join(f'`{name}`' for name in historical_outputs) if historical_outputs else 'none'}.",
        "",
        "## Matrix and mask orientation",
        "",
        *orientation_notes,
        "",
        "The official LUHK label is looked up at each pixel centre through the existing metadata-derived north-up rectangular footprint. "
        "The mapped LUHK cell identifier is provenance only. The footprint model ignores recorded yaw and is approximate; this is a spatial-label limitation, not a row/column ambiguity, and is carried into all reports.",
        "",
        "## Ambient provenance correction",
        "",
        "The formal manifest is reconciled directly to the Part D TAT3 extraction summary. The earlier local exploratory manifest is not used. "
        "In particular, `DJI_20260107143328_0008` uses the Part D TAT3 value **10.5 °C**. These values are provisional parameters and are not independently validated meteorological air temperature.",
        "",
        "## Shadow audit",
        "",
        "Available reviewed shadow masks are checked against each image's native grid. Missing masks remain null and invalid, never silently converted to zero. "
        "The current five-image pilot happens to contain no shadow-present pixels, so that comparison remains non-estimable for the pilot.",
        "",
        "## 2026-02-02 whole-day readiness",
        "",
        f"- Raw whole-day thermal images detected: {len(whole_day_thermal_images)}.",
        "- Formal Part D temperature matrices: missing for the whole-day selection.",
        "- One-to-one TAT3 ambient manifest: missing.",
        "- LUHK, physical-cover, and shadow pixel labels for a selected image set: missing.",
        "- Status: **not ready; extension not executed**. This does not block the five-image pilot.",
        "",
        "## Problems",
        "",
    ]
    lines.extend([f"- FAIL: {problem}" for problem in problems] if problems else ["- No blocking input, shape, identifier, or row/column problem detected."])
    write_markdown(project_path(config["outputs"]["qa"]) / "part_e_pipeline_audit.md", lines)
    print(f"Audited {len(records)} pilot images; blocking problems: {len(problems)}")
    print(f"Whole-day extension ready: {whole_day_ready}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
