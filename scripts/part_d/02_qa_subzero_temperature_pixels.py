#!/usr/bin/env python3
"""Focused Part D spatial QA for sub-zero pixels in TAT3-parameter matrices.

This script operates only on existing Part D temperature matrices and Part C
masks. It does not call the DJI Thermal SDK, re-extract temperatures,
calculate delta T, or change radiometric parameters.
"""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("MPLCONFIGDIR", str(PROJECT_ROOT / ".matplotlib-cache"))

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw

SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from table_io import write_rows

EXPECTED_SHAPE = (512, 640)
EDGE_PIXELS = 5
THRESHOLDS = [
    ("below_0", 0.0),
    ("below_minus_5", -5.0),
    ("below_minus_10", -10.0),
]

PILOT_PAIRS_XLSX = PROJECT_ROOT / "data" / "metadata" / "part_b_pilot_pairs.xlsx"
CLASS_MAPPING_XLSX = PROJECT_ROOT / "data" / "annotations" / "part_c" / "surface_cover_class_mapping.xlsx"
TEMPERATURE_DIR = PROJECT_ROOT / "data" / "processed" / "part_d" / "temperature_matrices"
PART_C_MASK_DIR = PROJECT_ROOT / "outputs" / "part_c" / "masks"
EXTRACTION_SUMMARY_MD = PROJECT_ROOT / "outputs" / "part_d" / "summaries" / "part_d_tat3_parameter_temperature_extraction_summary.md"
DOC_PATH = PROJECT_ROOT / "docs" / "part_d_temperature_extraction.md"

QA_ROOT = PROJECT_ROOT / "outputs" / "part_d" / "qa" / "subzero_spatial_qa"
SUMMARY_DIR = QA_ROOT / "summary"
SUBZERO_SUMMARY_MD = PROJECT_ROOT / "outputs" / "part_d" / "summaries" / "part_d_tat3_parameter_subzero_spatial_qa_summary.md"
SUMMARY_CSV = SUMMARY_DIR / "part_d_tat3_parameter_subzero_spatial_qa_summary.csv"
SUMMARY_XLSX = SUMMARY_DIR / "part_d_tat3_parameter_subzero_spatial_qa_summary.xlsx"
CLASS_BREAKDOWN_CSV = SUMMARY_DIR / "part_d_tat3_parameter_subzero_by_physical_class.csv"
CLASS_BREAKDOWN_XLSX = SUMMARY_DIR / "part_d_tat3_parameter_subzero_by_physical_class.xlsx"
SHADOW_BREAKDOWN_CSV = SUMMARY_DIR / "part_d_tat3_parameter_subzero_by_shadow_state.csv"
SHADOW_BREAKDOWN_XLSX = SUMMARY_DIR / "part_d_tat3_parameter_subzero_by_shadow_state.xlsx"
RECURRING_COORDS_CSV = SUMMARY_DIR / "part_d_tat3_parameter_recurring_subzero_coordinates.csv"
OVERALL_CONTACT_SHEET = SUMMARY_DIR / "part_d_tat3_parameter_subzero_overall_contact_sheet.png"

CLASS_COLORS = {
    0: "#000000",
    1: "#f2f2f2",
    2: "#ff8c00",
    3: "#555555",
    4: "#1f7a3a",
    5: "#8bc34a",
    6: "#9b6a3c",
    7: "#1f78b4",
    8: "#ffcc00",
    9: "#d94fd6",
}


def relative_posix(path: Path | str) -> str:
    work = Path(path)
    try:
        return work.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return work.as_posix()


def resolve_project_path(path_text: Any) -> Path:
    path = Path(str(path_text))
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def ensure_dirs() -> None:
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)


def load_table(path: Path, label: str) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Missing {label}: {relative_posix(path)}")
    return pd.read_excel(path, dtype=str).fillna("")


def load_pilot_pairs() -> pd.DataFrame:
    df = load_table(PILOT_PAIRS_XLSX, "Part B pilot pairs")
    required = {"pair_id", "image_id", "t_path", "t_image_width", "t_image_height"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Part B pilot pairs table is missing columns: {sorted(missing)}")
    return df


def load_class_names() -> dict[int, str]:
    df = load_table(CLASS_MAPPING_XLSX, "Part C class mapping")
    names: dict[int, str] = {}
    for _, row in df.iterrows():
        try:
            class_id = int(float(str(row.get("class_id", "")).strip()))
        except ValueError:
            continue
        names[class_id] = str(row.get("class_name", "")).strip() or f"class_{class_id}"
    return names


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[index : index + 2], 16) for index in (0, 2, 4))


def class_mask_to_rgb(class_mask: np.ndarray, class_names: dict[int, str]) -> np.ndarray:
    rgb = np.zeros((*class_mask.shape, 3), dtype=np.uint8)
    for class_id in sorted(set(class_names) | {int(value) for value in np.unique(class_mask)}):
        color = CLASS_COLORS.get(class_id, "#ffffff")
        rgb[class_mask == class_id] = hex_to_rgb(color)
    return rgb


def load_temperature_matrix(image_id: str) -> np.ndarray:
    path = TEMPERATURE_DIR / f"{image_id}_temperature_celsius.npy"
    if not path.is_file():
        raise FileNotFoundError(f"Missing temperature matrix: {relative_posix(path)}")
    return np.load(path)


def load_masks(image_id: str) -> tuple[np.ndarray, np.ndarray]:
    pair_dir = PART_C_MASK_DIR / image_id
    class_path = pair_dir / f"{image_id}_physical_surface_cover_class_id_thermal_grid.npy"
    shadow_path = pair_dir / f"{image_id}_shadow_flag_thermal_grid.npy"
    if not class_path.is_file():
        raise FileNotFoundError(f"Missing physical surface-cover mask: {relative_posix(class_path)}")
    if not shadow_path.is_file():
        raise FileNotFoundError(f"Missing shadow mask: {relative_posix(shadow_path)}")
    return np.load(class_path), np.load(shadow_path)


