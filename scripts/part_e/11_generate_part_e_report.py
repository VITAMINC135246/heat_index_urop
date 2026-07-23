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
    primary_seed = int(config["sampling"]["primary_seed"])
    overall = summary.loc[summary["analysis_family"].eq("overall")].iloc[0]
    canonical_value = str(config.get("outputs", {}).get("canonical_parquet", ""))
    canonical_path = project_path(canonical_value) if canonical_value else None
    canonical = pd.read_parquet(canonical_path) if canonical_path and canonical_path.is_file() else pd.DataFrame()
    image_ids = (
        sorted(canonical["image_id"].astype(str).unique())
        if "image_id" in canonical
        else list(map(str, config.get("pilot_image_ids", [])))
    )
    image_count = len(image_ids) or int(overall["n_images_full"])
    source_methods = (
        sorted(canonical["source_method"].dropna().astype(str).unique())
        if "source_method" in canonical
        else []
    )
    measurement_types = (
        sorted(canonical["measurement_type"].dropna().astype(str).unique())
        if "measurement_type" in canonical
        else []
    )
    shadow_known = int(canonical.get("shadow_valid", pd.Series(dtype=bool)).fillna(False).astype(bool).sum())
    shadow_present = int(
        (
            canonical.get("shadow_valid", pd.Series(False, index=canonical.index)).fillna(False).astype(bool)
            & pd.to_numeric(
                canonical.get("shadow_flag", pd.Series(0, index=canonical.index)), errors="coerce"
            ).fillna(0).astype(int).eq(1)
        ).sum()
    )
    if not canonical.empty and "ambient_temperature_c" in canonical:
        ambient_columns = [
            column for column in (
                "image_id", "ambient_temperature_c", "ambient_source", "ambient_definition",
                "ambient_data_qa_status", "ambient_provenance", "ambient_source_record",
            ) if column in canonical
        ]
        ambient = canonical.loc[:, ambient_columns].drop_duplicates(subset=["image_id"]).copy()
    else:
        legacy_ambient = project_path(config.get("inputs", {}).get("ambient_manifest", ""))
        ambient = pd.read_csv(legacy_ambient) if legacy_ambient.is_file() else pd.DataFrame()
    overall_status = str(overall.get("kde_status", "unavailable"))
    if overall_status == "eligible":
        overall_text = (
            f"The source-compatible image-stratified sample contains {int(overall['n_pixels_sampled']):,} pixels "
            f"from {int(overall['n_images'])} images, representing {int(overall['n_pixels_full']):,} formal "
            f"target-eligible pixels. Median ΔT is {fmt(overall['median_sampled'])} °C, mean is "
            f"{fmt(overall['mean_sampled'])} °C, Q25–Q75 is {fmt(overall['q25_sampled'])} to "
            f"{fmt(overall['q75_sampled'])} °C, and Q05–Q95 is {fmt(overall['q05_sampled'])} to "
            f"{fmt(overall['q95_sampled'])} °C. Curve height is normalized density, not pixel count."
        )
    else:
        overall_text = (
            "A single overall density was not produced because the accepted pixels contain heterogeneous "
            f"measurement/ROI/provenance strata ({overall.get('eligibility_or_skipped_reason', overall_status)}). "
            "Use the source-aware LUHK, surface-cover, and per-image facets; no pooled curve is treated as primary."
        )

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
        f"> Provisional analysis of {image_count} accepted capture(s). Results describe only these inputs and do not generalize to all of Hong Kong. Source methods: {', '.join(source_methods) or 'not recorded'}; measurement types: {', '.join(measurement_types) or 'not recorded'}.",
        "",
        "## Method and observation unit",
        "",
        "The formal observation is one original thermal pixel. Every formal pixel is accepted, finite, analysis-eligible, and inside target_mask:",
        "",
        "```text",
        "delta_t_c = temperature_c - ambient_temperature_c",
        "```",
        "",
        f"The canonical Parquet retains the complete source rasters; {int(overall['n_pixels_full']):,} accepted finite pixels also satisfy analysis_eligible=true and target_mask=true and therefore enter formal Part E. Pixels outside a reviewed polygon target remain descriptive source data only and are excluded from these counts. Formal plots use dispersed individual pixels selected by `{config['sampling']['method']}` with primary seed {primary_seed}; neither 10 m LUHK cells nor sampling tiles are averaged. Spatial thinning does not remove spatial autocorrelation, so sampled pixels are not described as independent observations.",
        "",
        "Here, spectrum means the statistical distribution/density spectrum of pixel-level ΔT, not an electromagnetic reflectance or multispectral-band spectrum. Python/SciPy is the formal plotting engine; density curves use Scott's bandwidth rule, common comparison axes, and no extrapolation beyond each group's observed sampled range.",
        "",
        "## 1. Overall pixel ΔT spectrum",
        "",
        overall_text,
        "",
        "## 2. LUHK spectra",
        "",
        *group_lines(summary, "luhk"),
        "",
        "LUHK categories and provenance are read from the current canonical inputs. Official lookup and user-supplied target context remain separate strata. Approximate north-up footprint assignment remains a spatial-label limitation and does not imply surveyed pixel precision.",
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
        f"Between-image location and shape differences are visible in Figure 05 for {image_count} accepted capture(s). This is a descriptive consistency view, not a temporal series: only captures explicitly confirmed as the same physical target may be compared through time.",
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
        (
            f"Shadow availability in the current canonical data: {shadow_known:,} known pixels and "
            f"{shadow_present:,} shadow-present pixels. A within-cover shadow contrast is reported only where "
            "both states meet the configured coverage rules; no missing state is fabricated."
        ),
        "",
        "## 8. Uncertainty summary and supporting boxplots",
        "",
        f"Figure 08 reports sampled medians with percentile 95% bootstrap intervals from {config['statistics']['bootstrap_repetitions']:,} pixel resamples. These intervals are descriptive because neighbouring-pixel correlation remains. Boxplots, coverage charts, image comparisons and stability charts, when requested, are supporting outputs under `{project_path(config['outputs']['excel_figures']).resolve().as_posix()}`; they are not the primary figure family.",
        "",
        "## 9. Spatial QA",
        "",
        f"Full-pixel temperature, ΔT, LUHK, physical-cover, shadow, target/eligibility, and combined panels under `{project_path(config['outputs']['spatial_maps']).resolve().as_posix()}` support alignment and spatial interpretation. They do not replace the sampled-pixel distribution analysis.",
        "",
        "## 10. Excel deliverables",
        "",
        "Excel workbooks and native charts are optional supporting delivery layers. Excel COM is not required for the formal Python spectrum stage, and batch runs do not create full per-image workbooks unless explicitly requested.",
        "",
        "## Ambient parameters used",
        "",
        "| Image | Ambient temperature (°C) | Source / definition | QA status | Provenance / source record |",
        "|---|---:|---|---|---|",
    ]
    for _, row in ambient.iterrows():
        source = str(row.get("ambient_source", row.get("source", "unavailable")))
        definition = str(row.get("ambient_definition", row.get("definition", "unavailable")))
        qa = str(row.get("ambient_data_qa_status", row.get("validation_status", "unavailable")))
        provenance = str(row.get("ambient_provenance", "unavailable"))
        source_record = str(row.get("ambient_source_record", row.get("source_record", "")))
        ambient_value = pd.to_numeric(row.get("ambient_temperature_c"), errors="coerce")
        lines.append(
            f"| {row.get('image_id', 'unavailable')} | {fmt(ambient_value, 1)} | "
            f"{source} / {definition} | {qa} | {provenance}"
            + (f" / {source_record}" if source_record and source_record != "nan" else "")
            + " |"
        )
    lines.extend([
        "",
        "## Primary outputs",
        "",
        f"- Formal figures and captions: `{project_path(config['outputs']['spectrum_figures']).resolve().as_posix()}`.",
        f"- Spectrum and grouped-statistics tables: `{tables.resolve().as_posix()}`.",
        f"- Spatial figures: `{project_path(config['outputs']['spatial_maps']).resolve().as_posix()}`.",
        f"- QA: `{project_path(config['outputs']['qa']).resolve().as_posix()}`.",
        "",
        "## Reproducibility",
        "",
        "```powershell",
        f'.\\.venv\\Scripts\\python.exe scripts\\part_e\\run_part_e_pipeline.py --config "{project_path(args.config).resolve()}" --resume --from-stage spectrum --to-stage spectrum',
        f'.\\.venv\\Scripts\\python.exe scripts\\part_e\\run_part_e_pipeline.py --config "{project_path(args.config).resolve()}" --resume --from-stage final-qa --to-stage report',
        "```",
        "",
        "The report is generated from the current canonical pixels and current stage tables; it does not assume a fixed pilot image list.",
        "",
        "## Limitations",
        "",
        f"- Only the {image_count} accepted capture(s) listed in this run are represented; results do not generalize to all of Hong Kong.",
        "- Ambient definitions, QA and source records above govern whether ΔT strata may be combined; provisional parameters remain provisional.",
        "- Neighbouring thermal pixels remain spatially correlated after thinning.",
        "- LUHK pixel labels use an approximate north-up footprint model that ignores recorded yaw.",
        f"- Shadow evidence is data-dependent ({shadow_present:,} current shadow-present pixels); a contrast is unavailable unless both states meet coverage rules.",
        "- Exploratory p-values do not establish causal or city-wide effects.",
    ])
    output = project_path(config["outputs"]["summaries"]) / "part_e_round1_delta_t_analysis_summary.md"
    write_markdown(output, lines)
    print(f"Spectrum-first Part E report written: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
