#!/usr/bin/env python3
"""Create clearer Part E delta-T density spectrum figures."""

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
SPECTRUM_DIR = PART_E_FIGURE_DIR / "spectrum"
SUMMARY_MD = PART_E_SUMMARY_DIR / "part_e_clear_spectrum_figure_summary.md"


COLORS = [
    "#1b9e77",
    "#d95f02",
    "#7570b3",
    "#e7298a",
    "#66a61e",
    "#e6ab02",
    "#a6761d",
    "#666666",
]


def valid_numeric(df: pd.DataFrame, value_col: str) -> pd.DataFrame:
    work = df.loc[pd.to_numeric(df.get("analysis_valid", 0), errors="coerce").fillna(0).astype(int).eq(1)].copy()
    work[value_col] = pd.to_numeric(work[value_col], errors="coerce")
    return work.dropna(subset=[value_col])


def density(values: np.ndarray, x_grid: np.ndarray) -> np.ndarray | None:
    values = values[np.isfinite(values)]
    if values.size < 3 or np.isclose(values.std(ddof=1), 0):
        return None
    try:
        from scipy.stats import gaussian_kde
    except Exception:
        return None
    kde = gaussian_kde(values)
    return kde(x_grid)


def ordered_groups(df: pd.DataFrame, group_col: str, value_col: str) -> list[tuple[str, np.ndarray]]:
    groups = []
    for label, group in df.groupby(group_col, sort=True):
        values = group[value_col].to_numpy(dtype=float)
        if values.size:
            groups.append((str(label), values))
    groups.sort(key=lambda item: (-item[1].size, item[0]))
    return groups


