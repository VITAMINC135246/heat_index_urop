#!/usr/bin/env python3
"""Generate the formal Part E spectrum-first statistical summary report."""

from __future__ import annotations

import argparse
from typing import Any

import pandas as pd

from part_e_pixel_common import load_config, project_path, write_markdown


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/part_e_delta_t_analysis.json")
    return parser.parse_args()


def fmt(value: Any, digits: int = 2) -> str:
    return "not available" if pd.isna(value) else f"{float(value):.{digits}f}"


def group_lines(summary: pd.DataFrame, family: str) -> list[str]:
    selected = summary.loc[summary["analysis_family"].eq(family)].copy()
    selected = selected.sort_values("median_sampled")
    lines: list[str] = []
    for row in selected.itertuples(index=False):
        status = ""
        if row.kde_status != "eligible":
            status = f" KDE status: {row.kde_status} ({row.eligibility_or_skipped_reason})."
        lines.append(
            f"- {row.display_name}: sampled/full n={int(row.n_pixels_sampled):,}/{int(row.n_pixels_full):,}; "
            f"images={int(row.n_images)}/{int(row.n_images_full)}; median={fmt(row.median_sampled)} °C; "
            f"mean={fmt(row.mean_sampled)} °C; Q25–Q75={fmt(row.q25_sampled)} to {fmt(row.q75_sampled)} °C; "
            f"Q05–Q95={fmt(row.q05_sampled)} to {fmt(row.q95_sampled)} °C.{status}"
        )
    return lines


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    tables = project_path(config["outputs"]["tables"])
    summary_path = tables / "part_e_pixel_delta_t_spectrum_summary.csv"
    if not summary_path.is_file():
        raise FileNotFoundError(f"Run the spectrum stage first: {summary_path}")
    summary = pd.read_csv(summary_path)
    stability = pd.read_csv(tables / "part_e_sampling_stability.csv")
    tests = pd.read_csv(tables / "part_e_pixel_statistical_tests.csv")
    effects = pd.read_csv(tables / "part_e_pixel_effect_sizes.csv")
    ambient = pd.read_csv(project_path(config["inputs"]["ambient_manifest"]))
    primary_seed = int(config["sampling"]["primary_seed"])
    overall = summary.loc[summary["analysis_family"].eq("overall")].iloc[0]

    stable_groups = stability.loc[stability["record_type"].eq("group")].copy()
    stability_lines: list[str] = []
    for (family, group_name), group in stable_groups.groupby(["analysis_family", "group_a"], sort=True):
        label = summary.loc[
            summary["analysis_family"].eq(family) & summary["group_name"].eq(group_name), "display_name"
        ]
        display = label.iloc[0] if not label.empty else group_name
        stability_lines.append(
            f"- {family} / {display}: sampled median range across {group['sampling_seed'].nunique()} seeds="
            f"{group['sampled_median_a'].min():.2f} to {group['sampled_median_a'].max():.2f} °C."
        )

    executed_tests = tests.loc[tests["interpretation_status"].ne("skipped")]
    skipped_tests = tests.loc[tests["interpretation_status"].eq("skipped")]
    lines = [
        "# Part E formal pixel-level ΔT spectrum and statistical summary",
        "",
        "> Provisional five-image HKUST pilot. Part D apparent-temperature radiometric plausibility review and the image-level TAT3 ambient parameters remain limitations; results do not generalize to all of Hong Kong.",
        "",
        "## Method and observation unit",
        "",
        "The formal observation is one original thermal pixel. For every accepted finite pixel:",
        "",
        "```text",
        "delta_t_c = temperature_c - ambient_temperature_c",
        "```",
        "",
        f"All {int(overall['n_pixels_full']):,} accepted finite pilot pixels remain in the canonical Parquet. Formal plots use dispersed individual pixels selected by `{config['sampling']['method']}` with primary seed {primary_seed}; neither 10 m LUHK cells nor 8 px sampling tiles are averaged. Spatial thinning does not remove spatial autocorrelation, so sampled pixels are not described as independent observations.",
        "",
        "Here, spectrum means the statistical distribution/density spectrum of pixel-level ΔT, not an electromagnetic reflectance or multispectral-band spectrum. Python/SciPy is the formal plotting engine; density curves use Scott's bandwidth rule, common comparison axes, and no extrapolation beyond each group's observed sampled range.",
        "",
        "## 1. Overall pixel ΔT spectrum",
        "",
        f"The overall image-stratified sample contains {int(overall['n_pixels_sampled']):,} pixels from {int(overall['n_images'])} images, representing {int(overall['n_pixels_full']):,} accepted finite pixels. Median ΔT is {fmt(overall['median_sampled'])} °C, mean is {fmt(overall['mean_sampled'])} °C, Q25–Q75 is {fmt(overall['q25_sampled'])} to {fmt(overall['q75_sampled'])} °C, and Q05–Q95 is {fmt(overall['q05_sampled'])} to {fmt(overall['q95_sampled'])} °C. Figure 00 should be used with the descriptive table; curve height is normalized density, not pixel count.",
        "",
        "## 2. LUHK spectra",
        "",
        *group_lines(summary, "luhk"),
        "",
        "LUHK class 51 has too few sampled pixels for a smooth spectrum. Codes 71, 72, and 73 retain separate official codes even where their displayed broad names coincide. The approximate north-up footprint-to-LUHK assignment remains a spatial-label limitation.",
        "",
        "## 3. Physical surface-cover spectra",
        "",
        *group_lines(summary, "surface_cover"),
        "",
        "The sampled medians and quartiles support the location ordering shown in Figure 02, while the density spectra additionally expose spread, skewness, overlap, and possible multimodality. Those visual features are descriptive and are not interpreted from curve height alone.",
        "",
        "## 4. Within-GIC surface-cover spectra",
        "",
        *group_lines(summary, "within_gic_surface_cover"),
        "",
        "Figure 04 limits the overlay to well-supported groups with at least the formal minimum sampled n and at least two contributing images. Figure 03 retains facets for all adequately sampled within-GIC cover classes so smaller densities do not disappear behind larger curves.",
        "",
        "## 5. Between-image consistency",
        "",
        *group_lines(summary, "image_comparison"),
        "",
        "Between-image location and shape differences are visible in Figure 05. Because the pilot contains only five temporally adjacent images, these differences are a consistency check rather than an estimate of broad temporal or city-wide variability.",
        "",
        "## 6. Sampling stability",
        "",
        *stability_lines,
        "",
        "Figure 07 displays the distribution of group medians across the primary seed and secondary seeds. Stability across seeds addresses sampling sensitivity only; it does not make spatially correlated pixels independent.",
        "",
        "## 7. Effect sizes and exploratory tests",
        "",
        f"The formal sampled-pixel tables contain {len(effects):,} effect-size rows and {len(tests):,} statistical-test rows ({len(executed_tests):,} executed and {len(skipped_tests):,} skipped under coverage rules). P-values are exploratory, use false-discovery-rate adjustment where applicable, and support rather than replace the spectrum interpretation. Conclusions should cross-reference distribution summaries, effect sizes, image coverage, and seed stability.",
        "",
        "The surface-cover × shadow contrast is **not estimable** because the five reviewed masks contain no valid `shadow_flag=1` pixels. No shadow-present observations or empty spectrum figure were created.",
        "",
        "## 8. Uncertainty summary and supporting boxplots",
        "",
        f"Figure 08 reports sampled medians with percentile 95% bootstrap intervals from {config['statistics']['bootstrap_repetitions']:,} pixel resamples. These intervals are descriptive because neighbouring-pixel correlation remains. Existing boxplots, coverage charts, image comparisons, the earlier stability chart, and the mean-CI chart are supporting outputs under `outputs/part_e/figures/excel/`; they are not the primary figure family.",
        "",
        "## 9. Spatial QA",
        "",
        "Full-pixel temperature, ΔT, LUHK, physical-cover, shadow, and combined panels under `outputs/part_e/figures/spatial_maps/` support alignment and spatial interpretation. They do not replace the sampled-pixel distribution analysis.",
        "",
        "## 10. Excel deliverables",
        "",
        "The main statistical workbook and five pilot pixel workbooks are preserved as interactive delivery layers. Native Excel charts are supporting figures. Excel COM is not required for the formal Python spectrum stage, and future batch runs should not create hundreds of full per-image workbooks unless explicitly requested.",
        "",
        "## Ambient parameters used",
        "",
        "| Image | Ambient temperature (°C) | Source | Validation status |",
        "|---|---:|---|---|",
    ]
    for row in ambient.itertuples(index=False):
        lines.append(
            f"| {row.image_id} | {float(row.ambient_temperature_c):.1f} | {row.ambient_source} | {row.validation_status} |"
        )
    lines.extend([
        "",
        "## Primary outputs",
        "",
        "- Formal figures and captions: `outputs/part_e/figures/spectrum/`.",
        "- Spectrum source/summary table: `outputs/part_e/tables/part_e_pixel_delta_t_spectrum_summary.csv`.",
        "- Grouped sampled/full summaries: `outputs/part_e/tables/part_e_delta_t_by_*_pixels.csv`.",
        "- Effect sizes and exploratory tests: `outputs/part_e/tables/part_e_pixel_effect_sizes.csv` and `part_e_pixel_statistical_tests.csv`.",
        "- Final QA: `outputs/part_e/qa/part_e_final_qa.md`.",
        "",
        "## Reproducibility",
        "",
        "```powershell",
        ".\\.venv\\Scripts\\python.exe scripts\\part_e\\run_part_e_pipeline.py --config config\\part_e_delta_t_analysis.json --resume --from-stage spectrum --to-stage spectrum",
        ".\\.venv\\Scripts\\python.exe scripts\\part_e\\run_part_e_pipeline.py --config config\\part_e_delta_t_analysis.json --resume --from-stage final-qa --to-stage report",
        "```",
        "",
        "The deprecated `06_create_clear_spectrum_figures.py` is research history only and is never called by the formal pipeline.",
        "",
        "## Limitations",
        "",
        "- Only five HKUST pilot images are included; results do not generalize to all of Hong Kong.",
        "- TAT3 ambient parameters and Part D apparent-temperature physical plausibility remain provisional.",
        "- Neighbouring thermal pixels remain spatially correlated after thinning.",
        "- LUHK pixel labels use an approximate north-up footprint model that ignores recorded yaw.",
        "- No shadow-present pixels are available, so a shadow effect is not estimable.",
        "- Exploratory p-values do not establish causal or city-wide effects.",
    ])
    output = project_path(config["outputs"]["summaries"]) / "part_e_round1_delta_t_analysis_summary.md"
    write_markdown(output, lines)
    print(f"Spectrum-first Part E report written: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
