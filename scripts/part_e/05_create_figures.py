#!/usr/bin/env python3
"""Create publication-style provisional Part E figures."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("MPLCONFIGDIR", str(PROJECT_ROOT / ".matplotlib-cache"))

SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

from part_e.part_e_common import (  # noqa: E402
    PART_E_FIGURE_DIR,
    PART_E_SUMMARY_DIR,
    PART_E_TABLE_DIR,
    PROVISIONAL_NOTICE,
    read_dataset,
    relative_posix,
    write_markdown,
)


CELL_DATA = PART_E_TABLE_DIR / "part_e_cell_delta_t_observations_all_finite.csv"
COVER_DATA = PART_E_TABLE_DIR / "part_e_surface_cover_delta_t_observations_all_finite.csv"
FIGURE_SUMMARY_MD = PART_E_SUMMARY_DIR / "part_e_figure_generation_summary.md"


def valid_numeric(df: pd.DataFrame, value_col: str) -> pd.DataFrame:
    work = df.loc[pd.to_numeric(df.get("analysis_valid", 0), errors="coerce").fillna(0).astype(int).eq(1)].copy()
    work[value_col] = pd.to_numeric(work[value_col], errors="coerce")
    return work.dropna(subset=[value_col])


def save_boxplot(df: pd.DataFrame, group_col: str, value_col: str, title: str, ylabel: str, path: Path) -> None:
    work = valid_numeric(df, value_col)
    labels = []
    values = []
    for label, group in work.groupby(group_col, sort=True):
        series = group[value_col].to_numpy(dtype=float)
        if series.size:
            labels.append(str(label))
            values.append(series)
    if not values:
        return
    fig_width = max(8, min(16, len(values) * 1.8))
    fig, ax = plt.subplots(figsize=(fig_width, 6), dpi=180)
    positions = np.arange(1, len(values) + 1)
    ax.boxplot(values, positions=positions, showmeans=True, patch_artist=True)
    ax.set_xticks(positions, labels=labels)
    for tick in ax.get_xticklabels():
        tick.set_rotation(30)
        tick.set_horizontalalignment("right")
    counts = [len(item) for item in values]
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.set_xlabel(group_col.replace("_", " "))
    ax.grid(axis="y", alpha=0.25)
    ax.text(0.01, 0.01, "n: " + ", ".join(f"{label}={count}" for label, count in zip(labels, counts)), transform=ax.transAxes, fontsize=8, va="bottom")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def save_histogram_by_group(df: pd.DataFrame, group_col: str, value_col: str, title: str, path: Path) -> None:
    work = valid_numeric(df, value_col)
    groups = [(str(label), group[value_col].to_numpy(dtype=float)) for label, group in work.groupby(group_col, sort=True)]
    groups = [(label, values) for label, values in groups if values.size]
    if not groups:
        return
    fig, ax = plt.subplots(figsize=(9, 6), dpi=180)
    bins = np.histogram_bin_edges(work[value_col].to_numpy(dtype=float), bins="auto")
    for label, values in groups:
        ax.hist(values, bins=bins, alpha=0.35, density=True, label=f"{label} (n={len(values)})")
    ax.set_title(title)
    ax.set_xlabel("Provisional delta-T (deg C)")
    ax.set_ylabel("Density")
    ax.grid(axis="y", alpha=0.25)
    ax.legend(fontsize=8)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def save_ecdf(df: pd.DataFrame, group_col: str, value_col: str, title: str, path: Path) -> None:
    work = valid_numeric(df, value_col)
    groups = [(str(label), group[value_col].to_numpy(dtype=float)) for label, group in work.groupby(group_col, sort=True)]
    groups = [(label, np.sort(values)) for label, values in groups if values.size]
    if not groups:
        return
    fig, ax = plt.subplots(figsize=(9, 6), dpi=180)
    for label, values in groups:
        y = np.arange(1, values.size + 1) / values.size
        ax.step(values, y, where="post", label=f"{label} (n={values.size})")
    ax.set_title(title)
    ax.set_xlabel("Provisional delta-T (deg C)")
    ax.set_ylabel("Empirical cumulative probability")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=8)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def save_grouped_boxplot(cover: pd.DataFrame, path: Path) -> None:
    work = valid_numeric(cover, "class_delta_t_mean_c")
    if work.empty:
        return
    combos = []
    labels = []
    for (luhk, cover_class), group in work.groupby(["luhk_aggregated_class", "physical_surface_cover_class"], sort=True):
        values = group["class_delta_t_mean_c"].to_numpy(dtype=float)
        if len(values):
            combos.append(values)
            labels.append(f"{luhk}\n{cover_class}")
    if not combos:
        return
    fig, ax = plt.subplots(figsize=(max(10, len(combos) * 1.2), 6.5), dpi=180)
    positions = np.arange(1, len(combos) + 1)
    ax.boxplot(combos, positions=positions, showmeans=True, patch_artist=True)
    ax.set_xticks(positions, labels=labels)
    for tick in ax.get_xticklabels():
        tick.set_rotation(45)
        tick.set_horizontalalignment("right")
    ax.set_title("Provisional Cell-Cover Delta-T By LUHK And Physical Surface Cover")
    ax.set_ylabel("Provisional delta-T (deg C)")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def save_heatmap(cover: pd.DataFrame, path: Path) -> None:
    work = valid_numeric(cover, "class_delta_t_mean_c")
    if work.empty:
        return
    pivot = work.pivot_table(
        index="luhk_aggregated_class",
        columns="physical_surface_cover_class",
        values="class_delta_t_mean_c",
        aggfunc="median",
    )
    if pivot.empty:
        return
    data = pivot.to_numpy(dtype=float)
    fig, ax = plt.subplots(figsize=(max(8, pivot.shape[1] * 1.4), max(4, pivot.shape[0] * 0.8)), dpi=180)
    im = ax.imshow(data, aspect="auto", cmap="coolwarm")
    ax.set_xticks(np.arange(pivot.shape[1]), labels=pivot.columns)
    ax.set_yticks(np.arange(pivot.shape[0]), labels=pivot.index)
    for tick in ax.get_xticklabels():
        tick.set_rotation(30)
        tick.set_horizontalalignment("right")
    for y in range(pivot.shape[0]):
        for x in range(pivot.shape[1]):
            value = data[y, x]
            label = "missing" if np.isnan(value) else f"{value:.2f}"
            ax.text(x, y, label, ha="center", va="center", fontsize=8)
    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label("Median provisional delta-T (deg C)")
    ax.set_title("Median Provisional Delta-T: LUHK x Physical Surface Cover")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def save_spatial_maps(cell: pd.DataFrame) -> list[Path]:
    work = cell.copy()
    work["delta_t_mean_c"] = pd.to_numeric(work["delta_t_mean_c"], errors="coerce")
    numeric = work["delta_t_mean_c"].dropna()
    if numeric.empty:
        return []
    scale = max(abs(float(numeric.quantile(0.05))), abs(float(numeric.quantile(0.95))))
    if scale == 0:
        scale = max(abs(float(numeric.min())), abs(float(numeric.max())), 1.0)
    generated = []
    for image_id, group in work.groupby("image_id", sort=True):
        fig, ax = plt.subplots(figsize=(8, 7), dpi=180)
        for _, row in group.iterrows():
            x = float(row["cell_min_x_2326"])
            y = float(row["cell_min_y_2326"])
            width = float(row["cell_max_x_2326"]) - float(row["cell_min_x_2326"])
            height = float(row["cell_max_y_2326"]) - float(row["cell_min_y_2326"])
            valid = int(row.get("analysis_valid", 0)) == 1 and pd.notna(row["delta_t_mean_c"])
            if valid:
                value = float(row["delta_t_mean_c"])
                color = plt.get_cmap("coolwarm")((value + scale) / (2 * scale))
                alpha = 0.85
                hatch = None
            else:
                color = "#dddddd"
                alpha = 0.45
                hatch = "///"
            ax.add_patch(Rectangle((x, y), width, height, facecolor=color, edgecolor="black", linewidth=0.2, alpha=alpha, hatch=hatch))
        ax.autoscale()
        ax.set_aspect("equal")
        ax.set_title(f"{image_id}: Provisional 10 m Cell Delta-T")
        ax.set_xlabel("Easting (EPSG:2326)")
        ax.set_ylabel("Northing (EPSG:2326)")
        ax.grid(alpha=0.2)
        sm = plt.cm.ScalarMappable(cmap="coolwarm", norm=plt.Normalize(vmin=-scale, vmax=scale))
        cbar = fig.colorbar(sm, ax=ax)
        cbar.set_label("Provisional delta-T (deg C)")
        fig.tight_layout()
        path = PART_E_FIGURE_DIR / "spatial" / f"{image_id}_cell_delta_t_map.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path)
        plt.close(fig)
        generated.append(path)
    return generated


def save_image_comparison(cell: pd.DataFrame, path: Path) -> None:
    work = valid_numeric(cell, "delta_t_mean_c")
    if work.empty:
        return
    grouped = work.groupby("image_id", sort=True).agg(
        mean_delta_t_c=("delta_t_mean_c", "mean"),
        median_delta_t_c=("delta_t_mean_c", "median"),
        mean_surface_temperature_c=("mean_surface_temperature_c", lambda s: pd.to_numeric(s, errors="coerce").mean()),
        ambient_temperature_c=("ambient_temperature_c", lambda s: pd.to_numeric(s, errors="coerce").median()),
        valid_cells=("cell_id", "count"),
    )
    fig, axes = plt.subplots(3, 1, figsize=(10, 9), dpi=180, sharex=True)
    x = np.arange(len(grouped))
    axes[0].bar(x, grouped["median_delta_t_c"])
    axes[0].set_ylabel("Median delta-T (deg C)")
    axes[0].set_title("Provisional Image-Level Comparison")
    axes[1].plot(x, grouped["ambient_temperature_c"], marker="o", label="Ambient")
    axes[1].plot(x, grouped["mean_surface_temperature_c"], marker="o", label="Mean surface")
    axes[1].set_ylabel("Temperature (deg C)")
    axes[1].legend()
    axes[2].bar(x, grouped["valid_cells"])
    axes[2].set_ylabel("Valid cells")
    axes[2].set_xticks(x, labels=grouped.index)
    for tick in axes[2].get_xticklabels():
        tick.set_rotation(30)
        tick.set_horizontalalignment("right")
    for ax in axes:
        ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def save_subzero_figures(cell: pd.DataFrame) -> list[Path]:
    work = cell.copy()
    work["below_0_c_pixel_fraction"] = pd.to_numeric(work["below_0_c_pixel_fraction"], errors="coerce")
    work["delta_t_mean_c"] = pd.to_numeric(work["delta_t_mean_c"], errors="coerce")
    generated = []
    by_image = work.groupby("image_id", sort=True)["below_0_c_pixel_fraction"].mean().dropna()
    if not by_image.empty:
        fig, ax = plt.subplots(figsize=(9, 5), dpi=180)
        by_image.plot(kind="bar", ax=ax)
        ax.set_title("Mean Cell Fraction Of Sub-Zero Pixels By Image")
        ax.set_ylabel("Mean fraction of mapped cell pixels below 0 deg C")
        ax.set_xlabel("Image ID")
        for tick in ax.get_xticklabels():
            tick.set_rotation(30)
            tick.set_horizontalalignment("right")
        fig.tight_layout()
        path = PART_E_FIGURE_DIR / "qa" / "subzero_fraction_by_image.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path)
        plt.close(fig)
        generated.append(path)
    scatter = work.dropna(subset=["below_0_c_pixel_fraction", "delta_t_mean_c"])
    if not scatter.empty:
        fig, ax = plt.subplots(figsize=(7, 5), dpi=180)
        ax.scatter(scatter["below_0_c_pixel_fraction"], scatter["delta_t_mean_c"], alpha=0.55, s=16)
        ax.set_title("Sub-Zero Pixel Fraction And Provisional Cell Delta-T")
        ax.set_xlabel("Fraction of mapped cell pixels below 0 deg C")
        ax.set_ylabel("Provisional delta-T (deg C)")
        ax.grid(alpha=0.25)
        fig.tight_layout()
        path = PART_E_FIGURE_DIR / "qa" / "subzero_fraction_vs_delta_t.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path)
        plt.close(fig)
        generated.append(path)
    return generated


def main() -> int:
    cell = read_dataset(CELL_DATA, "cell-level Part E dataset")
    cover = read_dataset(COVER_DATA, "cell-by-cover Part E dataset")
    generated: list[Path] = []

    figure_specs = [
        (lambda: save_boxplot(cell, "luhk_aggregated_class", "delta_t_mean_c", "Provisional Cell Delta-T By LUHK Class", "Provisional delta-T (deg C)", PART_E_FIGURE_DIR / "luhk" / "cell_delta_t_boxplot_by_luhk.png")),
        (lambda: save_histogram_by_group(cell, "luhk_aggregated_class", "delta_t_mean_c", "Provisional Cell Delta-T Distribution By LUHK Class", PART_E_FIGURE_DIR / "luhk" / "cell_delta_t_histogram_by_luhk.png")),
        (lambda: save_ecdf(cell, "luhk_aggregated_class", "delta_t_mean_c", "Provisional Cell Delta-T ECDF By LUHK Class", PART_E_FIGURE_DIR / "luhk" / "cell_delta_t_ecdf_by_luhk.png")),
        (lambda: save_boxplot(cover, "physical_surface_cover_class", "class_delta_t_mean_c", "Provisional Cell-Cover Delta-T By Physical Surface Cover", "Provisional delta-T (deg C)", PART_E_FIGURE_DIR / "surface_cover" / "cell_cover_delta_t_boxplot_by_surface_cover.png")),
        (lambda: save_histogram_by_group(cover, "physical_surface_cover_class", "class_delta_t_mean_c", "Provisional Cell-Cover Delta-T Distribution By Surface Cover", PART_E_FIGURE_DIR / "surface_cover" / "cell_cover_delta_t_histogram_by_surface_cover.png")),
        (lambda: save_boxplot(cell, "image_id", "delta_t_mean_c", "Provisional Cell Delta-T By Image", "Provisional delta-T (deg C)", PART_E_FIGURE_DIR / "image" / "cell_delta_t_boxplot_by_image.png")),
    ]
    for make_figure in figure_specs:
        before = set(PART_E_FIGURE_DIR.rglob("*.png")) if PART_E_FIGURE_DIR.exists() else set()
        make_figure()
        after = set(PART_E_FIGURE_DIR.rglob("*.png")) if PART_E_FIGURE_DIR.exists() else set()
        generated.extend(sorted(after - before))

    grouped_path = PART_E_FIGURE_DIR / "luhk_surface_cover" / "cell_cover_delta_t_grouped_boxplot_luhk_surface_cover.png"
    save_grouped_boxplot(cover, grouped_path)
    if grouped_path.exists():
        generated.append(grouped_path)
    heatmap_path = PART_E_FIGURE_DIR / "luhk_surface_cover" / "median_delta_t_luhk_surface_cover_heatmap.png"
    save_heatmap(cover, heatmap_path)
    if heatmap_path.exists():
        generated.append(heatmap_path)
    image_path = PART_E_FIGURE_DIR / "image" / "image_level_delta_t_temperature_cell_count.png"
    save_image_comparison(cell, image_path)
    if image_path.exists():
        generated.append(image_path)
    generated.extend(save_spatial_maps(cell))
    generated.extend(save_subzero_figures(cell))

    lines = [
        "# Part E Figure Generation Summary",
        "",
        f"**Provisional-result rule:** {PROVISIONAL_NOTICE}",
        "",
        "Shadow comparison figures are not generated unless `shadow_flag = 1` observations exist; the current pilot masks contain no shadow pixels.",
        "",
        "## Figures Written",
        "",
    ]
    lines.extend(f"- `{relative_posix(path)}`" for path in sorted(set(generated)))
    write_markdown(FIGURE_SUMMARY_MD, lines)
    print(f"Figures written: {len(set(generated))}")
    print(f"Figure summary: {relative_posix(FIGURE_SUMMARY_MD)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
