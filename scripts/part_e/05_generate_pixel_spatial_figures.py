#!/usr/bin/env python3
"""Generate full-pixel spatial maps and QA panels for all five pilot images."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import matplotlib
import numpy as np
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch

from part_e_pixel_common import (
    build_image_records,
    build_luhk_pixel_labels,
    class_mapping,
    ensure_output_directories,
    load_config,
    load_masks,
    load_source_tables,
    load_temperature,
    project_path,
)


os.environ.setdefault("MPLCONFIGDIR", str(project_path(".matplotlib-cache")))
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


COLORS = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#D55E00", "#56B4E9", "#999999", "#332288"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/part_e_delta_t_analysis.json")
    parser.add_argument("--image-id", help="Generate maps only for the selected pilot image.")
    return parser.parse_args()


def save(fig: plt.Figure, directory: Path, stem: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    fig.savefig(directory / f"{stem}.png", dpi=200, bbox_inches="tight", facecolor="white")
    fig.savefig(directory / f"{stem}.pdf", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def scalar_map(matrix: np.ndarray, title: str, label: str, cmap: str, directory: Path, stem: str) -> None:
    fig, ax = plt.subplots(figsize=(10, 6), facecolor="white")
    finite = matrix[np.isfinite(matrix)]
    vmin, vmax = np.quantile(finite, [0.01, 0.99])
    image = ax.imshow(matrix, origin="upper", cmap=cmap, vmin=vmin, vmax=vmax, interpolation="nearest")
    colorbar = fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04); colorbar.set_label(label, fontsize=12); colorbar.ax.tick_params(labelsize=10)
    ax.set_title(title, fontsize=14); ax.set_xlabel("Thermal column / pixel_x", fontsize=12); ax.set_ylabel("Thermal row / pixel_y", fontsize=12); ax.tick_params(labelsize=10)
    fig.tight_layout(); save(fig, directory, stem)


def categorical_overlay(
    base: np.ndarray,
    categories: np.ndarray,
    names: dict[int, str],
    title: str,
    directory: Path,
    stem: str,
) -> None:
    unique = sorted(int(value) for value in np.unique(categories) if int(value) >= 0)
    index = np.full(categories.shape, np.nan, dtype=float)
    for position, value in enumerate(unique):
        index[categories == value] = position
    cmap = ListedColormap(COLORS[: max(1, len(unique))])
    fig, ax = plt.subplots(figsize=(11, 6.5), facecolor="white")
    ax.imshow(base, origin="upper", cmap="gray", interpolation="nearest")
    ax.imshow(index, origin="upper", cmap=cmap, alpha=0.48, interpolation="nearest", vmin=0, vmax=max(len(unique) - 1, 1))
    handles = [Patch(facecolor=COLORS[pos % len(COLORS)], label=f"{value}: {names.get(value, str(value))}") for pos, value in enumerate(unique)]
    ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(1.01, 1), frameon=False, fontsize=9)
    ax.set_title(title, fontsize=14); ax.set_xlabel("Thermal column / pixel_x", fontsize=12); ax.set_ylabel("Thermal row / pixel_y", fontsize=12); ax.tick_params(labelsize=10)
    fig.tight_layout(); save(fig, directory, stem)


def shadow_overlay(base: np.ndarray, shadow: np.ndarray | None, image_id: str, directory: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 6), facecolor="white")
    ax.imshow(base, origin="upper", cmap="gray", interpolation="nearest")
    if shadow is not None:
        rgba = np.zeros((*shadow.shape, 4), dtype=float)
        rgba[shadow == 1] = [0.84, 0.15, 0.16, 0.65]
        ax.imshow(rgba, origin="upper", interpolation="nearest")
        present = int((shadow == 1).sum())
        note = f"shadow_flag=1 pixels: {present:,}; shadow-known pixels: {shadow.size:,}"
    else:
        note = "Shadow mask missing; values not converted to zero."
    ax.set_title(f"{image_id} — full-pixel shadow overlay", fontsize=14)
    ax.set_xlabel("Thermal column / pixel_x", fontsize=12); ax.set_ylabel("Thermal row / pixel_y", fontsize=12); ax.tick_params(labelsize=10)
    ax.text(0, -0.12, note, transform=ax.transAxes, fontsize=10)
    fig.tight_layout(); save(fig, directory, f"{image_id}_shadow_overlay")


def qa_panel(
    image_id: str,
    temperature: np.ndarray,
    delta_t: np.ndarray,
    luhk_code: np.ndarray,
    cover: np.ndarray,
    shadow: np.ndarray | None,
    cover_names: dict[int, str],
    directory: Path,
) -> None:
    fig, axes = plt.subplots(2, 3, figsize=(18, 10), facecolor="white")
    tlim = np.quantile(temperature[np.isfinite(temperature)], [0.01, 0.99])
    dlim = np.quantile(delta_t[np.isfinite(delta_t)], [0.01, 0.99])
    im0 = axes[0, 0].imshow(temperature, origin="upper", cmap="cividis", vmin=tlim[0], vmax=tlim[1]); axes[0, 0].set_title("Temperature (°C)")
    im1 = axes[0, 1].imshow(delta_t, origin="upper", cmap="coolwarm", vmin=dlim[0], vmax=dlim[1]); axes[0, 1].set_title("ΔT (°C)")
    fig.colorbar(im0, ax=axes[0, 0], fraction=0.046); fig.colorbar(im1, ax=axes[0, 1], fraction=0.046)
    for ax, matrix, title in ((axes[0, 2], luhk_code, "LUHK code"), (axes[1, 0], cover, "Physical cover class ID")):
        values = sorted(int(value) for value in np.unique(matrix) if int(value) >= 0)
        mapped = np.full(matrix.shape, np.nan)
        for index, value in enumerate(values): mapped[matrix == value] = index
        ax.imshow(mapped, origin="upper", cmap=ListedColormap(COLORS[: max(1, len(values))]), interpolation="nearest")
        ax.set_title(title)
    axes[1, 1].imshow(temperature, origin="upper", cmap="gray")
    if shadow is not None:
        rgba = np.zeros((*shadow.shape, 4)); rgba[shadow == 1] = [0.84, 0.15, 0.16, 0.65]; axes[1, 1].imshow(rgba, origin="upper")
    axes[1, 1].set_title("Shadow overlay")
    axes[1, 2].axis("off")
    stats = [
        f"Pixels: {temperature.size:,}", f"Finite/accepted: {np.isfinite(temperature).sum():,}",
        f"LUHK labelled: {(luhk_code >= 0).sum():,}", f"Cover labelled: {(~np.isin(cover, [0, 9])).sum():,}",
        f"Shadow known: {0 if shadow is None else shadow.size:,}", f"Shadow present: {0 if shadow is None else int((shadow == 1).sum()):,}",
        "Rows increase downward; columns increase rightward.", "All map pixels are full-population pixels, not sampled pixels.",
    ]
    axes[1, 2].text(0.02, 0.96, "\n".join(stats), va="top", fontsize=12, linespacing=1.5)
    for ax in axes.flat[:5]:
        ax.set_xlabel("thermal_col", fontsize=10); ax.set_ylabel("thermal_row", fontsize=10); ax.tick_params(labelsize=9)
    fig.suptitle(f"{image_id} — full-pixel Part E QA panel", fontsize=16)
    fig.tight_layout(rect=[0, 0, 1, 0.96]); save(fig, directory, f"{image_id}_combined_qa_panel")


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    ensure_output_directories(config)
    tables = load_source_tables(config)
    records = build_image_records(config, tables)
    if args.image_id:
        if args.image_id not in set(map(str, config["pilot_image_ids"])):
            raise ValueError(f"Unknown pilot image ID: {args.image_id}")
        records = records.loc[records["image_id"].astype(str).eq(args.image_id)].copy()
    cover_names = class_mapping(tables)
    directory = project_path(config["outputs"]["spatial_maps"])
    for _, record in records.iterrows():
        image_id = str(record["image_id"])
        temperature = load_temperature(record)
        delta_t = temperature - np.float32(record["ambient_temperature_c"])
        cover, shadow = load_masks(record, temperature.shape)
        luhk = build_luhk_pixel_labels(record, tables, temperature.shape)
        luhk_code = np.asarray(luhk["class_code"], dtype=int); luhk_code[~np.asarray(luhk["mapped"], dtype=bool)] = -1
        scalar_map(temperature, f"{image_id} — full-pixel temperature", "Temperature (°C)", "cividis", directory, f"{image_id}_temperature_map")
        scalar_map(delta_t, f"{image_id} — full-pixel ΔT", "ΔT (°C)", "coolwarm", directory, f"{image_id}_delta_t_map")
        luhk_names = {int(code): str(name) for code, name in zip(np.asarray(luhk["class_code"]).ravel(), np.asarray(luhk["class_name"]).ravel())}
        categorical_overlay(temperature, luhk_code, luhk_names, f"{image_id} — LUHK overlay", directory, f"{image_id}_luhk_overlay")
        categorical_overlay(temperature, cover.astype(int), cover_names, f"{image_id} — physical-cover overlay", directory, f"{image_id}_surface_cover_overlay")
        shadow_overlay(temperature, shadow, image_id, directory)
        qa_panel(image_id, temperature, delta_t, luhk_code, cover, shadow, cover_names, directory)
        print(f"Spatial figures complete: {image_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
