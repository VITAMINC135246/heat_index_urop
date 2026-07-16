#!/usr/bin/env python3
"""Author the main Part E statistical workbook with tables, formulas, and charts."""

from __future__ import annotations

import argparse
import platform
from pathlib import Path

import pandas as pd

from excel_workbook_common import run_builder
from part_e_pixel_common import SAMPLE_FILES, ensure_output_directories, git_info, load_config, project_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/part_e_delta_t_analysis.json")
    return parser.parse_args()


def write(frame: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    ensure_output_directories(config)
    source = project_path(config["outputs"]["excel_source_directory"])
    tables = project_path(config["outputs"]["tables"])
    qa = project_path(config["outputs"]["qa"])
    samples = project_path(config["outputs"]["sample_directory"])
    preview_dir = project_path(config["outputs"]["part_e_root"]) / "workbook_previews" / "main"
    payload_dir = project_path(config["outputs"]["part_e_root"]) / "workbook_previews" / "payloads"
    git = git_info()

    readme = pd.DataFrame([
        ["Workbook", "Part E Pixel Statistical Analysis"], ["Formal observation", "One original thermal pixel"],
        ["Formula", "delta_t_c = temperature_c - ambient_temperature_c"], ["Full-population role", "Counts and descriptive summaries use all accepted finite pixels"],
        ["Sample role", "Plots and exploratory tests use spatially thinned original pixels; spatial autocorrelation remains"], ["Sampling method", config["sampling"]["method"]],
        ["Primary seed", config["sampling"]["primary_seed"]], ["Spatial tile size", config["sampling"]["spatial_tile_size_px"]],
        ["Cell aggregation", "Prohibited; luhk_cell_id is provenance only"], ["Inference", "P-values are exploratory because pixels remain spatially dependent"],
        ["Scope", "Five HKUST pilot images; no Hong Kong-wide generalisation"], ["Prediction", config["prediction_status"]],
    ], columns=["Item", "Detail"])
    dictionary = pd.DataFrame([
        ["pixel_uid", "Unique image + thermal row + thermal column identifier", "text"], ["image_id", "Pilot thermal image identifier", "text"],
        ["thermal_row", "Zero-based thermal raster row; increases downward", "pixel"], ["thermal_col", "Zero-based thermal raster column; increases rightward", "pixel"],
        ["pixel_x", "Alias of thermal_col", "pixel"], ["pixel_y", "Alias of thermal_row", "pixel"],
        ["temperature_c", "Original Part D TAT3-parameter surface temperature", "°C"], ["ambient_temperature_c", "Per-image TAT3 ambient parameter", "°C"],
        ["delta_t_c", "temperature_c - ambient_temperature_c calculated per pixel", "°C"], ["pixel_accepted", "True exactly when temperature_is_finite", "boolean"],
        ["luhk_cell_id", "Official 10 m grid cell provenance; never an analysis observation", "text"], ["luhk_class_code", "Official LUHK raw class code at pixel centre", "code"],
        ["luhk_class_name", "Broad LUHK class label at the pixel centre", "text"], ["luhk_label_valid", "Pixel mapped to exactly one LUHK cell", "boolean"],
        ["surface_cover_class", "Reviewed physical surface-cover label", "text"], ["surface_cover_valid", "Reviewed physical cover eligible for class analysis", "boolean"],
        ["shadow_flag", "Separate reviewed shadow flag; 0 or 1, null if missing", "flag"], ["shadow_valid", "Whether shadow information is known", "boolean"],
        ["tile_row / tile_col", "8 px spatial thinning strata; never averaged", "sampling index"], ["sampling_seed", "Deterministic pseudorandom seed", "integer"],
        ["source_population_count", "Full eligible pixels in the analysis group", "pixels"],
    ], columns=["Field", "Definition", "Unit_or_type"])
    provenance = pd.DataFrame([
        ["Git branch at generation", git["branch"]], ["Git commit at generation", git["commit"]],
        ["Configuration", "config/part_e_delta_t_analysis.json"], ["Canonical source", config["outputs"]["canonical_parquet"]],
        ["Ambient source", "TAT3"], ["Ambient validation", "provisional; not independently validated meteorological air temperature"],
        ["LUHK assignment", config["luhk_assignment"]["method"]], ["LUHK spatial limitation", "Approximate north-up metadata footprint; yaw not applied"],
        ["Workbook authoring", "@oai/artifact-tool followed by Microsoft Excel COM"], ["Python", platform.python_version()],
        ["Analysis ToolPak", "installed but not enabled; scipy/statsmodels are the formal test source"],
    ], columns=["Provenance_item", "Value"])
    sampling_rules = pd.DataFrame([[key, value] for key, value in config["sampling"].items() if key != "secondary_seeds"] + [["secondary_seeds", ", ".join(map(str, config["sampling"]["secondary_seeds"]))]], columns=["Rule", "Value"])

    write(readme, source / "main_readme.csv"); write(dictionary, source / "data_dictionary.csv")
    write(provenance, source / "provenance.csv"); write(sampling_rules, source / "sampling_rules.csv")

    cover = pd.read_csv(tables / "part_e_delta_t_by_surface_cover_pixels.csv")
    coverage = pd.read_csv(tables / "part_e_pixel_sample_coverage.csv").groupby("analysis_family", sort=True).agg(sampled_pixel_count=("sampled_pixel_count", "sum")).reset_index()
    size = max(len(cover), len(coverage))
    figure = pd.DataFrame(index=range(size))
    figure["surface_cover_class"] = cover["surface_cover_class"]
    figure["mean_full_delta_t_c"] = cover["mean_full"]
    figure["median_full_delta_t_c"] = cover["median_full"]
    figure["separator"] = ""
    figure["analysis_family"] = coverage["analysis_family"]
    figure["sampled_pixel_count"] = coverage["sampled_pixel_count"]
    write(figure, source / "figure_data.csv")

    sample_placeholders: dict[str, Path] = {}
    for family, base in SAMPLE_FILES.items():
        actual = samples / f"{base}.csv"
        headers = pd.read_csv(actual, nrows=0).columns.tolist()
        placeholder = pd.DataFrame([{column: ("Full sampled-pixel rows are inserted by the Excel COM stage" if column == "pixel_uid" else "") for column in headers}])
        sample_placeholders[family] = write(placeholder, source / f"{base}_placeholder.csv")

    specs = [
        ("README", source / "main_readme.csv", None), ("Data_Dictionary", source / "data_dictionary.csv", "tblDataDictionary"),
        ("Provenance", source / "provenance.csv", "tblProvenance"), ("Input_QA", qa / "part_e_input_inventory.csv", "tblInputQA"),
        ("Full_Pixel_Image_Summary", tables / "part_e_full_pixel_summary_by_image.csv", "tblFullPixelImageSummary"),
        ("Sampling_Rules", source / "sampling_rules.csv", "tblSamplingRules"), ("Sampling_Manifest", tables / "part_e_pixel_sampling_manifest.csv", "tblSamplingManifest"),
        ("Sample_LUHK", sample_placeholders["luhk"], "tblSampleLUHK"),
        ("Sample_Cover", sample_placeholders["surface_cover"], "tblSampleCover"),
        ("Sample_LUHK_Cover", sample_placeholders["luhk_surface_cover"], "tblSampleLUHKCover"),
        ("Sample_Cover_Shadow", sample_placeholders["surface_cover_shadow"], "tblSampleCoverShadow"),
        ("Sample_Image", sample_placeholders["image_comparison"], "tblSampleImage"),
        ("Full_Pixel_LUHK_Summary", tables / "part_e_delta_t_by_luhk_pixels.csv", "tblFullPixelLUHKSummary"),
        ("Full_Pixel_Cover_Summary", tables / "part_e_delta_t_by_surface_cover_pixels.csv", "tblFullPixelCoverSummary"),
        ("Full_Pixel_LUHK_x_Cover", tables / "part_e_delta_t_by_luhk_surface_cover_pixels.csv", "tblFullPixelLUHKCover"),
        ("Full_Pixel_Cover_x_Shadow", tables / "part_e_delta_t_by_surface_cover_shadow_pixels.csv", "tblFullPixelCoverShadow"),
        ("Statistical_Tests", tables / "part_e_pixel_statistical_tests.csv", "tblStatisticalTests"),
        ("Effect_Sizes", tables / "part_e_pixel_effect_sizes.csv", "tblEffectSizes"),
        ("Sampling_Stability", tables / "part_e_sampling_stability.csv", "tblSamplingStability"),
        ("Sample_Coverage", tables / "part_e_pixel_sample_coverage.csv", "tblSampleCoverage"),
        ("Figure_Data", source / "figure_data.csv", "tblFigureData"),
    ]
    payload = {
        "mode": "main",
        "output": str(project_path(config["outputs"]["excel"]) / "part_e_pixel_statistical_analysis.xlsx"),
        "preview_dir": str(preview_dir),
        "cover_chart_range": f"A1:C{len(cover) + 1}", "coverage_chart_range": f"E1:F{len(coverage) + 1}",
        "sheets": [{"name": name, "path": str(path), "tableName": table_name} for name, path, table_name in specs],
    }
    run_builder(payload, payload_dir / "main_workbook.json")
    print("Artifact-tool main workbook complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