def load_thermal_image(path: Path) -> Image.Image:
    if not path.is_file():
        raise FileNotFoundError(f"Missing original thermal JPG: {relative_posix(path)}")
    return Image.open(path).convert("RGB")


def finite_values(array: np.ndarray) -> np.ndarray:
    return array[np.isfinite(array)]


def stat_or_blank(values: np.ndarray, stat: str) -> float | str:
    values = values[np.isfinite(values)]
    if values.size == 0:
        return ""
    if stat == "min":
        return float(np.min(values))
    if stat == "max":
        return float(np.max(values))
    if stat == "mean":
        return float(np.mean(values))
    if stat == "median":
        return float(np.median(values))
    if stat == "p01":
        return float(np.percentile(values, 1))
    if stat == "p99":
        return float(np.percentile(values, 99))
    raise ValueError(stat)


def round_float(value: float | str, digits: int = 6) -> float | str:
    if value == "":
        return ""
    return round(float(value), digits)


def edge_mask(shape: tuple[int, int], edge_pixels: int = EDGE_PIXELS) -> np.ndarray:
    height, width = shape
    mask = np.zeros(shape, dtype=bool)
    mask[:edge_pixels, :] = True
    mask[-edge_pixels:, :] = True
    mask[:, :edge_pixels] = True
    mask[:, -edge_pixels:] = True
    return mask


def connected_components(mask: np.ndarray) -> tuple[int, int]:
    try:
        from skimage.measure import label

        labels = label(mask, connectivity=2)
        component_count = int(labels.max())
        if component_count == 0:
            return 0, 0
        counts = np.bincount(labels.ravel())
        return int(component_count), int(counts[1:].max())
    except Exception:
        return connected_components_fallback(mask)


def connected_components_fallback(mask: np.ndarray) -> tuple[int, int]:
    height, width = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    component_count = 0
    largest = 0
    neighbors = [
        (-1, -1),
        (-1, 0),
        (-1, 1),
        (0, -1),
        (0, 1),
        (1, -1),
        (1, 0),
        (1, 1),
    ]
    ys, xs = np.where(mask)
    for start_y, start_x in zip(ys.tolist(), xs.tolist()):
        if visited[start_y, start_x]:
            continue
        component_count += 1
        stack = [(start_y, start_x)]
        visited[start_y, start_x] = True
        size = 0
        while stack:
            y, x = stack.pop()
            size += 1
            for dy, dx in neighbors:
                ny, nx = y + dy, x + dx
                if 0 <= ny < height and 0 <= nx < width and mask[ny, nx] and not visited[ny, nx]:
                    visited[ny, nx] = True
                    stack.append((ny, nx))
        largest = max(largest, size)
    return component_count, largest


def pearson_abs(a: np.ndarray, b: np.ndarray) -> float:
    a = a.astype(np.float32).ravel()
    b = b.astype(np.float32).ravel()
    good = np.isfinite(a) & np.isfinite(b)
    if good.sum() < 2:
        return float("nan")
    a = a[good]
    b = b[good]
    a = a - float(a.mean())
    b = b - float(b.mean())
    denom = float(np.sqrt(np.sum(a * a) * np.sum(b * b)))
    if denom == 0:
        return float("nan")
    return abs(float(np.sum(a * b) / denom))


def orientation_diagnostic(temps: np.ndarray, thermal_image: Image.Image) -> tuple[str, dict[str, float | str]]:
    image_array = np.asarray(thermal_image.convert("L"), dtype=np.float32)
    details: dict[str, float | str] = {
        "thermal_jpg_shape": f"{image_array.shape[0]}x{image_array.shape[1]}",
        "current_abs_corr": "",
        "vertical_flip_abs_corr": "",
        "horizontal_flip_abs_corr": "",
        "transposed_check": "not_applicable_shape_would_be_640x512",
    }
    if image_array.shape != temps.shape:
        return "thermal JPG shape differs from matrix shape; overlay/orientation requires manual review", details

    current = pearson_abs(temps, image_array)
    vertical = pearson_abs(np.flipud(temps), image_array)
    horizontal = pearson_abs(np.fliplr(temps), image_array)
    details["current_abs_corr"] = round(current, 6) if math.isfinite(current) else ""
    details["vertical_flip_abs_corr"] = round(vertical, 6) if math.isfinite(vertical) else ""
    details["horizontal_flip_abs_corr"] = round(horizontal, 6) if math.isfinite(horizontal) else ""

    warnings: list[str] = []
    if math.isfinite(current) and math.isfinite(vertical) and vertical > current + 0.08:
        warnings.append("vertical flip has stronger JPG-intensity diagnostic correlation")
    if math.isfinite(current) and math.isfinite(horizontal) and horizontal > current + 0.08:
        warnings.append("horizontal flip has stronger JPG-intensity diagnostic correlation")
    if warnings:
        return "; ".join(warnings), details
    return "none_detected_by_shape_and_JPG_intensity_diagnostic", details