def spectrum_facets(
    df: pd.DataFrame,
    group_col: str,
    value_col: str,
    title: str,
    path: Path,
    min_density_n: int = 8,
) -> None:
    groups = ordered_groups(df, group_col, value_col)
    if not groups:
        return
    all_values = np.concatenate([values for _, values in groups])
    x_min = float(np.nanpercentile(all_values, 0.5))
    x_max = float(np.nanpercentile(all_values, 99.5))
    margin = max((x_max - x_min) * 0.08, 0.5)
    x_grid = np.linspace(x_min - margin, x_max + margin, 500)
    panel_count = len(groups)
    fig_height = max(4.2, 1.55 * panel_count + 1.2)
    fig, axes = plt.subplots(panel_count, 1, figsize=(11.5, fig_height), dpi=260, sharex=True)
    if panel_count == 1:
        axes = [axes]

    max_density = 0.0
    cached = []
    for label, values in groups:
        y = density(values, x_grid) if values.size >= min_density_n else None
        if y is not None:
            max_density = max(max_density, float(np.max(y)))
        cached.append((label, values, y))

    for index, (ax, (label, values, y)) in enumerate(zip(axes, cached)):
        color = COLORS[index % len(COLORS)]
        median = float(np.median(values))
        if y is not None:
            ax.fill_between(x_grid, y, color=color, alpha=0.22)
            ax.plot(x_grid, y, color=color, linewidth=2.0)
        else:
            baseline = max_density * 0.08 if max_density else 0.05
            ax.vlines(values, 0, baseline, color=color, alpha=0.65, linewidth=1.2)
            ax.text(
                0.99,
                0.68,
                "too few observations for KDE",
                transform=ax.transAxes,
                ha="right",
                va="center",
                fontsize=8,
                color="#555555",
            )
        ax.axvline(median, color=color, linewidth=1.4, linestyle="--")
        ax.axvline(0, color="#333333", linewidth=0.8, alpha=0.5)
        ax.set_ylabel("Density")
        ax.grid(axis="x", alpha=0.18)
        ax.grid(axis="y", alpha=0.12)
        ax.text(
            0.01,
            0.76,
            f"{label} | n={values.size} | median={median:.2f} deg C",
            transform=ax.transAxes,
            ha="left",
            va="center",
            fontsize=9,
            fontweight="bold",
        )
        if max_density:
            ax.set_ylim(0, max_density * 1.18)
    axes[0].set_title(title)
    axes[-1].set_xlabel("Provisional Delta-T (deg C)")
    fig.text(
        0.01,
        0.01,
        "Provisional pilot result; apparent-temperature plausibility review remains pending.",
        fontsize=8,
        color="#555555",
    )
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def spectrum_overlay(
    df: pd.DataFrame,
    group_col: str,
    value_col: str,
    title: str,
    path: Path,
    min_density_n: int = 8,
) -> None:
    groups = ordered_groups(df, group_col, value_col)
    groups = [(label, values) for label, values in groups if values.size >= min_density_n]
    if not groups:
        return
    all_values = np.concatenate([values for _, values in groups])
    x_min = float(np.nanpercentile(all_values, 0.5))
    x_max = float(np.nanpercentile(all_values, 99.5))
    margin = max((x_max - x_min) * 0.08, 0.5)
    x_grid = np.linspace(x_min - margin, x_max + margin, 600)
    fig, ax = plt.subplots(figsize=(11.5, 6.5), dpi=260)
    for index, (label, values) in enumerate(groups):
        y = density(values, x_grid)
        if y is None:
            continue
        color = COLORS[index % len(COLORS)]
        ax.plot(x_grid, y, color=color, linewidth=2.0, label=f"{label} (n={values.size}, median={np.median(values):.2f})")
        ax.fill_between(x_grid, y, color=color, alpha=0.08)
    ax.axvline(0, color="#333333", linewidth=0.9, alpha=0.6)
    ax.set_title(title)
    ax.set_xlabel("Provisional Delta-T (deg C)")
    ax.set_ylabel("Density")
    ax.grid(alpha=0.2)
    ax.legend(fontsize=8, frameon=False)
    fig.text(
        0.01,
        0.01,
        "Provisional pilot result; apparent-temperature plausibility review remains pending.",
        fontsize=8,
        color="#555555",
    )
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def main() -> int:
    cell = valid_numeric(read_dataset(CELL_DATA, "cell-level Part E dataset"), "delta_t_mean_c")
    cover = valid_numeric(read_dataset(COVER_DATA, "cell-cover Part E dataset"), "class_delta_t_mean_c")
    gic_cover = cover.loc[cover["luhk_aggregated_class"].astype(str).eq("GIC / open space")].copy()

    outputs = [
        SPECTRUM_DIR / "luhk_delta_t_density_spectrum_facets.png",
        SPECTRUM_DIR / "surface_cover_delta_t_density_spectrum_facets.png",
        SPECTRUM_DIR / "gic_surface_cover_delta_t_density_spectrum_facets.png",
        SPECTRUM_DIR / "gic_surface_cover_delta_t_density_spectrum_overlay.png",
    ]
    spectrum_facets(
        cell,
        "luhk_aggregated_class",
        "delta_t_mean_c",
        "Cell-Level Provisional Delta-T Density Spectrum By LUHK Class",
        outputs[0],
    )
    spectrum_facets(
        cover,
        "physical_surface_cover_class",
        "class_delta_t_mean_c",
        "Cell-Cover Provisional Delta-T Density Spectrum By Physical Surface Cover",
        outputs[1],
    )
    spectrum_facets(
        gic_cover,
        "physical_surface_cover_class",
        "class_delta_t_mean_c",
        "Within GIC / Open Space: Delta-T Density Spectrum By Surface Cover",
        outputs[2],
    )
    spectrum_overlay(
        gic_cover,
        "physical_surface_cover_class",
        "class_delta_t_mean_c",
        "Within GIC / Open Space: Surface-Cover Delta-T Density Overlay",
        outputs[3],
    )

    written = [path for path in outputs if path.exists()]
    lines = [
        "# Part E Clear Density Spectrum Figures",
        "",
        f"**Provisional-result rule:** {PROVISIONAL_NOTICE}",
        "",
        "These high-resolution spectrum figures use aggregated cell or cell-cover observations, not individual thermal pixels.",
        "",
        "## Figures Written",
        "",
    ]
    lines.extend(f"- `{relative_posix(path)}`" for path in written)
    write_markdown(SUMMARY_MD, lines)
    print(f"Clear spectrum figures written: {len(written)}")
    for path in written:
        print(relative_posix(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
