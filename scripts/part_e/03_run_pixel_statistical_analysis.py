#!/usr/bin/env python3
"""Create full-pixel summaries, sampled exploratory tests, stability, and figures."""

from __future__ import annotations

import argparse
import itertools
import os
import zlib
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.multitest import multipletests

from part_e_pixel_common import (
    SAMPLE_COLUMNS,
    SAMPLE_FILES,
    describe_values,
    ensure_output_directories,
    grouped_summary,
    load_config,
    project_path,
    read_canonical,
    spatially_thinned_sample,
    write_csv,
)


os.environ.setdefault("MPLCONFIGDIR", str(project_path(".matplotlib-cache")))
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


PALETTE = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#D55E00", "#56B4E9", "#F0E442"]
SOURCE_STRATA = [
    "measurement_type", "temperature_source", "source_method",
    "surface_cover_provenance", "luhk_provenance", "target_name", "qa_status",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/part_e_delta_t_analysis.json")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--skip-supporting-figures",
        action="store_true",
        help="Write analysis tables without regenerating supporting figures.",
    )
    modes.add_argument(
        "--supporting-figures-only",
        action="store_true",
        help="Regenerate supporting figures from completed samples/tables only.",
    )
    return parser.parse_args()


def read_sample(config: dict, family: str) -> pd.DataFrame:
    path = project_path(config["outputs"]["sample_directory"]) / f"{SAMPLE_FILES[family]}.parquet"
    return pd.read_parquet(path)


def add_label(frame: pd.DataFrame, family: str) -> pd.DataFrame:
    result = frame.copy()
    if "group_name" in result.columns:
        # Schema 0.2 group_name already contains the complete source stratum.
        # Reusing it here prevents measurement/provenance strata from being
        # collapsed again by the formal statistical stage.
        result["analysis_group"] = result["group_name"].astype(str)
        return result
    if family == "luhk":
        result["analysis_group"] = result["luhk_class_code"].astype(str) + " | " + result["luhk_class_name"].astype(str)
    elif family == "surface_cover":
        result["analysis_group"] = result["surface_cover_class"].astype(str)
    elif family == "luhk_surface_cover":
        result["analysis_group"] = (
            result["luhk_class_code"].astype(str) + " | " + result["luhk_class_name"].astype(str) + " | " + result["surface_cover_class"].astype(str)
        )
    elif family == "surface_cover_shadow":
        result["analysis_group"] = result["surface_cover_class"].astype(str) + " | shadow=" + result["shadow_flag"].astype("Int64").astype(str)
    elif family == "image_comparison":
        result["analysis_group"] = result["image_id"].astype(str)
    return result


def full_count_map(coverage: pd.DataFrame, family: str) -> dict[str, int]:
    selected = coverage.loc[coverage["analysis_family"].eq(family)]
    return dict(zip(selected["group_name"].astype(str), selected["full_eligible_pixel_count"].astype(int)))


def rank_biserial_from_u(u_stat: float, n_a: int, n_b: int) -> float:
    return float(2.0 * u_stat / (n_a * n_b) - 1.0)