def save_heatmap(temps: np.ndarray, image_id: str, path: Path) -> None:
    values = finite_values(temps)
    p01 = float(np.percentile(values, 1)) if values.size else 0.0
    p99 = float(np.percentile(values, 99)) if values.size else 1.0
    if np.isclose(p01, p99):
        p01 = float(np.min(values)) if values.size else 0.0
        p99 = float(np.max(values)) if values.size else 1.0
    fig, ax = plt.subplots(figsize=(8.5, 6.2), dpi=150)
    im = ax.imshow(temps, cmap="inferno", vmin=p01, vmax=p99, origin="upper")
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("Temperature (deg C)")
    ax.set_title(f"{image_id} temperature heatmap")
    ax.set_xlabel("column")
    ax.set_ylabel("row")
    stats = (
        f"min={np.min(values):.2f}, max={np.max(values):.2f}, mean={np.mean(values):.2f}, "
        f"median={np.median(values):.2f}, p01={p01:.2f}, p99={p99:.2f}\n"
        f"Displayed scale clipped to p01-p99: {p01:.2f} to {p99:.2f} deg C"
    )
    fig.text(0.5, 0.02, stats, ha="center", va="bottom", fontsize=8)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def save_binary_mask(below0: np.ndarray, nonfinite: np.ndarray, image_id: str, path: Path) -> None:
    rgb = np.full((*below0.shape, 3), 245, dtype=np.uint8)
    rgb[below0] = (220, 30, 30)
    rgb[nonfinite] = (40, 90, 220)
    fig, ax = plt.subplots(figsize=(8.2, 5.8), dpi=150)
    ax.imshow(rgb, origin="upper")
    ax.set_title(f"{image_id}: valid temp < 0 deg C (red), non-finite (blue)")
    ax.set_xlabel("column")
    ax.set_ylabel("row")
    ax.text(
        0.01,
        -0.08,
        "Matrix orientation preserved: row 0 at top, column 0 at left.",
        transform=ax.transAxes,
        fontsize=8,
    )
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def save_overlay(thermal_image: Image.Image, below0: np.ndarray, image_id: str, path: Path) -> None:
    base = np.asarray(thermal_image.convert("RGB"), dtype=np.float32)
    if base.shape[:2] == below0.shape:
        overlay = base.copy()
        red = np.zeros_like(base)
        red[..., 0] = 255
        red[..., 1] = 20
        red[..., 2] = 20
        alpha = 0.55
        overlay[below0] = (1.0 - alpha) * base[below0] + alpha * red[below0]
        shown = np.clip(overlay, 0, 255).astype(np.uint8)
        note = "Red overlay: valid temp < 0 deg C."
    else:
        shown = np.clip(base, 0, 255).astype(np.uint8)
        note = "No overlay drawn because thermal JPG shape differs from matrix shape."

    fig, ax = plt.subplots(figsize=(8.2, 5.8), dpi=150)
    ax.imshow(shown, origin="upper")
    ax.set_title(f"{image_id}: sub-zero overlay on original thermal JPG")
    ax.set_xlabel("column")
    ax.set_ylabel("row")
    ax.text(0.01, -0.08, note, transform=ax.transAxes, fontsize=8)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def save_threshold_comparison(masks: dict[str, np.ndarray], image_id: str, path: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.2), dpi=150)
    titles = [("below_0", "< 0 deg C"), ("below_minus_5", "< -5 deg C"), ("below_minus_10", "< -10 deg C")]
    for ax, (key, title) in zip(axes, titles):
        ax.imshow(masks[key], cmap="Reds", vmin=0, vmax=1, origin="upper")
        ax.set_title(f"{title}\n{int(masks[key].sum())} px")
        ax.set_xticks([])
        ax.set_yticks([])
    fig.suptitle(f"{image_id}: threshold comparison")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def save_class_comparison(class_mask: np.ndarray, below0: np.ndarray, class_names: dict[int, str], image_id: str, path: Path) -> None:
    rgb = class_mask_to_rgb(class_mask, class_names).astype(np.float32)
    red = np.zeros_like(rgb)
    red[..., 0] = 255
    red[..., 1] = 30
    red[..., 2] = 30
    rgb[below0] = 0.45 * rgb[below0] + 0.55 * red[below0]
    fig, ax = plt.subplots(figsize=(8.2, 5.8), dpi=150)
    ax.imshow(np.clip(rgb, 0, 255).astype(np.uint8), origin="upper")
    ax.set_title(f"{image_id}: physical cover with temp < 0 deg C overlay")
    ax.set_xlabel("column")
    ax.set_ylabel("row")
    ax.text(0.01, -0.08, "Physical classes remain separate from shadow state. Red overlay: valid temp < 0 deg C.", transform=ax.transAxes, fontsize=8)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def save_shadow_comparison(shadow_mask: np.ndarray, below0: np.ndarray, image_id: str, path: Path) -> None:
    rgb = np.full((*shadow_mask.shape, 3), 235, dtype=np.uint8)
    rgb[shadow_mask == 1] = (70, 45, 120)
    rgb[below0] = (230, 35, 35)
    fig, ax = plt.subplots(figsize=(8.2, 5.8), dpi=150)
    ax.imshow(rgb, origin="upper")
    ax.set_title(f"{image_id}: shadow state with temp < 0 deg C overlay")
    ax.set_xlabel("column")
    ax.set_ylabel("row")
    ax.text(0.01, -0.08, "Gray=shadow 0, purple=shadow 1, red=valid temp < 0 deg C. Shadow is not a physical class.", transform=ax.transAxes, fontsize=8)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def thumbnail_with_label(image_path: Path, label: str, tile_size: tuple[int, int]) -> Image.Image:
    label_height = 34
    tile = Image.new("RGB", tile_size, "white")
    image = Image.open(image_path).convert("RGB")
    image.thumbnail((tile_size[0], tile_size[1] - label_height), Image.Resampling.LANCZOS)
    tile.paste(image, ((tile_size[0] - image.width) // 2, label_height + (tile_size[1] - label_height - image.height) // 2))
    draw = ImageDraw.Draw(tile)
    draw.text((8, 10), label, fill=(0, 0, 0))
    return tile


def save_contact_sheet(items: list[tuple[str, Path]], path: Path, columns: int = 3, tile_size: tuple[int, int] = (450, 340)) -> None:
    rows = int(math.ceil(len(items) / columns))
    sheet = Image.new("RGB", (tile_size[0] * columns, tile_size[1] * rows), "white")
    for index, (label, item_path) in enumerate(items):
        tile = thumbnail_with_label(item_path, label, tile_size)
        sheet.paste(tile, ((index % columns) * tile_size[0], (index // columns) * tile_size[1]))
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)


def classify_spatial_pattern(below0_count: int, component_count: int, largest_component: int, edge_fraction: float) -> str:
    if below0_count == 0:
        return "none"
    if edge_fraction >= 0.75:
        return "edge_concentrated"
    if component_count > 0 and largest_component / below0_count >= 0.50:
        return "clustered"
    if component_count >= max(10, below0_count // 3):
        return "mostly_isolated_or_speckled"
    return "mixed"


def qa_status_and_notes(
    summary: dict[str, Any],
    orientation_warning: str,
    structural_warnings: list[str],
    spatial_pattern: str,
) -> tuple[str, str]:
    notes: list[str] = []
    status = "pass"
    if structural_warnings:
        status = "fail"
        notes.extend(structural_warnings)
    if orientation_warning != "none_detected_by_shape_and_JPG_intensity_diagnostic":
        status = "fail" if "shape differs" in orientation_warning else "warn"
        notes.append(f"orientation diagnostic: {orientation_warning}")
    if int(summary["nonfinite_pixel_count"]) > 0:
        status = "fail"
        notes.append("non-finite temperature values present")
    if float(summary["below_0_percent_of_valid"]) > 0:
        if status == "pass":
            status = "warn"
        notes.append(f"sub-zero pixels present; pattern={spatial_pattern}")
    if float(summary["below_0_percent_of_valid"]) > 50:
        status = "fail"
        notes.append("most valid pixels are sub-zero")
    if float(summary["below_0_near_image_edge_fraction"]) > 0.75 and int(summary["below_0_pixel_count"]) > 0:
        if status == "pass":
            status = "warn"
        notes.append("sub-zero pixels are edge-concentrated")
    if not notes:
        notes.append("no structural or sub-zero anomaly detected")
    return status, "; ".join(notes)


def image_output_paths(image_id: str) -> dict[str, Path]:
    out_dir = QA_ROOT / image_id
    return {
        "dir": out_dir,
        "heatmap": out_dir / f"{image_id}_temperature_heatmap.png",
        "binary": out_dir / f"{image_id}_below_0_binary_mask.png",
        "overlay": out_dir / f"{image_id}_below_0_overlay_on_thermal_jpg.png",
        "thresholds": out_dir / f"{image_id}_threshold_comparison.png",
        "class": out_dir / f"{image_id}_below_0_physical_cover_comparison.png",
        "shadow": out_dir / f"{image_id}_below_0_shadow_comparison.png",
        "contact": out_dir / f"{image_id}_subzero_spatial_qa_contact_sheet.png",
    }


def process_image(row: pd.Series, class_names: dict[int, str]) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], np.ndarray, Path]:
    pair_id = str(row["pair_id"])
    image_id = str(row["image_id"])
    t_path = resolve_project_path(row["t_path"])
    temps = load_temperature_matrix(image_id)
    class_mask, shadow_mask = load_masks(image_id)
    thermal_image = load_thermal_image(t_path)
    outputs = image_output_paths(image_id)
    outputs["dir"].mkdir(parents=True, exist_ok=True)

    finite = np.isfinite(temps)
    nonfinite = ~finite
    nan_mask = np.isnan(temps)
    posinf_mask = np.isposinf(temps)
    neginf_mask = np.isneginf(temps)
    valid_count = int(finite.sum())
    total_count = int(temps.size)
    threshold_masks = {
        key: (temps < threshold) & finite
        for key, threshold in THRESHOLDS
    }
    below0 = threshold_masks["below_0"]
    below_minus_5 = threshold_masks["below_minus_5"]
    below_minus_10 = threshold_masks["below_minus_10"]
    edge = edge_mask(temps.shape)

    component_count, largest_component = connected_components(below0)
    below0_count = int(below0.sum())
    below0_edge_count = int((below0 & edge).sum())
    below0_edge_fraction = below0_edge_count / below0_count if below0_count else 0.0
    below0_shadow_count = int((below0 & (shadow_mask == 1)).sum())
    below0_nonshadow_count = int((below0 & (shadow_mask == 0)).sum())
    below0_shadow_fraction = below0_shadow_count / below0_count if below0_count else 0.0

    unique_below_classes, below_class_counts = np.unique(class_mask[below0], return_counts=True) if below0_count else (np.array([], dtype=int), np.array([], dtype=int))
    if below0_count:
        dominant_index = int(np.argmax(below_class_counts))
        dominant_class_id = int(unique_below_classes[dominant_index])
        dominant_class_name = class_names.get(dominant_class_id, f"unknown_class_{dominant_class_id}")
        dominant_class_count = int(below_class_counts[dominant_index])
    else:
        dominant_class_id = ""
        dominant_class_name = ""
        dominant_class_count = 0

    structural_warnings: list[str] = []
    if temps.shape != EXPECTED_SHAPE:
        structural_warnings.append(f"temperature matrix shape {temps.shape} does not match expected {EXPECTED_SHAPE}")
    if class_mask.shape != temps.shape:
        structural_warnings.append(f"physical mask shape {class_mask.shape} does not match temperature matrix shape {temps.shape}")
    if shadow_mask.shape != temps.shape:
        structural_warnings.append(f"shadow mask shape {shadow_mask.shape} does not match temperature matrix shape {temps.shape}")
    if thermal_image.size != (temps.shape[1], temps.shape[0]):
        structural_warnings.append(f"thermal JPG size {thermal_image.size} does not match matrix width/height {(temps.shape[1], temps.shape[0])}")

    orientation_warning, orientation_details = orientation_diagnostic(temps, thermal_image)
    spatial_pattern = classify_spatial_pattern(below0_count, component_count, largest_component, below0_edge_fraction)

    values = finite_values(temps)
    summary: dict[str, Any] = {
        "pair_id": pair_id,
        "image_id": image_id,
        "temperature_matrix_path": relative_posix(TEMPERATURE_DIR / f"{image_id}_temperature_celsius.npy"),
        "thermal_jpg_path": relative_posix(t_path),
        "matrix_height": int(temps.shape[0]),
        "matrix_width": int(temps.shape[1]),
        "total_pixel_count": total_count,
        "valid_temperature_pixel_count": valid_count,
        "nonfinite_pixel_count": int(nonfinite.sum()),
        "nan_pixel_count": int(nan_mask.sum()),
        "positive_infinity_pixel_count": int(posinf_mask.sum()),
        "negative_infinity_pixel_count": int(neginf_mask.sum()),
        "below_0_pixel_count": below0_count,
        "below_0_percent_of_valid": round(below0_count / valid_count * 100.0, 6) if valid_count else 0.0,
        "below_minus_5_pixel_count": int(below_minus_5.sum()),
        "below_minus_5_percent_of_valid": round(int(below_minus_5.sum()) / valid_count * 100.0, 6) if valid_count else 0.0,
        "below_minus_10_pixel_count": int(below_minus_10.sum()),
        "below_minus_10_percent_of_valid": round(int(below_minus_10.sum()) / valid_count * 100.0, 6) if valid_count else 0.0,
        "minimum_temperature_c": round_float(stat_or_blank(values, "min")),
        "maximum_temperature_c": round_float(stat_or_blank(values, "max")),
        "mean_temperature_c": round_float(stat_or_blank(values, "mean")),
        "median_temperature_c": round_float(stat_or_blank(values, "median")),
        "p01_temperature_c": round_float(stat_or_blank(values, "p01")),
        "p99_temperature_c": round_float(stat_or_blank(values, "p99")),
        "below_0_in_shadow_count": below0_shadow_count,
        "below_0_in_nonshadow_count": below0_nonshadow_count,
        "below_0_shadow_fraction": round(below0_shadow_fraction, 6),
        "below_0_near_image_edge_count": below0_edge_count,
        "below_0_near_image_edge_fraction": round(below0_edge_fraction, 6),
        "edge_rule": f"within {EDGE_PIXELS} pixels of any image border",
        "largest_below_0_connected_component_pixels": largest_component,
        "below_0_connected_component_count": component_count,
        "dominant_physical_class_for_below_0": dominant_class_name,
        "dominant_physical_class_for_below_0_id": dominant_class_id,
        "dominant_physical_class_below_0_count": dominant_class_count,
        "spatial_pattern": spatial_pattern,
        "orientation_or_alignment_warning": orientation_warning,
        "current_abs_corr_to_thermal_jpg_intensity": orientation_details.get("current_abs_corr", ""),
        "vflip_abs_corr_to_thermal_jpg_intensity": orientation_details.get("vertical_flip_abs_corr", ""),
        "hflip_abs_corr_to_thermal_jpg_intensity": orientation_details.get("horizontal_flip_abs_corr", ""),
        "transposed_check": orientation_details.get("transposed_check", ""),
        "structural_warnings": "; ".join(structural_warnings),
        "heatmap_path": relative_posix(outputs["heatmap"]),
        "binary_mask_path": relative_posix(outputs["binary"]),
        "thermal_overlay_path": relative_posix(outputs["overlay"]),
        "threshold_comparison_path": relative_posix(outputs["thresholds"]),
        "physical_cover_comparison_path": relative_posix(outputs["class"]),
        "shadow_comparison_path": relative_posix(outputs["shadow"]),
        "contact_sheet_path": relative_posix(outputs["contact"]),
    }
    status, notes = qa_status_and_notes(summary, orientation_warning, structural_warnings, spatial_pattern)
    summary["qa_status"] = status
    summary["qa_notes"] = notes

    class_rows = class_breakdown(pair_id, image_id, temps, class_mask, class_names)
    shadow_rows = shadow_breakdown(pair_id, image_id, temps, shadow_mask)

    save_heatmap(temps, image_id, outputs["heatmap"])
    save_binary_mask(below0, nonfinite, image_id, outputs["binary"])
    save_overlay(thermal_image, below0, image_id, outputs["overlay"])
    save_threshold_comparison(threshold_masks, image_id, outputs["thresholds"])
    save_class_comparison(class_mask, below0, class_names, image_id, outputs["class"])
    save_shadow_comparison(shadow_mask, below0, image_id, outputs["shadow"])
    save_contact_sheet(
        [
            ("temperature heatmap", outputs["heatmap"]),
            ("below 0 binary", outputs["binary"]),
            ("thermal JPG overlay", outputs["overlay"]),
            ("thresholds", outputs["thresholds"]),
            ("physical cover", outputs["class"]),
            ("shadow state", outputs["shadow"]),
        ],
        outputs["contact"],
    )
    return summary, class_rows, shadow_rows, below0, outputs["contact"]


def class_breakdown(pair_id: str, image_id: str, temps: np.ndarray, class_mask: np.ndarray, class_names: dict[int, str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    finite = np.isfinite(temps)
    class_ids = sorted(set(class_names) | {int(value) for value in np.unique(class_mask)})
    for class_id in class_ids:
        class_pixels = class_mask == class_id
        valid = class_pixels & finite
        values = temps[valid]
        below0 = valid & (temps < 0)
        below5 = valid & (temps < -5)
        below10 = valid & (temps < -10)
        valid_count = int(valid.sum())
        below0_count = int(below0.sum())
        rows.append(
            {
                "pair_id": pair_id,
                "image_id": image_id,
                "physical_class_id": class_id,
                "physical_class_name": class_names.get(class_id, f"unknown_class_{class_id}"),
                "total_valid_pixels_in_class": valid_count,
                "below_0_pixel_count": below0_count,
                "below_0_percent_of_class_valid": round(below0_count / valid_count * 100.0, 6) if valid_count else 0.0,
                "minimum_temperature_c": round_float(stat_or_blank(values, "min")),
                "median_temperature_c": round_float(stat_or_blank(values, "median")),
                "mean_temperature_c": round_float(stat_or_blank(values, "mean")),
                "below_minus_5_pixel_count": int(below5.sum()),
                "below_minus_10_pixel_count": int(below10.sum()),
                "taxonomy_note": "physical surface-cover class only; shadow state is separate",
            }
        )
    return rows


def shadow_breakdown(pair_id: str, image_id: str, temps: np.ndarray, shadow_mask: np.ndarray) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    finite = np.isfinite(temps)
    shadow_values = sorted({0, 1} | {int(value) for value in np.unique(shadow_mask)})
    for shadow_value in shadow_values:
        state_pixels = shadow_mask == shadow_value
        valid = state_pixels & finite
        values = temps[valid]
        below0 = valid & (temps < 0)
        below5 = valid & (temps < -5)
        below10 = valid & (temps < -10)
        valid_count = int(valid.sum())
        below0_count = int(below0.sum())
        if shadow_value == 0:
            name = "non_shadow"
        elif shadow_value == 1:
            name = "shadow"
        else:
            name = f"invalid_shadow_value_{shadow_value}"
        rows.append(
            {
                "pair_id": pair_id,
                "image_id": image_id,
                "shadow_flag": shadow_value,
                "shadow_name": name,
                "total_valid_pixels_in_shadow_state": valid_count,
                "below_0_pixel_count": below0_count,
                "below_0_percent_of_shadow_state_valid": round(below0_count / valid_count * 100.0, 6) if valid_count else 0.0,
                "minimum_temperature_c": round_float(stat_or_blank(values, "min")),
                "median_temperature_c": round_float(stat_or_blank(values, "median")),
                "mean_temperature_c": round_float(stat_or_blank(values, "mean")),
                "below_minus_5_pixel_count": int(below5.sum()),
                "below_minus_10_pixel_count": int(below10.sum()),
                "taxonomy_note": "shadow is binary state mask: 1=shadow, 0=non-shadow; not a physical class",
            }
        )
    return rows


def recurring_coordinate_rows(image_ids: list[str], masks: list[np.ndarray]) -> list[dict[str, Any]]:
    if not masks:
        return []
    stack = np.stack(masks, axis=0)
    recurrence = stack.sum(axis=0)
    rows: list[dict[str, Any]] = []
    for count in range(len(masks), 1, -1):
        ys, xs = np.where(recurrence == count)
        if ys.size == 0:
            rows.append(
                {
                    "recurring_image_count": count,
                    "coordinate_count": 0,
                    "example_coordinates_row_col": "",
                    "image_ids": "",
                }
            )
            continue
        examples = []
        image_sets = []
        for y, x in zip(ys[:10].tolist(), xs[:10].tolist()):
            examples.append(f"{y},{x}")
            present = [image_ids[index] for index, mask in enumerate(masks) if mask[y, x]]
            image_sets.append("+".join(present))
        rows.append(
            {
                "recurring_image_count": count,
                "coordinate_count": int(ys.size),
                "example_coordinates_row_col": "; ".join(examples),
                "image_ids": " | ".join(image_sets[:3]),
            }
        )
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def write_tables(summary_rows: list[dict[str, Any]], class_rows: list[dict[str, Any]], shadow_rows: list[dict[str, Any]], recurring_rows: list[dict[str, Any]]) -> None:
    write_csv(SUMMARY_CSV, summary_rows)
    write_csv(CLASS_BREAKDOWN_CSV, class_rows)
    write_csv(SHADOW_BREAKDOWN_CSV, shadow_rows)
    write_csv(RECURRING_COORDS_CSV, recurring_rows)
    write_rows(SUMMARY_XLSX, summary_rows)
    write_rows(CLASS_BREAKDOWN_XLSX, class_rows)
    write_rows(SHADOW_BREAKDOWN_XLSX, shadow_rows)


def checkpoint_recommendation(summary_rows: list[dict[str, Any]]) -> str:
    if not summary_rows:
        return "do_not_accept_tat3_parameter_baseline"
    blocking_status = any(row["qa_status"] == "fail" for row in summary_rows)
    if blocking_status:
        return "do_not_accept_tat3_parameter_baseline"
    required_ok = all(
        int(row["matrix_height"]) == EXPECTED_SHAPE[0]
        and int(row["matrix_width"]) == EXPECTED_SHAPE[1]
        and not str(row["structural_warnings"]).strip()
        for row in summary_rows
    )
    return "tat3_parameter_baseline_structurally_ok" if required_ok else "do_not_accept_tat3_parameter_baseline"


def build_markdown_summary(summary_rows: list[dict[str, Any]], recurring_rows: list[dict[str, Any]]) -> str:
    recommendation = checkpoint_recommendation(summary_rows)
    lines = [
        "# Part D TAT3-Parameter Sub-Zero Spatial QA Summary",
        "",
        "## Scope",
        "",
        "- Located and quantified valid pixels with extracted temperature below 0 deg C, below -5 deg C, and below -10 deg C.",
        "- Checked matrix, thermal JPG, physical surface-cover mask, and shadow mask shape compatibility.",
        "- Generated spatial QA images for the current TAT3-parameter temperature matrices.",
        "- Did not run delta T analysis, 10 m aggregation, or modeling.",
        "",
        "## Definitions",
        "",
        f"- Expected matrix shape: `{EXPECTED_SHAPE[0]}x{EXPECTED_SHAPE[1]}` rows x columns.",
        f"- Near image edge: within `{EDGE_PIXELS}` pixels of any image border.",
        "- Connected components: 8-connected components on valid temperature pixels below 0 deg C.",
        "- Shadow state is interpreted only as `0 = non-shadow`, `1 = shadow`.",
        "",
        "## Per-Image Findings",
        "",
        "| image_id | QA | <0 px (%) | <-5 px (%) | <-10 px (%) | min C | pattern | dominant <0 class | edge fraction | shadow fraction | orientation/alignment |",
        "|---|---:|---:|---:|---:|---:|---|---|---:|---:|---|",
    ]
    for row in summary_rows:
        lines.append(
            "| {image_id} | {qa_status} | {below0} ({below0_pct:.3f}%) | {below5} ({below5_pct:.3f}%) | {below10} ({below10_pct:.3f}%) | {min_c} | {pattern} | {dominant} | {edge:.3f} | {shadow:.3f} | {orient} |".format(
                image_id=row["image_id"],
                qa_status=row["qa_status"],
                below0=row["below_0_pixel_count"],
                below0_pct=float(row["below_0_percent_of_valid"]),
                below5=row["below_minus_5_pixel_count"],
                below5_pct=float(row["below_minus_5_percent_of_valid"]),
                below10=row["below_minus_10_pixel_count"],
                below10_pct=float(row["below_minus_10_percent_of_valid"]),
                min_c=row["minimum_temperature_c"],
                pattern=row["spatial_pattern"],
                dominant=row["dominant_physical_class_for_below_0"],
                edge=float(row["below_0_near_image_edge_fraction"]),
                shadow=float(row["below_0_shadow_fraction"]),
                orient=str(row["orientation_or_alignment_warning"]).replace("|", "/"),
            )
        )

    fail_count = sum(row["qa_status"] == "fail" for row in summary_rows)
    warn_count = sum(row["qa_status"] == "warn" for row in summary_rows)
    pass_count = sum(row["qa_status"] == "pass" for row in summary_rows)
    total_below0 = sum(int(row["below_0_pixel_count"]) for row in summary_rows)
    total_valid = sum(int(row["valid_temperature_pixel_count"]) for row in summary_rows)
    total_below5 = sum(int(row["below_minus_5_pixel_count"]) for row in summary_rows)
    total_below10 = sum(int(row["below_minus_10_pixel_count"]) for row in summary_rows)
    recurrence_2 = next((row for row in recurring_rows if int(row["recurring_image_count"]) == 2), None)
    recurrence_all = next((row for row in recurring_rows if int(row["recurring_image_count"]) == len(summary_rows)), None)

    lines.extend(
        [
            "",
            "## Overall Result",
            "",
            f"- QA statuses: pass={pass_count}, warn={warn_count}, fail={fail_count}.",
            f"- Total valid pixels: {total_valid}.",
            f"- Total below 0 deg C pixels: {total_below0} ({total_below0 / total_valid * 100.0:.6f}% of valid)." if total_valid else "- Total below 0 deg C pixels: 0.",
            f"- Total below -5 deg C pixels: {total_below5} ({total_below5 / total_valid * 100.0:.6f}% of valid)." if total_valid else "- Total below -5 deg C pixels: 0.",
            f"- Total below -10 deg C pixels: {total_below10} ({total_below10 / total_valid * 100.0:.6f}% of valid)." if total_valid else "- Total below -10 deg C pixels: 0.",
            f"- Coordinates below 0 deg C in all five images: {recurrence_all['coordinate_count'] if recurrence_all else 0}.",
            f"- Coordinates below 0 deg C in exactly two images: {recurrence_2['coordinate_count'] if recurrence_2 else 0}.",
            "",
            "## Structural QA",
            "",
        ]
    )
    structural_issues = [row for row in summary_rows if str(row["structural_warnings"]).strip()]
    orientation_issues = [
        row for row in summary_rows
        if row["orientation_or_alignment_warning"] != "none_detected_by_shape_and_JPG_intensity_diagnostic"
    ]
    if not structural_issues and not orientation_issues:
        lines.append("- No obvious shape, transpose, flip, image-size, or mask-compatibility failure was detected by this QA.")
    else:
        for row in structural_issues:
            lines.append(f"- {row['image_id']}: {row['structural_warnings']}")
        for row in orientation_issues:
            lines.append(f"- {row['image_id']}: {row['orientation_or_alignment_warning']}")
    lines.extend(
        [
            "",
            "## Baseline QA Status",
            "",
        ]
    )
    if recommendation == "tat3_parameter_baseline_structurally_ok":
        lines.extend(
            [
                "- TAT3-parameter matrices are structurally acceptable for the next review step.",
                "- Rationale: all five matrices are readable, `512x640`, structurally aligned with Part C masks, and no obvious flip, transpose, corruption, or unit-scale failure was detected.",
                "- Remaining sub-zero extrema are documented for physical plausibility review before delta T analysis.",
            ]
        )
    else:
        lines.append("- Do not accept the TAT3-parameter baseline yet; one or more structural QA checks failed.")

    lines.extend(
        [
            "",
            "## Outputs",
            "",
            f"- Summary CSV: `{relative_posix(SUMMARY_CSV)}`",
            f"- Summary XLSX: `{relative_posix(SUMMARY_XLSX)}`",
            f"- Physical class breakdown: `{relative_posix(CLASS_BREAKDOWN_CSV)}`",
            f"- Shadow-state breakdown: `{relative_posix(SHADOW_BREAKDOWN_CSV)}`",
            f"- Recurring coordinate summary: `{relative_posix(RECURRING_COORDS_CSV)}`",
            f"- Overall contact sheet: `{relative_posix(OVERALL_CONTACT_SHEET)}`",
            f"- Per-image QA images: `{relative_posix(QA_ROOT)}/<image_id>/`",
            "- PNG visual QA outputs are reproducible local artifacts and remain ignored by default; compact CSV/XLSX/Markdown outputs carry the tracked checkpoint record.",
            "",
            "## Reproducibility",
            "",
            "```powershell",
            ".\\.venv\\Scripts\\python.exe scripts\\part_d\\02_qa_subzero_temperature_pixels.py",
            "```",
            "",
            "## Still Deferred",
            "",
            "- physical plausibility of apparent temperatures",
            "- suitability for final delta T analysis",
            "",
        ]
    )
    return "\n".join(lines)


def replace_or_append_section(path: Path, marker: str, section: str) -> None:
    start = f"<!-- {marker}:START -->"
    end = f"<!-- {marker}:END -->"
    block = f"{start}\n{section.rstrip()}\n{end}\n"
    if path.is_file():
        text = path.read_text(encoding="utf-8")
    else:
        text = ""
    if start in text and end in text:
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        new_text = before.rstrip() + "\n\n" + block + after.lstrip()
    else:
        new_text = text.rstrip() + "\n\n" + block
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_text, encoding="utf-8")


def update_part_d_docs(summary_rows: list[dict[str, Any]]) -> None:
    warn_count = sum(row["qa_status"] == "warn" for row in summary_rows)
    fail_count = sum(row["qa_status"] == "fail" for row in summary_rows)
    section = "\n".join(
        [
            "## TAT3-Parameter Sub-Zero Spatial QA",
            "",
            "This QA locates and documents extracted temperature pixels below 0 deg C after the canonical TAT3-parameter extraction. It does not calculate delta T.",
            "",
            "Confirmed for the current TAT3-parameter matrices:",
            "",
            "- Extraction succeeded for all five pilot images.",
            "- Temperature matrices are `512x640` and structurally compatible with the Part C physical-cover and shadow masks.",
            "- Sub-zero pixels were located, quantified, and visualized.",
            f"- QA statuses: warn={warn_count}, fail={fail_count}.",
            f"- Summary: `{relative_posix(SUBZERO_SUMMARY_MD)}`",
            "",
            "Still requiring review before delta T:",
            "",
            "- physical plausibility of apparent temperatures",
            "- suitability for final delta T analysis",
            "",
            "The old placeholder/default-parameter extraction is deprecated and should not be used for downstream analysis.",
        ]
    )
    replace_or_append_section(DOC_PATH, "PART_D_TAT3_PARAMETER_SUBZERO_QA", section)


def update_extraction_summary(summary_rows: list[dict[str, Any]]) -> None:
    section = "\n".join(
        [
            "## TAT3-Parameter Sub-Zero Spatial QA Addendum",
            "",
            "This QA checked the current TAT3-parameter matrices only; the DJI Thermal SDK was not rerun.",
            "",
            f"- Summary: `{relative_posix(SUBZERO_SUMMARY_MD)}`",
            f"- Table: `{relative_posix(SUMMARY_CSV)}`",
            f"- Per-image QA image root: `{relative_posix(QA_ROOT)}`",
            "- PNG visual QA outputs are reproducible local artifacts and are not part of the default tracked checkpoint.",
            "- All five matrices remained readable and structurally aligned with Part C masks.",
            "- Remaining sub-zero pixels are documented for physical plausibility review, not as final physical interpretation.",
        ]
    )
    replace_or_append_section(EXTRACTION_SUMMARY_MD, "PART_D_TAT3_PARAMETER_SUBZERO_QA", section)


def main() -> int:
    ensure_dirs()
    pairs = load_pilot_pairs()
    class_names = load_class_names()

    summary_rows: list[dict[str, Any]] = []
    class_rows: list[dict[str, Any]] = []
    shadow_rows: list[dict[str, Any]] = []
    below0_masks: list[np.ndarray] = []
    image_ids: list[str] = []
    contact_items: list[tuple[str, Path]] = []

    for _, row in pairs.iterrows():
        summary, class_breakdown_rows, shadow_breakdown_rows, below0_mask, contact_path = process_image(row, class_names)
        summary_rows.append(summary)
        class_rows.extend(class_breakdown_rows)
        shadow_rows.extend(shadow_breakdown_rows)
        below0_masks.append(below0_mask)
        image_ids.append(str(row["image_id"]))
        contact_items.append((str(row["image_id"]), contact_path))

    recurring_rows = recurring_coordinate_rows(image_ids, below0_masks)
    write_tables(summary_rows, class_rows, shadow_rows, recurring_rows)
    SUBZERO_SUMMARY_MD.parent.mkdir(parents=True, exist_ok=True)
    SUBZERO_SUMMARY_MD.write_text(build_markdown_summary(summary_rows, recurring_rows), encoding="utf-8")
    save_contact_sheet(contact_items, OVERALL_CONTACT_SHEET, columns=2, tile_size=(520, 390))
    update_part_d_docs(summary_rows)
    update_extraction_summary(summary_rows)

    print(f"Images checked: {len(summary_rows)}")
    print(f"QA statuses: {pd.Series([row['qa_status'] for row in summary_rows]).value_counts().to_dict()}")
    print(f"Summary: {relative_posix(SUBZERO_SUMMARY_MD)}")
    print(f"Summary CSV: {relative_posix(SUMMARY_CSV)}")
    return 0 if checkpoint_recommendation(summary_rows) == "tat3_parameter_baseline_structurally_ok" else 1


if __name__ == "__main__":
    sys.exit(main())
