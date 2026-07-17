#!/usr/bin/env python3
"""Generate the formal Part E sampled-pixel delta-T spectrum figure family.

"Spectrum" means a statistical distribution/density spectrum of original
thermal-pixel delta-T values. This stage never reads the retired cell-level
tables and never averages pixels before plotting.
"""

from __future__ import annotations

import argparse
import math
import os
import textwrap
import zlib
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parents[2] / ".matplotlib-cache"))

import matplotlib
import numpy as np
import pandas as pd
from scipy import stats

from part_e_pixel_common import (
    SAMPLE_FILES,
    ensure_output_directories,
    load_config,
    project_path,
    write_csv,
    write_markdown,
)


matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


PALETTE = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#D55E00", "#56B4E9"]
COVER_LABELS = {
    "bare_soil": "Bare soil",
    "concrete_pavement": "Concrete pavement",
    "grass_low_vegetation": "Grass / low vegetation",
    "roof": "Roof",
    "vegetation_tree": "Vegetation / tree canopy",
}
FIGURE_STEMS = [
    "fig00_pixel_delta_t_spectrum_overall",
    "fig01_pixel_delta_t_spectrum_by_luhk_facets",
    "fig02_pixel_delta_t_spectrum_by_surface_cover_facets",
    "fig03_pixel_delta_t_spectrum_within_gic_by_cover_facets",
    "fig04_pixel_delta_t_spectrum_within_gic_overlay",
    "fig05_pixel_delta_t_spectrum_by_image_facets",
    "fig07_pixel_delta_t_sampling_stability",
    "fig08_pixel_delta_t_surface_cover_bootstrap_ci",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/part_e_delta_t_analysis.json")
    return parser.parse_args()


def read_sample(config: dict[str, Any], family: str) -> pd.DataFrame:
    path = project_path(config["outputs"]["sample_directory"]) / f"{SAMPLE_FILES[family]}.parquet"
    if not path.is_file():
        raise FileNotFoundError(f"Required sampled-pixel Parquet is missing: {path}")
    frame = pd.read_parquet(path)
    required = {
        "pixel_uid", "image_id", "delta_t_c", "group_name", "sampling_seed",
        "sampling_method", "source_population_count",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"{path.name} is missing required columns: {missing}")
    if frame["pixel_uid"].duplicated().any():
        raise ValueError(f"{path.name} contains duplicate pixel_uid values")
    if not np.isfinite(frame["delta_t_c"].to_numpy(float)).all():
        raise ValueError(f"{path.name} contains non-finite delta_t_c values")
    return frame


def readable_group(group_name: str, family: str) -> str:
    text = str(group_name)
    parts = text.split(" | ")
    source_keys = {
        "measurement_type", "temperature_source", "temperature_definition", "source_method",
        "surface_cover_provenance", "luhk_provenance", "target_id", "target_name", "qa_status",
    }
    source_parts = [part for part in parts if part.split("=", 1)[0] in source_keys]
    detail_parts = [part for part in parts if part not in source_parts]
    source_label = ", ".join(part.replace("measurement_type=", "type=") for part in source_parts)
    if family in {"surface_cover", "within_gic_surface_cover", "surface_cover_shadow"}:
        base = next((part for part in reversed(detail_parts) if not part.startswith("shadow=")), "unknown")
        label = COVER_LABELS.get(base, base.replace("_", " ").title())
        if "shadow=" in text:
            label += " | " + text.rsplit(" | ", 1)[-1]
        return f"{label}\n[{source_label}]" if source_label else label
    if family == "image_comparison":
        label = detail_parts[-1] if detail_parts else text
        label = label.replace("DJI_20260107", "DJI 2026-01-07 ")
        return f"{label}\n[{source_label}]" if source_label else label
    detail = " | ".join(detail_parts) or "unknown"
    return f"{detail}\n[{source_label}]" if source_label else detail


def gic_open_space_mask(frame: pd.DataFrame) -> pd.Series:
    """Recognize both the legacy numeric code and schema-0.2 vocabulary."""
    if frame.empty:
        return pd.Series(False, index=frame.index, dtype=bool)
    codes = frame["luhk_class_code"].astype(str).str.casefold()
    names = frame["luhk_class_name"].astype(str).str.casefold()
    return (
        codes.isin({"31", "gic_open_space"})
        | names.str.contains("gic", regex=False)
        | names.str.contains("open space", regex=False)
    )


def describe(values: np.ndarray) -> dict[str, float | int]:
    clean = np.asarray(values, dtype=float)
    clean = clean[np.isfinite(clean)]
    if not clean.size:
        return {
            "n": 0, "mean": np.nan, "median": np.nan, "std": np.nan,
            "min": np.nan, "q05": np.nan, "q25": np.nan, "q75": np.nan,
            "q95": np.nan, "max": np.nan,
        }
    return {
        "n": int(clean.size),
        "mean": float(clean.mean()),
        "median": float(np.median(clean)),
        "std": float(clean.std(ddof=1)) if clean.size > 1 else np.nan,
        "min": float(clean.min()),
        "q05": float(np.quantile(clean, 0.05)),
        "q25": float(np.quantile(clean, 0.25)),
        "q75": float(np.quantile(clean, 0.75)),
        "q95": float(np.quantile(clean, 0.95)),
        "max": float(clean.max()),
    }


def kde_assessment(values: np.ndarray, config: dict[str, Any]) -> tuple[str, str]:
    spectrum = config["spectrum"]
    minimum_n = int(config["sampling"]["minimum_pixels_for_formal_plot"])
    clean = np.asarray(values, dtype=float)
    clean = clean[np.isfinite(clean)]
    if clean.size < minimum_n:
        return "insufficient_sample", f"sampled n < {minimum_n}"
    if np.unique(clean).size < int(spectrum["minimum_unique_values_for_kde"]):
        return "insufficient_variation", "too few unique delta-T values for KDE"
    if float(clean.std(ddof=1)) < float(spectrum["near_constant_std_c"]):
        return "near_constant", "sampled delta-T standard deviation is below the KDE threshold"
    return "eligible", ""


def density(values: np.ndarray, config: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    clean = np.asarray(values, dtype=float)
    clean = clean[np.isfinite(clean)]
    x = np.linspace(clean.min(), clean.max(), int(config["spectrum"]["kde_grid_points"]))
    kde = stats.gaussian_kde(clean, bw_method=config["spectrum"]["kde_bandwidth_method"])
    return x, kde(x)


def coverage_lookup(coverage: pd.DataFrame) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (str(row.analysis_family), str(row.group_name)): row._asdict()
        for row in coverage.itertuples(index=False)
    }


def make_summary_rows(
    samples: dict[str, pd.DataFrame], coverage: pd.DataFrame, config: dict[str, Any]
) -> pd.DataFrame:
    lookup = coverage_lookup(coverage)
    seed = int(config["sampling"]["primary_seed"])
    method = str(config["sampling"]["method"])
    rows: list[dict[str, Any]] = []

    def add_row(
        analysis_family: str,
        source_family: str,
        group_name: str,
        group: pd.DataFrame,
        coverage_key: tuple[str, str] | None,
        forced_status: str | None = None,
        forced_reason: str = "",
    ) -> None:
        info = lookup.get(coverage_key, {}) if coverage_key else {}
        values = group["delta_t_c"].to_numpy(float)
        summary = describe(values)
        status, reason = kde_assessment(values, config)
        if forced_status:
            status, reason = forced_status, forced_reason
        fallback_full = 0 if group.empty else group["source_population_count"].max()
        rows.append({
            "analysis_family": analysis_family,
            "group_name": group_name,
            "display_name": readable_group(group_name, analysis_family),
            "n_pixels_full": int(info.get("full_eligible_pixel_count", fallback_full)),
            "n_pixels_sampled": int(summary["n"]),
            "n_images": int(group["image_id"].nunique()),
            "n_images_full": int(info.get("full_image_count", group["image_id"].nunique())),
            "mean_sampled": summary["mean"],
            "median_sampled": summary["median"],
            "std_sampled": summary["std"],
            "min_sampled": summary["min"],
            "q05_sampled": summary["q05"],
            "q25_sampled": summary["q25"],
            "q75_sampled": summary["q75"],
            "q95_sampled": summary["q95"],
            "max_sampled": summary["max"],
            "sampling_seed": seed,
            "sampling_method": method,
            "kde_status": status,
            "kde_bandwidth_method": config["spectrum"]["kde_bandwidth_method"] if status == "eligible" else "not_applied",
            "eligibility_or_skipped_reason": reason,
            "source_sample_family": source_family,
        })

    overall = samples["image_comparison"]
    overall_info = coverage.loc[coverage["analysis_family"].eq("image_comparison")]
    overall_full = int(overall_info["full_eligible_pixel_count"].sum())
    overall_copy = overall.copy()
    overall_copy["source_population_count"] = overall_full
    overall_name = "All accepted schema-0.2 delta-temperature pixels"
    add_row(
        "overall", "image_comparison", overall_name, overall_copy, None,
        "unavailable" if overall.empty else None,
        "no compatible finite delta-temperature pixels" if overall.empty else "",
    )
    rows[-1]["n_pixels_full"] = overall_full
    rows[-1]["n_images_full"] = int(overall_info["full_image_count"].sum())

    for family in ("luhk", "surface_cover", "image_comparison"):
        for group_name, group in samples[family].groupby("group_name", sort=True):
            add_row(family, family, str(group_name), group, (family, str(group_name)))

    gic = samples["luhk_surface_cover"].loc[gic_open_space_mask(samples["luhk_surface_cover"])]
    for group_name, group in gic.groupby("group_name", sort=True):
        add_row(
            "within_gic_surface_cover", "luhk_surface_cover", str(group_name), group,
            ("luhk_surface_cover", str(group_name)),
        )

    shadow_flags = set(samples["surface_cover_shadow"]["shadow_flag"].dropna().astype(int).unique())
    shadow_estimable = shadow_flags.issuperset({0, 1})
    shadow_reason = "both shadow states are not available for a within-cover contrast"
    for group_name, group in samples["surface_cover_shadow"].groupby("group_name", sort=True):
        add_row(
            "surface_cover_shadow", "surface_cover_shadow", str(group_name), group,
            ("surface_cover_shadow", str(group_name)),
            None if shadow_estimable else "not_estimable_as_contrast",
            "" if shadow_estimable else shadow_reason,
        )
    return pd.DataFrame(rows)


def _figure_note(config: dict[str, Any]) -> str:
    method = str(config["sampling"]["method"]).replace("_", " ")
    return (
        f"Sampled original thermal pixels; seed {config['sampling']['primary_seed']}; "
        f"{method}. Density is normalized within group, not pixel count. "
        "Spatial thinning disperses pixels but does not remove spatial autocorrelation."
    )


def save_figure(fig: plt.Figure, directory: Path, stem: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    fig.savefig(directory / f"{stem}.png", dpi=220, facecolor="white", bbox_inches="tight")
    fig.savefig(directory / f"{stem}.pdf", facecolor="white", bbox_inches="tight")
    plt.close(fig)


def unavailable_figure(directory: Path, stem: str, title: str, reason: str) -> None:
    """Write an explicit QA figure instead of failing or inventing a group."""
    fig, ax = plt.subplots(figsize=(11, 5.5), facecolor="white")
    ax.axis("off")
    ax.text(0.5, 0.62, title, ha="center", va="center", fontsize=16, weight="bold")
    ax.text(0.5, 0.42, f"Not available: {reason}", ha="center", va="center", fontsize=12, color="#9C2F2F")
    ax.text(0.5, 0.25, "No observations were fabricated for this optional analysis family.", ha="center", va="center", fontsize=10)
    save_figure(fig, directory, stem)


def _prepare_density_data(
    sample: pd.DataFrame, summary: pd.DataFrame, family: str, config: dict[str, Any]
) -> tuple[list[dict[str, Any]], tuple[float, float], float]:
    items: list[dict[str, Any]] = []
    if sample.empty:
        return items, (0.0, 1.0), 0.0
    values_all = sample["delta_t_c"].to_numpy(float)
    x_limits = (float(values_all.min()), float(values_all.max()))
    ymax = 0.0
    for group_name, group in sample.groupby("group_name", sort=True):
        row = summary.loc[
            summary["analysis_family"].eq(family) & summary["group_name"].eq(str(group_name))
        ].iloc[0]
        values = group["delta_t_c"].to_numpy(float)
        x = y = None
        if row["kde_status"] == "eligible":
            x, y = density(values, config)
            ymax = max(ymax, float(y.max()))
        items.append({"group_name": str(group_name), "group": group, "row": row, "x": x, "y": y})
    return items, x_limits, ymax


def density_facets(
    sample: pd.DataFrame,
    summary: pd.DataFrame,
    family: str,
    title: str,
    stem: str,
    directory: Path,
    config: dict[str, Any],
) -> None:
    items, x_limits, ymax = _prepare_density_data(sample, summary, family, config)
    if not items:
        unavailable_figure(directory, stem, title, f"no eligible {family} observations")
        return
    columns = 2 if len(items) > 1 else 1
    rows = math.ceil(len(items) / columns)
    fig, axes = plt.subplots(
        rows, columns, figsize=(14, max(4.5, 3.35 * rows)), sharex=True, sharey=True,
        facecolor="white", squeeze=False,
    )
    for index, (ax, item) in enumerate(zip(axes.flat, items)):
        color = PALETTE[index % len(PALETTE)]
        group = item["group"]
        row = item["row"]
        values = group["delta_t_c"].to_numpy(float)
        ax.axvline(0, color="#666666", linewidth=1.0, linestyle="--", zorder=1)
        if item["x"] is not None:
            ax.plot(item["x"], item["y"], color=color, linewidth=2.2)
            ax.fill_between(item["x"], item["y"], color=color, alpha=0.18)
            ax.axvline(row["median_sampled"], color="#222222", linewidth=1.4, label="Median")
            ax.axvline(row["mean_sampled"], color="#222222", linewidth=1.2, linestyle=":", label="Mean")
            ax.axvspan(row["q25_sampled"], row["q75_sampled"], color=color, alpha=0.08)
        else:
            shown = values if values.size <= 250 else values[:250]
            ax.plot(shown, np.full(shown.size, max(ymax * 0.04, 0.001)), "|", color=color, alpha=0.7)
            ax.text(
                0.5, 0.55, f"KDE not drawn\n{row['eligibility_or_skipped_reason']}",
                transform=ax.transAxes, ha="center", va="center", color="#9C2F2F", fontsize=10,
            )
        label = readable_group(item["group_name"], family)
        ax.set_title(textwrap.fill(label, 45), fontsize=11.5, loc="left")
        ax.text(
            0.99, 0.94,
            f"sample n={int(row['n_pixels_sampled']):,} / full n={int(row['n_pixels_full']):,}\n"
            f"images={int(row['n_images'])}/{int(row['n_images_full'])}",
            transform=ax.transAxes, ha="right", va="top", fontsize=8.7,
            bbox={"boxstyle": "round,pad=0.25", "facecolor": "white", "edgecolor": "#DDDDDD", "alpha": 0.9},
        )
        ax.set_xlim(*x_limits)
        ax.set_ylim(0, ymax * 1.12 if ymax else 1)
        ax.grid(axis="x", alpha=0.16)
    for ax in axes.flat[len(items):]:
        ax.axis("off")
    for ax in axes[-1, :]:
        if ax.get_visible():
            ax.set_xlabel("ΔT (°C)", fontsize=11)
    for ax in axes[:, 0]:
        ax.set_ylabel("Density", fontsize=11)
    fig.suptitle(title, fontsize=16, y=0.985)
    fig.text(0.01, 0.012, _figure_note(config), fontsize=9)
    fig.tight_layout(rect=[0, 0.055, 1, 0.955])
    save_figure(fig, directory, stem)


def overall_figure(
    sample: pd.DataFrame, summary: pd.DataFrame, directory: Path, config: dict[str, Any]
) -> None:
    if sample.empty:
        unavailable_figure(
            directory, FIGURE_STEMS[0], "Overall pixel-level delta-temperature density spectrum",
            "no compatible finite ambient/delta-temperature observations",
        )
        return
    row = summary.loc[summary["analysis_family"].eq("overall")].iloc[0]
    values = sample["delta_t_c"].to_numpy(float)
    fig, ax = plt.subplots(figsize=(12, 6.7), facecolor="white")
    status, reason = kde_assessment(values, config)
    if status == "eligible":
        x, y = density(values, config)
        ax.fill_between(x, y, color=PALETTE[0], alpha=0.2)
        ax.plot(x, y, color=PALETTE[0], linewidth=2.4)
    else:
        shown = values if values.size <= 500 else values[:500]
        ax.plot(shown, np.full(shown.size, 0.01), "|", color=PALETTE[0], alpha=0.7)
        ax.text(0.5, 0.65, f"KDE not drawn: {reason}", transform=ax.transAxes, ha="center", color="#9C2F2F")
    ax.axvspan(row["q25_sampled"], row["q75_sampled"], color=PALETTE[0], alpha=0.08, label="Q25–Q75")
    ax.axvline(0, color="#666666", linewidth=1.1, linestyle="--", label="ΔT = 0")
    ax.axvline(row["median_sampled"], color="#222222", linewidth=1.5, label="Median")
    ax.axvline(row["mean_sampled"], color="#222222", linewidth=1.3, linestyle=":", label="Mean")
    ax.set_xlim(float(values.min()), float(values.max()))
    ax.set_ylim(bottom=0)
    ax.set_xlabel("ΔT (°C)", fontsize=12)
    ax.set_ylabel("Density", fontsize=12)
    ax.set_title("Overall pixel-level ΔT density spectrum", fontsize=16, pad=12)
    ax.grid(axis="x", alpha=0.18)
    ax.legend(frameon=False, ncol=4, loc="upper right")
    ax.text(
        0.01, 0.96,
        f"sample n={int(row['n_pixels_sampled']):,} / full n={int(row['n_pixels_full']):,}; "
        f"images={int(row['n_images'])}/{int(row['n_images_full'])}",
        transform=ax.transAxes, va="top", fontsize=10,
    )
    fig.text(0.01, 0.012, _figure_note(config), fontsize=9)
    fig.tight_layout(rect=[0, 0.055, 1, 1])
    save_figure(fig, directory, FIGURE_STEMS[0])


def overlay_figure(
    gic: pd.DataFrame, summary: pd.DataFrame, directory: Path, config: dict[str, Any]
) -> list[str]:
    minimum_n = int(config["sampling"]["minimum_pixels_for_formal_plot"])
    minimum_images = int(config["spectrum"]["overlay_minimum_images"])
    selected: list[tuple[str, pd.DataFrame, pd.Series]] = []
    for group_name, group in gic.groupby("group_name", sort=True):
        row = summary.loc[
            summary["analysis_family"].eq("within_gic_surface_cover")
            & summary["group_name"].eq(str(group_name))
        ].iloc[0]
        if (
            row["kde_status"] == "eligible"
            and int(row["n_pixels_sampled"]) >= minimum_n
            and int(row["n_images"]) >= minimum_images
        ):
            selected.append((str(group_name), group, row))
    if not selected:
        unavailable_figure(
            directory, FIGURE_STEMS[4], "Within-GIC surface-cover delta-temperature spectrum overlay",
            "no groups meet the configured pixel/image/variation inclusion rule",
        )
        return []
    values_all = np.concatenate([group["delta_t_c"].to_numpy(float) for _, group, _ in selected])
    fig, ax = plt.subplots(figsize=(12.5, 7.2), facecolor="white")
    ax.axvline(0, color="#666666", linewidth=1.1, linestyle="--", label="ΔT = 0")
    included: list[str] = []
    for index, (group_name, group, row) in enumerate(selected):
        color = PALETTE[index % len(PALETTE)]
        x, y = density(group["delta_t_c"].to_numpy(float), config)
        label = readable_group(group_name, "within_gic_surface_cover")
        included.append(label)
        ax.plot(x, y, color=color, linewidth=2.2, label=f"{label} (n={len(group):,})")
        ax.plot([row["median_sampled"]], [0], marker="|", markersize=12, markeredgewidth=2, color=color)
    ax.set_xlim(float(values_all.min()), float(values_all.max()))
    ax.set_ylim(bottom=0)
    ax.set_xlabel("ΔT (°C)", fontsize=12)
    ax.set_ylabel("Density", fontsize=12)
    ax.set_title("Within-GIC pixel-level ΔT density spectrum overlay", fontsize=16, pad=12)
    ax.grid(axis="x", alpha=0.18)
    ax.legend(frameon=False, loc="upper right", fontsize=9.5)
    fig.text(
        0.01, 0.012,
        _figure_note(config)
        + f" Overlay rule: sampled n≥{minimum_n} and ≥{minimum_images} contributing images; colored baseline ticks mark medians.",
        fontsize=8.7,
    )
    fig.tight_layout(rect=[0, 0.07, 1, 1])
    save_figure(fig, directory, FIGURE_STEMS[4])
    return included


def stability_figure(
    stability: pd.DataFrame, coverage: pd.DataFrame, directory: Path, config: dict[str, Any]
) -> None:
    groups = stability.loc[
        stability["record_type"].eq("group") & stability["analysis_family"].eq("surface_cover")
    ].copy()
    if groups.empty:
        unavailable_figure(
            directory, FIGURE_STEMS[6], "Sampling-stability distribution",
            "no eligible surface-cover observations across configured seeds",
        )
        return
    order = (
        groups.groupby("group_a")["sampled_median_a"].median().sort_values().index.tolist()
    )
    values = [groups.loc[groups["group_a"].eq(name), "sampled_median_a"].to_numpy(float) for name in order]
    fig, ax = plt.subplots(figsize=(12, 7), facecolor="white")
    boxes = ax.boxplot(
        values,
        orientation="horizontal",
        tick_labels=[readable_group(x, "surface_cover") for x in order],
        patch_artist=True,
        showfliers=True,
    )
    for patch, color in zip(boxes["boxes"], PALETTE):
        patch.set_facecolor(color)
        patch.set_alpha(0.55)
    primary_seed = int(config["sampling"]["primary_seed"])
    for y, group_name in enumerate(order, start=1):
        primary = groups.loc[
            groups["group_a"].eq(group_name) & groups["sampling_seed"].eq(primary_seed),
            "sampled_median_a",
        ]
        if not primary.empty:
            ax.plot(primary.iloc[0], y, marker="D", color="#222222", markersize=5)
    ax.axvline(0, color="#666666", linewidth=1.0, linestyle="--")
    ax.set_xlabel("Sampled median ΔT (°C) across deterministic seeds", fontsize=12)
    ax.set_ylabel("Physical surface cover", fontsize=12)
    ax.set_title("Sampling-stability distribution of pixel-level ΔT medians", fontsize=16, pad=12)
    ax.grid(axis="x", alpha=0.18)
    seed_count = int(groups["sampling_seed"].nunique())
    total_full = int(coverage.loc[coverage["analysis_family"].eq("surface_cover"), "full_eligible_pixel_count"].sum())
    fig.text(
        0.01, 0.012,
        f"Each box summarizes {seed_count} spatially thinned sampled-pixel medians; diamonds mark primary seed {primary_seed}. "
        f"Full eligible cover-labelled population n={total_full:,}. Spatial autocorrelation remains.",
        fontsize=9,
    )
    fig.tight_layout(rect=[0, 0.055, 1, 1])
    save_figure(fig, directory, FIGURE_STEMS[6])


def bootstrap_median_ci(
    values: np.ndarray, seed: int, repetitions: int, confidence: float
) -> tuple[float, float, float]:
    clean = np.asarray(values, dtype=float)
    rng = np.random.default_rng(seed)
    estimates = np.empty(repetitions, dtype=float)
    for index in range(repetitions):
        estimates[index] = np.median(rng.choice(clean, size=clean.size, replace=True))
    alpha = (1.0 - confidence) / 2.0
    return float(np.median(clean)), float(np.quantile(estimates, alpha)), float(np.quantile(estimates, 1 - alpha))


def uncertainty_figure(
    cover: pd.DataFrame, summary: pd.DataFrame, directory: Path, config: dict[str, Any]
) -> pd.DataFrame:
    repetitions = int(config["statistics"]["bootstrap_repetitions"])
    confidence = float(config["spectrum"]["bootstrap_confidence_level"])
    primary_seed = int(config["sampling"]["primary_seed"])
    rows: list[dict[str, Any]] = []
    for group_name, group in cover.groupby("group_name", sort=True):
        seed = primary_seed + zlib.crc32(str(group_name).encode("utf-8"))
        median, lower, upper = bootstrap_median_ci(
            group["delta_t_c"].to_numpy(float), seed, repetitions, confidence
        )
        rows.append({
            "group_name": str(group_name), "median": median, "lower": lower,
            "upper": upper, "n": len(group),
        })
    if not rows:
        unavailable_figure(
            directory, FIGURE_STEMS[7], "Bootstrap uncertainty summary",
            "no eligible surface-cover observations",
        )
        return pd.DataFrame(columns=["group_name", "median", "lower", "upper", "n"])
    frame = pd.DataFrame(rows).sort_values("median").reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(11.5, 6.8), facecolor="white")
    y = np.arange(len(frame))
    medians = frame["median"].to_numpy(float)
    ax.errorbar(
        medians, y,
        xerr=np.vstack([medians - frame["lower"].to_numpy(float), frame["upper"].to_numpy(float) - medians]),
        fmt="o", color=PALETTE[0], ecolor="#555555", capsize=5, linewidth=1.4,
    )
    ax.axvline(0, color="#666666", linewidth=1.0, linestyle="--")
    ax.set_yticks(y, [f"{readable_group(row.group_name, 'surface_cover')} (n={row.n:,})" for row in frame.itertuples(index=False)])
    ax.set_xlabel("Median ΔT (°C) with 95% percentile bootstrap CI", fontsize=12)
    ax.set_ylabel("Physical surface cover", fontsize=12)
    ax.set_title("Uncertainty summary for sampled-pixel ΔT spectra", fontsize=16, pad=12)
    ax.grid(axis="x", alpha=0.18)
    fig.text(
        0.01, 0.012,
        f"{repetitions:,} deterministic pixel-resampling replicates per cover; primary sample seed {primary_seed}. "
        "Intervals are descriptive because neighbouring pixels remain spatially correlated.",
        fontsize=9,
    )
    fig.tight_layout(rect=[0, 0.055, 1, 1])
    save_figure(fig, directory, FIGURE_STEMS[7])
    return frame


def counts_text(summary: pd.DataFrame, family: str, only_groups: list[str] | None = None) -> str:
    selected = summary.loc[summary["analysis_family"].eq(family)]
    if only_groups is not None:
        selected = selected.loc[selected["display_name"].isin(only_groups)]
    return "; ".join(
        f"{row.display_name}: {int(row.n_pixels_sampled):,}/{int(row.n_pixels_full):,} pixels, "
        f"{int(row.n_images)}/{int(row.n_images_full)} images"
        for row in selected.itertuples(index=False)
    )


def write_captions(
    summary: pd.DataFrame,
    included_overlay: list[str],
    config: dict[str, Any],
    directory: Path,
) -> None:
    seed = int(config["sampling"]["primary_seed"])
    method = config["sampling"]["method"]
    common = (
        f"One observation is one accepted finite thermal pixel with ΔT = temperature − image-level ambient temperature. "
        f"Pixels were selected with {method} (primary seed {seed}); original pixel ΔT values were retained. "
        "Density is normalized within each group and does not encode pixel count. "
        "Spatial thinning improves dispersion but does not remove spatial autocorrelation, so pixels are not described as independent."
    )
    overall = summary.loc[summary["analysis_family"].eq("overall")].iloc[0]
    image_count = int(overall["n_images_full"])
    shadow_rows = summary.loc[summary["analysis_family"].eq("surface_cover_shadow")]
    shadow_estimable = not shadow_rows.empty and shadow_rows["kde_status"].ne("not_estimable_as_contrast").any()
    shadow_text = (
        "Both shadow states occur in eligible schema-0.2 samples; formal contrast results are reported in the statistical tables."
        if shadow_estimable
        else "Status: **not estimable** because both valid shadow states are not available. No observations were fabricated."
    )
    lines = [
        "# Formal Part E pixel-level ΔT spectrum figure captions",
        "",
        "Spectrum means the statistical distribution/density spectrum of pixel-level ΔT; it is not an electromagnetic or multispectral spectrum.",
        "",
        "## Figure 00 — Overall pixel-level ΔT density spectrum",
        "",
        f"Accepted finite delta-temperature pixels from {image_count} schema-0.2 images are represented by the source- and image-stratified sampled-pixel dataset "
        f"(sampled n={int(overall['n_pixels_sampled']):,}; full eligible n={int(overall['n_pixels_full']):,}; "
        f"{int(overall['n_images'])}/{int(overall['n_images_full'])} images). The curve uses SciPy Gaussian KDE with Scott's bandwidth rule and is evaluated only across the observed sampled range. {common}",
        "",
        "## Figure 01 — Pixel-level ΔT spectrum by LUHK class",
        "",
        f"Eligibility requires an accepted finite pixel and a valid approximate LUHK label. {counts_text(summary, 'luhk')}. "
        f"Groups below {config['sampling']['minimum_pixels_for_formal_plot']} sampled pixels are shown without a smoothed KDE. "
        f"Directly compared facets share x and y scales; KDEs use Scott's rule and stop at each group's observed range. {common}",
        "",
        "## Figure 02 — Pixel-level ΔT spectrum by physical surface cover",
        "",
        f"Eligibility requires an accepted finite pixel and a reviewed valid physical-cover label. {counts_text(summary, 'surface_cover')}. "
        f"Facets share comparison scales; KDEs use Scott's rule and stop at observed group ranges. {common}",
        "",
        "## Figure 03 — Within-GIC pixel-level ΔT spectrum by physical surface cover",
        "",
        f"Eligibility additionally requires legacy LUHK code 31 or schema-0.2 `gic_open_space`. {counts_text(summary, 'within_gic_surface_cover')}. "
        f"Facets share comparison scales; KDEs use Scott's rule and stop at observed group ranges. {common}",
        "",
        "## Figure 04 — Within-GIC surface-cover ΔT spectrum overlay",
        "",
        f"The overlay includes groups with at least {config['sampling']['minimum_pixels_for_formal_plot']} sampled pixels, at least "
        f"{config['spectrum']['overlay_minimum_images']} contributing images, and adequate variation for KDE: {', '.join(included_overlay) or 'none'}. "
        f"Colored baseline ticks mark medians; Scott-rule KDEs are normalized per group and stop at observed ranges. {common}",
        "",
        "## Figure 05 — Pixel-level ΔT spectrum by image",
        "",
        f"Eligibility is any accepted finite delta-temperature pixel in the schema-0.2 result set. {counts_text(summary, 'image_comparison')}. "
        f"Facets use a common comparison scale and Scott-rule KDEs evaluated only over observed image ranges. {common}",
        "",
        "## Figure 06 — Surface-cover × shadow spectrum",
        "",
        shadow_text,
        "",
        "## Figure 07 — Sampling-stability distribution",
        "",
        f"Boxes summarize surface-cover sampled medians across the primary seed and {len(config['sampling']['secondary_seeds'])} secondary seeds; diamonds mark seed {seed}. "
        f"Each seed selects dispersed original pixels with {method}; no tile or pixel mean is substituted. Spatial autocorrelation remains, and the display describes seed sensitivity rather than inferential uncertainty.",
        "",
        "## Figure 08 — Bootstrap uncertainty summary",
        "",
        f"Points show sampled-pixel median ΔT and percentile 95% bootstrap intervals from {config['statistics']['bootstrap_repetitions']:,} deterministic resamples. "
        f"Eligibility is the same as Figure 02; counts are {counts_text(summary, 'surface_cover')}. Intervals are descriptive because ordinary pixel resampling does not account fully for neighbouring-pixel spatial correlation. {common}",
    ]
    write_markdown(directory / "part_e_spectrum_figure_captions.md", lines)


def write_generation_summary(
    summary: pd.DataFrame, directory: Path, config: dict[str, Any]
) -> None:
    rows = summary.loc[summary["kde_status"].ne("eligible")]
    lines = [
        "# Part E formal pixel-level ΔT spectrum generation summary",
        "",
        "- Status: complete.",
        "- Formal observation: one accepted finite thermal pixel.",
        f"- Primary sampling seed: {config['sampling']['primary_seed']}.",
        f"- Sampling method: `{config['sampling']['method']}`.",
        f"- KDE: SciPy `gaussian_kde`, `{config['spectrum']['kde_bandwidth_method']}` bandwidth, evaluated only within each group's observed sampled range.",
        "- Shadow comparison is conditional on both valid shadow states; unavailable families remain explicit QA exceptions.",
        "- Spatial limitation: thinning disperses selected pixels but does not eliminate spatial autocorrelation.",
        "",
        "## Written figures",
        "",
    ]
    for stem in FIGURE_STEMS:
        figure_path = directory / (stem + ".png")
        try:
            display_path = figure_path.relative_to(project_path(".")).as_posix()
        except ValueError:
            display_path = figure_path.resolve().as_posix()
        lines.append(f"- `{display_path}` and PDF counterpart")
    lines.extend([
        "",
        "Figure 06 remains a table-level shadow contrast in this preserved formal family; availability is documented in captions and statistical tables.",
        "",
        "## KDE exceptions",
        "",
    ])
    if rows.empty:
        lines.append("- None.")
    else:
        for row in rows.itertuples(index=False):
            lines.append(
                f"- `{row.analysis_family}` / `{row.group_name}`: `{row.kde_status}` — {row.eligibility_or_skipped_reason}."
            )
    write_markdown(
        project_path(config["outputs"]["summaries"]) / "part_e_pixel_delta_t_spectrum_generation_summary.md",
        lines,
    )


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    ensure_output_directories(config)
    directory = project_path(config["outputs"]["spectrum_figures"])
    tables = project_path(config["outputs"]["tables"])
    coverage_path = tables / "part_e_pixel_sample_coverage.csv"
    stability_path = tables / "part_e_sampling_stability.csv"
    if not coverage_path.is_file() or not stability_path.is_file():
        raise FileNotFoundError("Completed sample coverage and sampling-stability tables are required")
    coverage = pd.read_csv(coverage_path)
    stability = pd.read_csv(stability_path)
    samples = {family: read_sample(config, family) for family in SAMPLE_FILES}
    seed = int(config["sampling"]["primary_seed"])
    for family, sample in samples.items():
        if sample.empty:
            continue
        seeds = set(sample["sampling_seed"].astype(int).unique())
        if seeds != {seed}:
            raise ValueError(f"{family} sample seed mismatch: expected {seed}, found {sorted(seeds)}")

    summary = make_summary_rows(samples, coverage, config)
    summary_path = tables / "part_e_pixel_delta_t_spectrum_summary.csv"
    write_csv(summary_path, summary)

    overall_figure(samples["image_comparison"], summary, directory, config)
    density_facets(
        samples["luhk"], summary, "luhk", "Pixel-level ΔT density spectrum by LUHK class",
        FIGURE_STEMS[1], directory, config,
    )
    density_facets(
        samples["surface_cover"], summary, "surface_cover",
        "Pixel-level ΔT density spectrum by physical surface cover",
        FIGURE_STEMS[2], directory, config,
    )
    gic = samples["luhk_surface_cover"].loc[gic_open_space_mask(samples["luhk_surface_cover"])].copy()
    density_facets(
        gic, summary, "within_gic_surface_cover",
        "Within-GIC pixel-level ΔT density spectrum by physical surface cover",
        FIGURE_STEMS[3], directory, config,
    )
    included_overlay = overlay_figure(gic, summary, directory, config)
    density_facets(
        samples["image_comparison"], summary, "image_comparison",
        "Pixel-level ΔT density spectrum by image",
        FIGURE_STEMS[5], directory, config,
    )
    stability_figure(stability, coverage, directory, config)
    ci = uncertainty_figure(samples["surface_cover"], summary, directory, config)
    ci_lookup = ci.set_index("group_name")
    mask = summary["analysis_family"].eq("surface_cover")
    summary.loc[mask, "bootstrap_median_ci_lower"] = summary.loc[mask, "group_name"].map(ci_lookup["lower"])
    summary.loc[mask, "bootstrap_median_ci_upper"] = summary.loc[mask, "group_name"].map(ci_lookup["upper"])
    write_csv(summary_path, summary)
    write_captions(summary, included_overlay, config, directory)
    write_generation_summary(summary, directory, config)
    print(f"Formal spectrum figures written: {len(FIGURE_STEMS)} PNG/PDF pairs")
    print("Shadow spectrum status: not estimable; no shadow comparison figure written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