def statistical_tests_for_family(
    sample: pd.DataFrame, family: str, coverage: pd.DataFrame, config: dict
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    work = add_label(sample, family)
    minimum_n = int(config["sampling"]["minimum_pixels_for_formal_plot"])
    minimum_images = int(config["sampling"]["minimum_images_for_cross_image_statement"])
    full_counts = full_count_map(coverage, family)
    if family == "surface_cover_shadow":
        tests: list[dict[str, object]] = []
        effects: list[dict[str, object]] = []
        for cover_class, cover_group in work.groupby("surface_cover_class", sort=True):
            flags = sorted(cover_group["shadow_flag"].dropna().astype(int).unique().tolist())
            group_a = f"{cover_class} | shadow=0"
            group_b = f"{cover_class} | shadow=1"
            if flags != [0, 1]:
                reason = "Within-cover shadow contrast skipped because both shadow_flag=0 and shadow_flag=1 are not present."
                tests.append({
                    "analysis_family": family, "comparison_type": "within_cover_pairwise",
                    "groups_compared": f"{group_a} vs {group_b}", "test_name": "Mann-Whitney U",
                    "test_statistic": np.nan, "p_value": np.nan, "adjusted_p_value": np.nan,
                    "full_pixel_counts": f"{group_a}={full_counts.get(group_a, 0)}; {group_b}={full_counts.get(group_b, 0)}",
                    "sampled_pixel_counts": f"{group_a}={len(cover_group)}; {group_b}=0",
                    "image_coverage": f"{group_a}={cover_group['image_id'].nunique()}; {group_b}=0",
                    "interpretation_status": "skipped", "skipped_reason": reason,
                })
                effects.append({
                    "analysis_family": family, "group_a": group_a, "group_b": group_b,
                    "n_full_a": full_counts.get(group_a, 0), "n_full_b": full_counts.get(group_b, 0),
                    "n_sampled_a": len(cover_group), "n_sampled_b": 0,
                    "n_images_a": cover_group["image_id"].nunique(), "n_images_b": 0,
                    "effect_size_name": "rank_biserial_correlation", "effect_size": np.nan,
                    "mean_difference_a_minus_b": np.nan, "median_difference_a_minus_b": np.nan,
                    "interpretation_status": "skipped", "skipped_reason": reason,
                })
                continue
            values_a = cover_group.loc[cover_group["shadow_flag"].astype(int).eq(0), "delta_t_c"].to_numpy(float)
            values_b = cover_group.loc[cover_group["shadow_flag"].astype(int).eq(1), "delta_t_c"].to_numpy(float)
            images_a = cover_group.loc[cover_group["shadow_flag"].astype(int).eq(0), "image_id"].nunique()
            images_b = cover_group.loc[cover_group["shadow_flag"].astype(int).eq(1), "image_id"].nunique()
            if min(len(values_a), len(values_b)) < minimum_n or min(images_a, images_b) < minimum_images:
                reason = "Within-cover shadow contrast fails minimum sampled-pixel or image-coverage rules."
                u_stat = p_value = np.nan
                status = "skipped"
            else:
                u_stat, p_value = stats.mannwhitneyu(values_a, values_b, alternative="two-sided", method="asymptotic")
                reason = ""; status = "exploratory_only_spatial_dependence_remains"
            tests.append({
                "analysis_family": family, "comparison_type": "within_cover_pairwise",
                "groups_compared": f"{group_a} vs {group_b}", "test_name": "Mann-Whitney U",
                "test_statistic": u_stat, "p_value": p_value, "adjusted_p_value": p_value,
                "full_pixel_counts": f"{group_a}={full_counts.get(group_a, 0)}; {group_b}={full_counts.get(group_b, 0)}",
                "sampled_pixel_counts": f"{group_a}={len(values_a)}; {group_b}={len(values_b)}",
                "image_coverage": f"{group_a}={images_a}; {group_b}={images_b}",
                "interpretation_status": status, "skipped_reason": reason,
            })
            effects.append({
                "analysis_family": family, "group_a": group_a, "group_b": group_b,
                "n_full_a": full_counts.get(group_a, 0), "n_full_b": full_counts.get(group_b, 0),
                "n_sampled_a": len(values_a), "n_sampled_b": len(values_b), "n_images_a": images_a, "n_images_b": images_b,
                "effect_size_name": "rank_biserial_correlation",
                "effect_size": rank_biserial_from_u(float(u_stat), len(values_a), len(values_b)) if np.isfinite(u_stat) else np.nan,
                "mean_difference_a_minus_b": float(values_a.mean() - values_b.mean()) if np.isfinite(u_stat) else np.nan,
                "median_difference_a_minus_b": float(np.median(values_a) - np.median(values_b)) if np.isfinite(u_stat) else np.nan,
                "interpretation_status": "exploratory_effect_size" if np.isfinite(u_stat) else "skipped",
                "skipped_reason": reason,
            })
        return tests, effects
    group_info = work.groupby("analysis_group", sort=True).agg(
        n=("delta_t_c", "size"), images=("image_id", "nunique")
    )
    valid_groups = group_info.loc[(group_info["n"] >= minimum_n) & (group_info["images"] >= minimum_images)].index.tolist()
    tests: list[dict[str, object]] = []
    effects: list[dict[str, object]] = []
    if len(valid_groups) >= 2:
        arrays = [work.loc[work["analysis_group"].eq(group), "delta_t_c"].to_numpy(float) for group in valid_groups]
        statistic, p_value = stats.kruskal(*arrays)
        tests.append({
            "analysis_family": family,
            "comparison_type": "global",
            "groups_compared": " vs ".join(valid_groups),
            "test_name": "Kruskal-Wallis",
            "test_statistic": float(statistic),
            "p_value": float(p_value),
            "adjusted_p_value": float(p_value),
            "full_pixel_counts": "; ".join(f"{group}={full_counts.get(group, 0)}" for group in valid_groups),
            "sampled_pixel_counts": "; ".join(f"{group}={int(group_info.loc[group, 'n'])}" for group in valid_groups),
            "image_coverage": "; ".join(f"{group}={int(group_info.loc[group, 'images'])}" for group in valid_groups),
            "interpretation_status": "exploratory_only_spatial_dependence_remains",
            "skipped_reason": "",
        })
    else:
        tests.append({
            "analysis_family": family, "comparison_type": "global", "groups_compared": "",
            "test_name": "Kruskal-Wallis", "test_statistic": np.nan, "p_value": np.nan,
            "adjusted_p_value": np.nan, "full_pixel_counts": "", "sampled_pixel_counts": "",
            "image_coverage": "", "interpretation_status": "skipped",
            "skipped_reason": "Fewer than two groups meet both minimum sampled-pixel and minimum-image rules.",
        })

    pair_rows: list[dict[str, object]] = []
    effect_rows: list[dict[str, object]] = []
    for group_a, group_b in itertools.combinations(group_info.index.astype(str), 2):
        info_a, info_b = group_info.loc[group_a], group_info.loc[group_b]
        reason = ""
        if int(info_a["n"]) < minimum_n or int(info_b["n"]) < minimum_n:
            reason = f"At least one group has fewer than {minimum_n} sampled pixels."
        elif int(info_a["images"]) < minimum_images or int(info_b["images"]) < minimum_images:
            reason = f"At least one group occurs in fewer than {minimum_images} images."
        values_a = work.loc[work["analysis_group"].eq(group_a), "delta_t_c"].to_numpy(float)
        values_b = work.loc[work["analysis_group"].eq(group_b), "delta_t_c"].to_numpy(float)
        common = {
            "analysis_family": family,
            "group_a": group_a,
            "group_b": group_b,
            "n_full_a": full_counts.get(group_a, 0), "n_full_b": full_counts.get(group_b, 0),
            "n_sampled_a": len(values_a), "n_sampled_b": len(values_b),
            "n_images_a": int(info_a["images"]), "n_images_b": int(info_b["images"]),
        }
        if reason:
            pair_rows.append({
                **common, "comparison_type": "pairwise", "groups_compared": f"{group_a} vs {group_b}",
                "test_name": "Mann-Whitney U", "test_statistic": np.nan, "p_value": np.nan,
                "adjusted_p_value": np.nan, "full_pixel_counts": f"{len(values_a)}; {len(values_b)}",
                "sampled_pixel_counts": f"{len(values_a)}; {len(values_b)}",
                "image_coverage": f"{int(info_a['images'])}; {int(info_b['images'])}",
                "interpretation_status": "skipped", "skipped_reason": reason,
            })
            effect_rows.append({
                **common, "effect_size_name": "rank_biserial_correlation", "effect_size": np.nan,
                "mean_difference_a_minus_b": np.nan, "median_difference_a_minus_b": np.nan,
                "interpretation_status": "skipped", "skipped_reason": reason,
            })
            continue
        u_stat, p_value = stats.mannwhitneyu(values_a, values_b, alternative="two-sided", method="asymptotic")
        pair_rows.append({
            **common, "comparison_type": "pairwise", "groups_compared": f"{group_a} vs {group_b}",
            "test_name": "Mann-Whitney U", "test_statistic": float(u_stat), "p_value": float(p_value),
            "adjusted_p_value": np.nan,
            "full_pixel_counts": f"{full_counts.get(group_a, 0)}; {full_counts.get(group_b, 0)}",
            "sampled_pixel_counts": f"{len(values_a)}; {len(values_b)}",
            "image_coverage": f"{int(info_a['images'])}; {int(info_b['images'])}",
            "interpretation_status": "exploratory_only_spatial_dependence_remains", "skipped_reason": "",
        })
        effect_rows.append({
            **common, "effect_size_name": "rank_biserial_correlation",
            "effect_size": rank_biserial_from_u(float(u_stat), len(values_a), len(values_b)),
            "mean_difference_a_minus_b": float(values_a.mean() - values_b.mean()),
            "median_difference_a_minus_b": float(np.median(values_a) - np.median(values_b)),
            "interpretation_status": "exploratory_effect_size", "skipped_reason": "",
        })
    valid_pair_positions = [index for index, row in enumerate(pair_rows) if np.isfinite(row["p_value"])]
    if valid_pair_positions:
        adjusted = multipletests([pair_rows[index]["p_value"] for index in valid_pair_positions], method="fdr_bh")[1]
        for index, value in zip(valid_pair_positions, adjusted):
            pair_rows[index]["adjusted_p_value"] = float(value)
    tests.extend(pair_rows)
    effects.extend(effect_rows)
    return tests, effects


def stability_analysis(full: pd.DataFrame, config: dict) -> pd.DataFrame:
    seeds = [int(config["sampling"]["primary_seed"]), *map(int, config["sampling"]["secondary_seeds"])]
    rows: list[dict[str, object]] = []
    for family in ("luhk", "surface_cover"):
        for seed in seeds:
            sample, _ = spatially_thinned_sample(full, family, config, seed)
            sample = add_label(sample, family)
            group_stats: dict[str, dict[str, float | int]] = {}
            for group_name, group in sample.groupby("analysis_group", sort=True):
                summary = describe_values(group["delta_t_c"])
                group_stats[str(group_name)] = summary
                rows.append({
                    "analysis_family": family, "record_type": "group", "sampling_seed": seed,
                    "is_primary_seed": seed == seeds[0], "group_a": str(group_name), "group_b": "",
                    "sampled_n_a": summary["n"], "sampled_n_b": np.nan,
                    "sampled_mean_a": summary["mean"], "sampled_mean_b": np.nan,
                    "sampled_median_a": summary["median"], "sampled_median_b": np.nan,
                    "q25_a": summary["q25"], "q75_a": summary["q75"],
                    "pairwise_mean_difference": np.nan, "pairwise_median_difference": np.nan,
                    "effect_size_rank_biserial": np.nan,
                })
            for group_a, group_b in itertools.combinations(sorted(group_stats), 2):
                a = sample.loc[sample["analysis_group"].eq(group_a), "delta_t_c"].to_numpy(float)
                b = sample.loc[sample["analysis_group"].eq(group_b), "delta_t_c"].to_numpy(float)
                if len(a) < 2 or len(b) < 2:
                    continue
                u_stat = stats.mannwhitneyu(a, b, alternative="two-sided", method="asymptotic").statistic
                rows.append({
                    "analysis_family": family, "record_type": "pair", "sampling_seed": seed,
                    "is_primary_seed": seed == seeds[0], "group_a": group_a, "group_b": group_b,
                    "sampled_n_a": len(a), "sampled_n_b": len(b),
                    "sampled_mean_a": float(a.mean()), "sampled_mean_b": float(b.mean()),
                    "sampled_median_a": float(np.median(a)), "sampled_median_b": float(np.median(b)),
                    "q25_a": float(np.quantile(a, 0.25)), "q75_a": float(np.quantile(a, 0.75)),
                    "pairwise_mean_difference": float(a.mean() - b.mean()),
                    "pairwise_median_difference": float(np.median(a) - np.median(b)),
                    "effect_size_rank_biserial": rank_biserial_from_u(float(u_stat), len(a), len(b)),
                })
        print(f"Stability seeds completed for {family}: {len(seeds)}")
    result = pd.DataFrame(rows)
    if result.empty:
        return pd.DataFrame(columns=[
            "analysis_family", "record_type", "sampling_seed", "is_primary_seed",
            "group_a", "group_b", "sampled_n_a", "sampled_n_b", "sampled_mean_a",
            "sampled_mean_b", "sampled_median_a", "sampled_median_b", "q25_a", "q75_a",
            "pairwise_mean_difference", "pairwise_median_difference",
            "effect_size_rank_biserial", "sign_agreement_mean_fraction",
            "sign_agreement_median_fraction", "sign_agreement_effect_fraction", "stability_status",
        ])
    result["sign_agreement_mean_fraction"] = np.nan
    result["sign_agreement_median_fraction"] = np.nan
    result["sign_agreement_effect_fraction"] = np.nan
    result["stability_status"] = "group_distribution_record"
    pairs = result.loc[result["record_type"].eq("pair")]
    for keys, group in pairs.groupby(["analysis_family", "group_a", "group_b"], sort=True):
        primary = group.loc[group["is_primary_seed"]]
        secondary = group.loc[~group["is_primary_seed"]]
        if primary.empty or secondary.empty:
            continue
        agreements = {}
        for column, output in (
            ("pairwise_mean_difference", "sign_agreement_mean_fraction"),
            ("pairwise_median_difference", "sign_agreement_median_fraction"),
            ("effect_size_rank_biserial", "sign_agreement_effect_fraction"),
        ):
            primary_sign = np.sign(float(primary.iloc[0][column]))
            agreements[output] = float((np.sign(secondary[column].to_numpy(float)) == primary_sign).mean())
        stable = min(agreements.values()) >= 0.8
        mask = (
            result["analysis_family"].eq(keys[0]) & result["group_a"].eq(keys[1])
            & result["group_b"].eq(keys[2]) & result["record_type"].eq("pair")
        )
        for output, value in agreements.items():
            result.loc[mask, output] = value
        result.loc[mask, "stability_status"] = "stable_sign_across_seeds" if stable else "seed_sensitive_sign"
    return result


def apply_stability_coverage_rules(stability: pd.DataFrame, coverage: pd.DataFrame, config: dict) -> pd.DataFrame:
    result = stability.copy()
    if result.empty:
        return result
    minimum_n = int(config["sampling"]["minimum_pixels_for_formal_plot"])
    minimum_images = int(config["sampling"]["minimum_images_for_cross_image_statement"])
    lookup = coverage.set_index(["analysis_family", "group_name"])[
        ["sampled_pixel_count", "full_image_count"]
    ].to_dict(orient="index")
    pair_mask = result["record_type"].eq("pair")
    for index, row in result.loc[pair_mask & result["is_primary_seed"].astype(bool)].iterrows():
        info_a = lookup.get((row["analysis_family"], row["group_a"]), {})
        info_b = lookup.get((row["analysis_family"], row["group_b"]), {})
        adequate = (
            info_a.get("sampled_pixel_count", 0) >= minimum_n
            and info_b.get("sampled_pixel_count", 0) >= minimum_n
            and info_a.get("full_image_count", 0) >= minimum_images
            and info_b.get("full_image_count", 0) >= minimum_images
        )
        if not adequate:
            mask = (
                result["analysis_family"].eq(row["analysis_family"])
                & result["group_a"].eq(row["group_a"])
                & result["group_b"].eq(row["group_b"])
                & result["record_type"].eq("pair")
            )
            result.loc[mask, "stability_status"] = "insufficient_coverage_for_conclusion"
    return result


def save_figure(fig: plt.Figure, directory: Path, stem: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    fig.savefig(directory / f"{stem}.png", dpi=200, facecolor="white", bbox_inches="tight")
    fig.savefig(directory / f"{stem}.pdf", facecolor="white", bbox_inches="tight")
    plt.close(fig)


def boxplot_figure(sample: pd.DataFrame, group_col: str, title: str, stem: str, directory: Path, config: dict) -> None:
    order = sample.groupby(group_col)["delta_t_c"].median().sort_values().index.tolist()
    values = [sample.loc[sample[group_col].eq(group), "delta_t_c"].to_numpy(float) for group in order]
    fig, ax = plt.subplots(figsize=(12, 7), facecolor="white")
    boxes = ax.boxplot(values, orientation="horizontal", tick_labels=order, showfliers=False, patch_artist=True, widths=0.65)
    for patch, color in zip(boxes["boxes"], itertools.cycle(PALETTE)):
        patch.set_facecolor(color); patch.set_alpha(0.75)
    ax.axvline(0, color="#666666", linewidth=1, linestyle="--")
    ax.set_xlabel("ΔT (°C)", fontsize=12); ax.set_ylabel("")
    ax.set_title(title, fontsize=14, pad=12)
    ax.tick_params(labelsize=10); ax.grid(axis="x", alpha=0.2)
    full_n = int(sample["source_population_count"].drop_duplicates().sum())
    ax.text(0.0, -0.13, f"Sampled individual pixels; seed {config['sampling']['primary_seed']}; {config['sampling']['method']}; sampled n={len(sample):,}; full eligible n={full_n:,}.", transform=ax.transAxes, fontsize=10)
    fig.tight_layout()
    save_figure(fig, directory, stem)


def bootstrap_mean_ci(values: np.ndarray, seed: int, repetitions: int) -> tuple[float, float, float]:
    rng = np.random.default_rng(seed)
    estimates = np.empty(repetitions, dtype=float)
    for index in range(repetitions):
        estimates[index] = rng.choice(values, size=len(values), replace=True).mean()
    return float(values.mean()), float(np.quantile(estimates, 0.025)), float(np.quantile(estimates, 0.975))


def make_figures(samples: dict[str, pd.DataFrame], coverage: pd.DataFrame, stability: pd.DataFrame, config: dict) -> None:
    directory = project_path(config["outputs"]["excel_figures"])
    luhk = add_label(samples["luhk"], "luhk")
    boxplot_figure(luhk, "analysis_group", "Pixel-level ΔT by LUHK class", "fig01_delta_t_by_luhk_boxplot", directory, config)
    cover = add_label(samples["surface_cover"], "surface_cover")
    boxplot_figure(cover, "analysis_group", "Pixel-level ΔT by physical surface cover", "fig02_delta_t_by_surface_cover_boxplot", directory, config)

    gic = samples["luhk_surface_cover"].loc[samples["luhk_surface_cover"]["luhk_class_code"].astype(int).eq(31)].copy()
    gic = gic.loc[gic["surface_cover_class"].isin(["roof", "concrete_pavement", "vegetation_tree", "grass_low_vegetation"])]
    adequate = gic.groupby("surface_cover_class").size()
    gic = gic.loc[gic["surface_cover_class"].isin(adequate[adequate >= config["sampling"]["minimum_pixels_for_formal_plot"]].index)]
    boxplot_figure(gic, "surface_cover_class", "Pixel-level ΔT within GIC / open space", "fig03_delta_t_within_gic_by_cover", directory, config)

    shadow = samples["surface_cover_shadow"].copy()
    fig, ax = plt.subplots(figsize=(11, 6), facecolor="white")
    counts = shadow.groupby(["surface_cover_class", "shadow_flag"]).size().unstack(fill_value=0)
    counts.plot(kind="bar", ax=ax, color=["#0072B2", "#D55E00"], width=0.75)
    ax.set_yscale("log"); ax.set_ylabel("Sampled pixel count (log scale)", fontsize=12); ax.set_xlabel("Physical surface cover", fontsize=12)
    ax.set_title("Cover × shadow sampling availability", fontsize=14)
    ax.legend(title="shadow_flag", frameon=False); ax.tick_params(axis="x", rotation=25, labelsize=10); ax.grid(axis="y", alpha=0.2)
    ax.text(0.0, -0.22, "All reviewed shadow masks contain only shadow_flag=0; no within-cover shadow contrast is estimable.", transform=ax.transAxes, fontsize=10, color="#9C2F2F")
    fig.tight_layout(); save_figure(fig, directory, "fig04_delta_t_by_cover_shadow")

    family_coverage = coverage.groupby("analysis_family", sort=True).agg(
        full_eligible=("full_eligible_pixel_count", "sum"), sampled=("sampled_pixel_count", "sum"),
        image_coverage=("sampled_image_count", "max")
    ).reset_index()
    fig, ax = plt.subplots(figsize=(12, 6), facecolor="white")
    positions = np.arange(len(family_coverage)); width = 0.38
    ax.bar(positions - width / 2, family_coverage["full_eligible"], width, label="Full eligible pixels", color="#56B4E9")
    ax.bar(positions + width / 2, family_coverage["sampled"], width, label="Sampled pixels", color="#E69F00")
    ax.set_yscale("log"); ax.set_xticks(positions, family_coverage["analysis_family"], rotation=20, ha="right")
    ax.set_ylabel("Pixel count (log scale)", fontsize=12); ax.set_title("Full eligible and sampled pixel coverage", fontsize=14)
    ax.legend(frameon=False); ax.grid(axis="y", alpha=0.2)
    for index, row in family_coverage.iterrows():
        ax.text(index, row["sampled"] * 1.2, f"{row['sampled']/row['full_eligible']:.2%}", ha="center", fontsize=10)
    fig.tight_layout(); save_figure(fig, directory, "fig05_pixel_sample_coverage")

    image = add_label(samples["image_comparison"], "image_comparison")
    boxplot_figure(image, "analysis_group", "Pixel-level ΔT by pilot image", "fig06_delta_t_by_image", directory, config)

    stable_groups = stability.loc[(stability["record_type"].eq("group")) & (stability["analysis_family"].eq("surface_cover"))]
    fig, ax = plt.subplots(figsize=(12, 6), facecolor="white")
    group_order = stable_groups.groupby("group_a")["sampled_median_a"].median().sort_values().index.tolist()
    values = [stable_groups.loc[stable_groups["group_a"].eq(group), "sampled_median_a"].to_numpy(float) for group in group_order]
    boxes = ax.boxplot(values, tick_labels=group_order, showfliers=True, patch_artist=True)
    for patch, color in zip(boxes["boxes"], itertools.cycle(PALETTE)):
        patch.set_facecolor(color); patch.set_alpha(0.75)
    ax.set_ylabel("Sampled median ΔT (°C)", fontsize=12); ax.set_xlabel("Physical surface cover", fontsize=12)
    ax.set_title("Sampling stability across 21 deterministic seeds", fontsize=14); ax.tick_params(axis="x", rotation=25, labelsize=10); ax.grid(axis="y", alpha=0.2)
    ax.text(0.0, -0.2, "Primary seed 20260715 plus 20 secondary seeds; each point summarizes original sampled pixels after spatial thinning.", transform=ax.transAxes, fontsize=10)
    fig.tight_layout(); save_figure(fig, directory, "fig07_sampling_stability")

    repetitions = int(config["statistics"]["bootstrap_repetitions"])
    ci_rows = []
    for group_name, group in cover.groupby("analysis_group", sort=True):
        values = group["delta_t_c"].to_numpy(float)
        seed = int(config["sampling"]["primary_seed"]) + zlib.crc32(str(group_name).encode("utf-8"))
        mean, lower, upper = bootstrap_mean_ci(values, seed, repetitions)
        ci_rows.append((str(group_name), mean, lower, upper, len(values)))
    ci_rows.sort(key=lambda row: row[1])
    fig, ax = plt.subplots(figsize=(11, 6), facecolor="white")
    y = np.arange(len(ci_rows)); means = np.array([row[1] for row in ci_rows]); lower = np.array([row[2] for row in ci_rows]); upper = np.array([row[3] for row in ci_rows])
    ax.errorbar(means, y, xerr=np.vstack([means - lower, upper - means]), fmt="o", color="#0072B2", ecolor="#555555", capsize=5)
    ax.set_yticks(y, [row[0] for row in ci_rows]); ax.set_xlabel("Mean ΔT (°C), 95% bootstrap CI", fontsize=12)
    ax.set_title("Sampled-pixel mean ΔT by physical surface cover", fontsize=14); ax.grid(axis="x", alpha=0.2)
    ax.text(0.0, -0.14, f"Error bars are percentile 95% bootstrap CIs ({repetitions:,} resamples); pixels remain spatially dependent.", transform=ax.transAxes, fontsize=10)
    fig.tight_layout(); save_figure(fig, directory, "fig08_cover_mean_delta_t_95ci")


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    ensure_output_directories(config)
    full = read_canonical(config, columns=list(dict.fromkeys(SAMPLE_COLUMNS + ["pixel_accepted"])))
    samples = {family: read_sample(config, family) for family in SAMPLE_FILES}
    coverage = pd.read_csv(project_path(config["outputs"]["tables"]) / "part_e_pixel_sample_coverage.csv")
    stability_path = project_path(config["outputs"]["tables"]) / "part_e_sampling_stability.csv"
    if args.supporting_figures_only:
        if not stability_path.is_file():
            raise FileNotFoundError(f"Supporting figures require completed stability results: {stability_path}")
        make_figures(samples, coverage, pd.read_csv(stability_path), config)
        print("Supporting Part E figures regenerated from completed sampled-pixel outputs")
        return 0
    accepted = full["pixel_accepted"].astype(bool)
    summaries = {
        "part_e_delta_t_by_luhk_pixels.csv": grouped_summary(full, samples["luhk"], SOURCE_STRATA + ["luhk_class_code", "luhk_class_name"], accepted & full["luhk_label_valid"].astype(bool)),
        "part_e_delta_t_by_surface_cover_pixels.csv": grouped_summary(full, samples["surface_cover"], SOURCE_STRATA + ["surface_cover_class"], accepted & full["surface_cover_valid"].astype(bool)),
        "part_e_delta_t_by_luhk_surface_cover_pixels.csv": grouped_summary(full, samples["luhk_surface_cover"], SOURCE_STRATA + ["luhk_class_code", "luhk_class_name", "surface_cover_class"], accepted & full["luhk_label_valid"].astype(bool) & full["surface_cover_valid"].astype(bool)),
        "part_e_delta_t_by_surface_cover_shadow_pixels.csv": grouped_summary(full, samples["surface_cover_shadow"], SOURCE_STRATA + ["surface_cover_class", "shadow_flag"], accepted & full["surface_cover_valid"].astype(bool) & full["shadow_valid"].astype(bool)),
        "part_e_delta_t_by_image_pixels.csv": grouped_summary(full, samples["image_comparison"], SOURCE_STRATA + ["image_id"], accepted),
    }
    for filename, frame in summaries.items():
        write_csv(project_path(config["outputs"]["tables"]) / filename, frame)

    tests: list[dict[str, object]] = []
    effects: list[dict[str, object]] = []
    for family, sample in samples.items():
        family_tests, family_effects = statistical_tests_for_family(sample, family, coverage, config)
        tests.extend(family_tests); effects.extend(family_effects)
    write_csv(project_path(config["outputs"]["tables"]) / "part_e_pixel_statistical_tests.csv", pd.DataFrame(tests))
    write_csv(project_path(config["outputs"]["tables"]) / "part_e_pixel_effect_sizes.csv", pd.DataFrame(effects))

    expected_seed_count = 1 + len(config["sampling"]["secondary_seeds"])
    if stability_path.exists():
        existing_stability = pd.read_csv(stability_path)
    else:
        existing_stability = pd.DataFrame()
    if not existing_stability.empty and existing_stability["sampling_seed"].nunique() == expected_seed_count:
        stability = existing_stability
        print(f"Reusing completed stability table with {expected_seed_count} seeds")
    else:
        stability = stability_analysis(full, config)
    stability = apply_stability_coverage_rules(stability, coverage, config)
    write_csv(stability_path, stability)
    if not args.skip_supporting_figures:
        make_figures(samples, coverage, stability, config)
    print(f"Grouped tables: {len(summaries)}; test rows: {len(tests)}; effect-size rows: {len(effects)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
