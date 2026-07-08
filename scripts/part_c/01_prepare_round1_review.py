#!/usr/bin/env python3
"""Prepare Part C Round 1 LUHK and surface-cover review outputs.

Part C uses the manually accepted Part B Round 1.1 refined visible ROI as the
surface-cover image basis. LUHK is summarized only as broad land-use context
from existing approximate drone footprint/grid products.

This script does not extract thermal temperature, train a model, ingest manual
annotations, or create final masks.
"""

from __future__ import annotations

import csv
import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("MPLCONFIGDIR", str(PROJECT_ROOT / ".matplotlib-cache"))

import numpy as np
import pandas as pd
from PIL import Image, ImageColor, ImageDraw, ImageOps
from skimage import color, segmentation


PART_B_ALIGNMENT_SUMMARY_CSV = (
    PROJECT_ROOT / "outputs" / "part_b" / "summaries" / "part_b_round1_1_alignment_summary.csv"
)
PART_B_LOCAL_MANIFEST_CSV = (
    PROJECT_ROOT / "outputs" / "part_b" / "summaries" / "part_b_round1_local_outputs_manifest.csv"
)
GRID_CSV = PROJECT_ROOT / "data" / "processed" / "grids" / "pilot_luhk_aligned_10m_grid_cells.csv"
FOOTPRINTS_CSV = PROJECT_ROOT / "data" / "processed" / "footprints" / "image_footprints.csv"
VISIBLE_CAMERA_PROFILES_CSV = PROJECT_ROOT / "data" / "metadata" / "visible_camera_profiles.csv"
THERMAL_METADATA_CSV = PROJECT_ROOT / "data" / "metadata" / "dji_image_metadata.csv"

ANNOTATION_DIR = PROJECT_ROOT / "data" / "annotations" / "part_c"
PART_C_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "part_c"
LUHK_DIR = PART_C_OUTPUT_DIR / "luhk_context"
SURFACE_REVIEW_DIR = PART_C_OUTPUT_DIR / "surface_cover_review"
SUPERPIXEL_DIR = PART_C_OUTPUT_DIR / "superpixels"
SUMMARY_DIR = PART_C_OUTPUT_DIR / "summaries"
MASK_DIR = PART_C_OUTPUT_DIR / "masks"

SURFACE_CLASSES_CSV = ANNOTATION_DIR / "surface_cover_classes.csv"
MAIN_ANNOTATION_CSV = ANNOTATION_DIR / "part_c_surface_cover_annotations.csv"
LUHK_SUMMARY_CSV = SUMMARY_DIR / "part_c_luhk_context_summary.csv"
ROUND1_SUMMARY_CSV = SUMMARY_DIR / "part_c_round1_summary.csv"
ROUND1_SUMMARY_MD = SUMMARY_DIR / "part_c_round1_summary.md"
MANUAL_REVIEW_GUIDE_MD = SUMMARY_DIR / "part_c_manual_review_guide.md"
EARLY_DRAFT_MANIFEST_CSV = SUPERPIXEL_DIR / "early_part_b_draft_superpixels_manifest.csv"
MASK_README = MASK_DIR / "README.md"

SLIC_PARAMS = {
    "n_segments": 220,
    "compactness": 12.0,
    "sigma": 1.0,
    "start_label": 1,
    "image_basis": "refined_visible_roi_resized_to_thermal_grid",
}

SURFACE_CLASSES = [
    ("roof", "Building roof surfaces visible in the refined ROI."),
    ("concrete_pavement", "Light hardscape, plazas, walkways, and paved open areas."),
    ("asphalt_road", "Dark road carriageways and similar asphalt surfaces."),
    ("vegetation_tree", "Tree canopy and taller woody vegetation."),
    ("grass_low_vegetation", "Grass, planted ground cover, and low vegetation."),
    ("bare_soil", "Exposed soil or unsealed ground."),
    ("water", "Water surfaces."),
    ("shadow", "Cast shadow or deeply shaded image regions."),
    ("vehicle_temporary_object", "Vehicles, movable equipment, or temporary objects."),
    ("unclear_ignore", "Ambiguous or out-of-scope segments to exclude from final masks."),
]

LUHK_CATEGORY_COLORS = {
    0: "#1f77b4",
    1: "#ff7f0e",
    2: "#9467bd",
    3: "#2ca02c",
    4: "#d62728",
    5: "#8c564b",
    6: "#e377c2",
    7: "#7f7f7f",
    8: "#bcbd22",
    9: "#17becf",
}


def relative_posix(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def resolve_project_path(path_text: Any) -> Path:
    path = Path(str(path_text))
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def safe_name(value: Any) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value))
    return text.strip("_") or "item"


def as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def as_int(value: Any) -> int:
    number = as_float(value)
    if number is None:
        raise ValueError(f"Expected numeric value, got {value!r}")
    return int(round(number))


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().casefold()
    return text in {"true", "1", "yes", "y"}


def write_rows_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def load_rgb(path: Path) -> Image.Image:
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image)
        image.load()
        if image.mode == "L":
            return ImageOps.autocontrast(image).convert("RGB")
        return image.convert("RGB")


def thermal_preview(thermal: Image.Image, size: tuple[int, int] | None = None) -> Image.Image:
    preview = ImageOps.autocontrast(thermal.convert("L")).convert("RGB")
    if size is not None and preview.size != size:
        preview = preview.resize(size, Image.Resampling.BILINEAR)
    return preview


def parse_refined_bbox(row: pd.Series) -> tuple[int, int, int, int]:
    return (
        as_int(row["refined_roi_x_min_px"]),
        as_int(row["refined_roi_y_min_px"]),
        as_int(row["refined_roi_x_max_px"]),
        as_int(row["refined_roi_y_max_px"]),
    )


def crop_refined_visible_roi(row: pd.Series) -> tuple[Image.Image, Image.Image, tuple[int, int, int, int]]:
    visible = load_rgb(resolve_project_path(row["v_path"]))
    thermal = load_rgb(resolve_project_path(row["t_path"]))
    bbox = parse_refined_bbox(row)
    rotation = as_float(row.get("rotation_deg")) or 0.0
    roi = visible.crop(bbox)
    if abs(rotation) > 1e-6:
        roi = roi.rotate(
            rotation,
            resample=Image.Resampling.BICUBIC,
            expand=False,
            fillcolor=(0, 0, 0),
        )
    resized = roi.resize(thermal.size, Image.Resampling.LANCZOS)
    return roi.convert("RGB"), resized.convert("RGB"), bbox


def draw_refined_bbox_preview(row: pd.Series, bbox: tuple[int, int, int, int]) -> Image.Image:
    visible = load_rgb(resolve_project_path(row["v_path"]))
    preview = visible.copy()
    preview.thumbnail((1400, 1050), Image.Resampling.LANCZOS)
    scale_x = preview.width / visible.width
    scale_y = preview.height / visible.height
    box = (
        int(bbox[0] * scale_x),
        int(bbox[1] * scale_y),
        int(bbox[2] * scale_x),
        int(bbox[3] * scale_y),
    )
    draw = ImageDraw.Draw(preview)
    for offset in range(4):
        draw.rectangle(
            (box[0] - offset, box[1] - offset, box[2] + offset, box[3] + offset),
            outline=(20, 160, 255),
        )
    label = f"{row['image_id']} refined ROI"
    text_box = draw.textbbox((0, 0), label)
    draw.rectangle((0, 0, text_box[2] + 18, text_box[3] + 16), fill=(255, 255, 255))
    draw.text((8, 6), label, fill=(0, 0, 0))
    return preview


def save_image(path: Path, image: Image.Image) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return relative_posix(path)


def image_to_array01(image: Image.Image) -> np.ndarray:
    return np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0


def array01_to_image(array: np.ndarray) -> Image.Image:
    array = np.clip(array, 0.0, 1.0)
    return Image.fromarray((array * 255.0 + 0.5).astype(np.uint8), mode="RGB")


def colorize_labels(labels: np.ndarray) -> Image.Image:
    labels = labels.astype(np.int64)
    rgb = np.zeros((labels.shape[0], labels.shape[1], 3), dtype=np.uint8)
    rgb[..., 0] = (labels * 37) % 255
    rgb[..., 1] = (labels * 73) % 255
    rgb[..., 2] = (labels * 109) % 255
    rgb[labels == 0] = 0
    return Image.fromarray(rgb, mode="RGB")


def write_label_png(path: Path, labels: np.ndarray) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(labels.astype(np.uint16)).save(path)
    return relative_posix(path)


def classify_segment(mean_rgb: np.ndarray, mean_hsv: np.ndarray, area_fraction: float) -> tuple[str, str, str]:
    r, g, b = [float(value) for value in mean_rgb]
    hue, saturation, value = [float(value) for value in mean_hsv]
    green_excess = g - max(r, b)

    if value < 0.18:
        return "shadow", "medium", "low brightness heuristic; manual review required"
    if saturation > 0.18 and green_excess > 0.06:
        if value < 0.50 or area_fraction > 0.01:
            return "vegetation_tree", "low", "green-dominant segment; tree/low vegetation must be reviewed"
        return "grass_low_vegetation", "low", "green-dominant bright segment; review required"
    if 0.48 <= hue <= 0.66 and saturation > 0.25 and value > 0.20:
        return "water", "low", "blue/cyan heuristic; review required"
    if saturation < 0.12 and value > 0.58:
        return "concrete_pavement", "low", "bright low-saturation hardscape heuristic"
    if saturation < 0.16 and 0.20 <= value <= 0.46:
        return "asphalt_road", "low", "dark low-saturation hardscape heuristic"
    return "unclear_ignore", "low", "heuristic could not assign a reliable surface-cover suggestion"


def summarize_segments(
    labels: np.ndarray,
    image_array: np.ndarray,
    pair_id: str,
    image_id: str,
) -> list[dict[str, Any]]:
    hsv = color.rgb2hsv(image_array)
    total_pixels = labels.size
    rows: list[dict[str, Any]] = []
    for segment_id in sorted(int(value) for value in np.unique(labels) if int(value) > 0):
        mask = labels == segment_id
        ys, xs = np.where(mask)
        if ys.size == 0:
            continue
        mean_rgb = image_array[mask].mean(axis=0)
        mean_hsv = hsv[mask].mean(axis=0)
        area_px = int(mask.sum())
        area_fraction = area_px / float(total_pixels)
        suggested, confidence, note = classify_segment(mean_rgb, mean_hsv, area_fraction)
        rows.append(
            {
                "pair_id": pair_id,
                "image_id": image_id,
                "segment_id": segment_id,
                "pixel_count": area_px,
                "pixel_fraction": round(area_fraction, 8),
                "bbox_x_min": int(xs.min()),
                "bbox_y_min": int(ys.min()),
                "bbox_x_max": int(xs.max()),
                "bbox_y_max": int(ys.max()),
                "centroid_x": round(float(xs.mean()), 3),
                "centroid_y": round(float(ys.mean()), 3),
                "mean_r": round(float(mean_rgb[0] * 255.0), 3),
                "mean_g": round(float(mean_rgb[1] * 255.0), 3),
                "mean_b": round(float(mean_rgb[2] * 255.0), 3),
                "mean_h": round(float(mean_hsv[0]), 6),
                "mean_s": round(float(mean_hsv[1]), 6),
                "mean_v": round(float(mean_hsv[2]), 6),
                "suggested_class": suggested,
                "suggestion_confidence": confidence,
                "review_status": "needs_review",
                "notes": note,
            }
        )
    return rows


def annotation_rows(segment_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in segment_rows:
        rows.append(
            {
                "pair_id": row["pair_id"],
                "segment_id": row["segment_id"],
                "suggested_class": row["suggested_class"],
                "manual_class": "",
                "confidence": row["suggestion_confidence"],
                "review_status": "needs_review",
                "notes": row["notes"],
            }
        )
    return rows


def run_slic(image: Image.Image) -> tuple[np.ndarray, Image.Image, Image.Image, Image.Image, list[dict[str, Any]]]:
    image_array = image_to_array01(image)
    labels = segmentation.slic(
        image_array,
        n_segments=int(SLIC_PARAMS["n_segments"]),
        compactness=float(SLIC_PARAMS["compactness"]),
        sigma=float(SLIC_PARAMS["sigma"]),
        start_label=int(SLIC_PARAMS["start_label"]),
        channel_axis=-1,
    )
    boundaries = segmentation.mark_boundaries(
        image_array,
        labels,
        color=(1.0, 0.92, 0.05),
        mode="thick",
    )
    avg = color.label2rgb(labels, image_array, kind="avg", bg_label=0)
    avg_blend = np.clip(0.45 * image_array + 0.55 * avg, 0.0, 1.0)
    return labels, array01_to_image(boundaries), array01_to_image(avg_blend), colorize_labels(labels), []


def thumbnail_with_label(image: Image.Image, label: str, tile_size: tuple[int, int]) -> Image.Image:
    tile_width, tile_height = tile_size
    label_height = 30
    canvas = Image.new("RGB", tile_size, "white")
    body = image.copy()
    body.thumbnail((tile_width, tile_height - label_height), Image.Resampling.LANCZOS)
    x = (tile_width - body.width) // 2
    y = label_height + (tile_height - label_height - body.height) // 2
    canvas.paste(body, (x, y))
    draw = ImageDraw.Draw(canvas)
    draw.text((8, 8), label, fill=(0, 0, 0))
    return canvas


def make_contact_sheet(items: list[tuple[str, Image.Image]], path: Path, columns: int = 2) -> str:
    tile_size = (540, 405)
    rows = int(math.ceil(len(items) / columns))
    sheet = Image.new("RGB", (tile_size[0] * columns, tile_size[1] * rows), "white")
    for index, (label, image) in enumerate(items):
        tile = thumbnail_with_label(image, label, tile_size)
        x = (index % columns) * tile_size[0]
        y = (index // columns) * tile_size[1]
        sheet.paste(tile, (x, y))
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)
    return relative_posix(path)


def draw_text_label(draw: ImageDraw.ImageDraw, x: float, y: float, text: str) -> None:
    bbox = draw.textbbox((0, 0), text)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    left = int(round(x - width / 2 - 3))
    top = int(round(y - height / 2 - 2))
    right = left + width + 6
    bottom = top + height + 4
    draw.rectangle((left, top, right, bottom), fill=(255, 255, 255), outline=(0, 0, 0))
    draw.text((left + 3, top + 2), text, fill=(0, 0, 0))


def make_segment_id_label_map(
    base_image: Image.Image,
    segment_rows: list[dict[str, Any]],
    crop_box: tuple[int, int, int, int] | None = None,
    scale: int = 2,
) -> Image.Image:
    if crop_box is None:
        crop_box = (0, 0, base_image.width, base_image.height)
    x0, y0, x1, y1 = crop_box
    cropped = base_image.crop(crop_box)
    canvas = cropped.resize((cropped.width * scale, cropped.height * scale), Image.Resampling.BILINEAR)
    draw = ImageDraw.Draw(canvas)
    for row in segment_rows:
        cx = float(row["centroid_x"])
        cy = float(row["centroid_y"])
        if not (x0 <= cx < x1 and y0 <= cy < y1):
            continue
        draw_text_label(draw, (cx - x0) * scale, (cy - y0) * scale, str(row["segment_id"]))
    return canvas


def make_segment_quadrant_label_sheet(
    base_image: Image.Image,
    segment_rows: list[dict[str, Any]],
    path: Path,
) -> str:
    mid_x = base_image.width // 2
    mid_y = base_image.height // 2
    quadrants = [
        ("IDs top left", (0, 0, mid_x, mid_y)),
        ("IDs top right", (mid_x, 0, base_image.width, mid_y)),
        ("IDs bottom left", (0, mid_y, mid_x, base_image.height)),
        ("IDs bottom right", (mid_x, mid_y, base_image.width, base_image.height)),
    ]
    items = [
        (label, make_segment_id_label_map(base_image, segment_rows, crop_box=crop_box, scale=2))
        for label, crop_box in quadrants
    ]
    return make_contact_sheet(items, path, columns=2)


def category_color(value: Any) -> str:
    try:
        return LUHK_CATEGORY_COLORS.get(int(float(value)), "#eeeeee")
    except (TypeError, ValueError):
        return "#eeeeee"


def map_x_to_pixel(x: float, min_x: float, max_x: float, image_width: int) -> float:
    return (x - min_x) / (max_x - min_x) * image_width


def map_y_to_pixel(y: float, min_y: float, max_y: float, image_height: int) -> float:
    return (max_y - y) / (max_y - min_y) * image_height


def make_luhk_legend(context_rows: list[dict[str, Any]], image_id: str) -> Image.Image:
    legend = Image.new("RGB", (640, 512), "white")
    draw = ImageDraw.Draw(legend)
    draw.text((18, 18), f"Approx LUHK context\n{image_id}", fill=(0, 0, 0))
    draw.text(
        (18, 76),
        "Mapped from approximate metadata-based\nthermal footprint/grid, not from\nPart B refined image alignment.",
        fill=(70, 70, 70),
    )
    y = 172
    for row in context_rows[:8]:
        color_hex = category_color(row.get("luhk_category_code"))
        rgb = ImageColor.getrgb(color_hex)
        draw.rectangle((24, y, 54, y + 24), fill=rgb, outline=(0, 0, 0))
        label = f"{row.get('luhk_category_name', '')}: {float(row.get('proportion', 0.0)):.3f}"
        draw.text((66, y + 4), label, fill=(0, 0, 0))
        y += 38
    return legend


def make_luhk_image_overlay(
    base_image: Image.Image,
    thermal_rows: pd.DataFrame,
    thermal_footprint: pd.Series | None,
) -> Image.Image:
    base = base_image.convert("RGBA")
    if thermal_rows.empty or thermal_footprint is None:
        return base.convert("RGB")

    min_x = float(thermal_footprint["min_x_2326"])
    max_x = float(thermal_footprint["max_x_2326"])
    min_y = float(thermal_footprint["min_y_2326"])
    max_y = float(thermal_footprint["max_y_2326"])
    if max_x <= min_x or max_y <= min_y:
        return base.convert("RGB")

    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for _, cell in thermal_rows.iterrows():
        x0 = map_x_to_pixel(float(cell["cell_min_x_2326"]), min_x, max_x, base.width)
        x1 = map_x_to_pixel(float(cell["cell_max_x_2326"]), min_x, max_x, base.width)
        y0 = map_y_to_pixel(float(cell["cell_max_y_2326"]), min_y, max_y, base.height)
        y1 = map_y_to_pixel(float(cell["cell_min_y_2326"]), min_y, max_y, base.height)
        left = max(0, min(base.width, int(round(min(x0, x1)))))
        right = max(0, min(base.width, int(round(max(x0, x1)))))
        top = max(0, min(base.height, int(round(min(y0, y1)))))
        bottom = max(0, min(base.height, int(round(max(y0, y1)))))
        if right <= left or bottom <= top:
            continue
        rgb = ImageColor.getrgb(category_color(cell.get("luhk_category_code")))
        draw.rectangle((left, top, right, bottom), fill=rgb + (62,), outline=rgb + (205,))

    draw.rectangle((1, 1, base.width - 2, base.height - 2), outline=(0, 0, 0, 230), width=2)
    return Image.alpha_composite(base, layer).convert("RGB")


def luhk_context_for_pair(grid_df: pd.DataFrame, pair_id: str) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    pair_rows = grid_df.loc[grid_df["pair_id"].astype(str).eq(pair_id)].copy()
    if pair_rows.empty:
        return pair_rows, []
    thermal_rows = pair_rows.loc[pair_rows["is_thermal_covered"].map(bool_value)].copy()
    if thermal_rows.empty:
        return thermal_rows, []
    thermal_rows["weighted_area_m2"] = (
        pd.to_numeric(thermal_rows["thermal_coverage_ratio"], errors="coerce").fillna(0.0)
        * pd.to_numeric(thermal_rows["cell_area_m2"], errors="coerce").fillna(100.0)
    )
    total_area = float(thermal_rows["weighted_area_m2"].sum())
    if total_area <= 0:
        thermal_rows["weighted_area_m2"] = pd.to_numeric(
            thermal_rows["cell_area_m2"], errors="coerce"
        ).fillna(100.0)
        total_area = float(thermal_rows["weighted_area_m2"].sum())
    grouped = (
        thermal_rows.groupby(["luhk_category_code", "luhk_category_name"], dropna=False)["weighted_area_m2"]
        .sum()
        .reset_index()
        .sort_values("weighted_area_m2", ascending=False)
    )
    context_rows: list[dict[str, Any]] = []
    for _, row in grouped.iterrows():
        area = float(row["weighted_area_m2"])
        context_rows.append(
            {
                "pair_id": pair_id,
                "luhk_category_code": row["luhk_category_code"],
                "luhk_category_name": row["luhk_category_name"],
                "area_m2_weighted_by_thermal_overlap": round(area, 4),
                "proportion": round(area / total_area, 6) if total_area > 0 else 0.0,
                "spatial_uncertainty_note": (
                    "Approximate context only: LUHK is summarized from Part A approximate "
                    "north-up drone thermal footprints; Part B refined alignment is image-space only."
                ),
            }
        )
    return thermal_rows, context_rows


def footprint_for_pair(footprints_df: pd.DataFrame, pair_id: str, image_type: str) -> pd.Series | None:
    rows = footprints_df.loc[
        footprints_df["pair_id"].astype(str).eq(pair_id)
        & footprints_df["image_type"].astype(str).str.casefold().eq(image_type)
        & footprints_df["status"].astype(str).str.casefold().eq("ok")
    ]
    if rows.empty:
        return None
    return rows.iloc[0]


def plot_luhk_preview(
    thermal_rows: pd.DataFrame,
    thermal_footprint: pd.Series | None,
    image_id: str,
    output_path: Path,
) -> str:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.patches as patches
    import matplotlib.pyplot as plt

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 7))
    if thermal_rows.empty:
        ax.text(0.5, 0.5, "No thermal LUHK cells available", ha="center", va="center")
        ax.set_axis_off()
    else:
        for _, row in thermal_rows.iterrows():
            ax.add_patch(
                patches.Rectangle(
                    (float(row["cell_min_x_2326"]), float(row["cell_min_y_2326"])),
                    float(row["cell_max_x_2326"]) - float(row["cell_min_x_2326"]),
                    float(row["cell_max_y_2326"]) - float(row["cell_min_y_2326"]),
                    facecolor=category_color(row.get("luhk_category_code")),
                    edgecolor="black",
                    linewidth=0.25,
                    alpha=0.70,
                )
            )
        if thermal_footprint is not None:
            min_x = float(thermal_footprint["min_x_2326"])
            max_x = float(thermal_footprint["max_x_2326"])
            min_y = float(thermal_footprint["min_y_2326"])
            max_y = float(thermal_footprint["max_y_2326"])
            ax.add_patch(
                patches.Rectangle(
                    (min_x, min_y),
                    max_x - min_x,
                    max_y - min_y,
                    fill=False,
                    edgecolor="black",
                    linewidth=1.8,
                    label="approx thermal footprint",
                )
            )
        ax.autoscale()
        ax.set_aspect("equal")
        ax.grid(True, linewidth=0.25, alpha=0.35)
        ax.set_xlabel("Easting (EPSG:2326)")
        ax.set_ylabel("Northing (EPSG:2326)")
        ax.tick_params(axis="x", labelrotation=30)
        ax.legend(loc="best")
    ax.set_title(f"Approximate LUHK Context\n{image_id}")
    fig.tight_layout()
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return relative_posix(output_path)


def write_surface_classes() -> None:
    rows = [
        {
            "class_name": class_name,
            "description": description,
            "part_c_review_rule": "Allowed surface-cover label; manual review required before final masks.",
        }
        for class_name, description in SURFACE_CLASSES
    ]
    write_rows_csv(
        SURFACE_CLASSES_CSV,
        rows,
        ["class_name", "description", "part_c_review_rule"],
    )


def write_mask_readme() -> None:
    MASK_README.parent.mkdir(parents=True, exist_ok=True)
    MASK_README.write_text(
        "\n".join(
            [
                "# Part C masks",
                "",
                "Final class masks are intentionally not generated in Part C Round 1.",
                "Create final masks only after manual surface-cover annotations have been reviewed.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def park_early_part_b_superpixels(
    manifest_df: pd.DataFrame | None,
    image_ids: list[str],
) -> None:
    rows: list[dict[str, Any]] = []
    if manifest_df is not None and not manifest_df.empty:
        for _, row in manifest_df.iterrows():
            image_id = str(row.get("image_id", ""))
            if image_ids and image_id not in set(image_ids):
                continue
            rows.append(
                {
                    "image_id": image_id,
                    "pair_id": row.get("pair_id", ""),
                    "draft_source_stage": "early_part_b_round1",
                    "old_roi_basis": "metadata_fov_center_crop",
                    "parked_status": "parked_for_reference_only",
                    "do_not_use_as_final": "yes",
                    "reason_not_final": (
                        "Generated before Part B Round 1.1 refined alignment acceptance; "
                        "surface-cover segmentation is regenerated on the accepted refined ROI in Part C."
                    ),
                    "old_superpixel_overlay_path": row.get("round1_superpixel_overlay_path", ""),
                    "old_segment_boundary_overlay_path": row.get("round1_segment_boundary_overlay_path", ""),
                    "old_segment_id_map_path": row.get("round1_segment_id_map_path", ""),
                    "old_segment_summary_path": row.get("round1_segment_summary_path", ""),
                    "old_annotation_template_path": row.get("round1_annotation_template_path", ""),
                    "new_part_c_superpixel_dir": relative_posix(SUPERPIXEL_DIR / image_id),
                }
            )
    else:
        for image_id in image_ids:
            rows.append(
                {
                    "image_id": image_id,
                    "pair_id": "",
                    "draft_source_stage": "early_part_b_round1",
                    "old_roi_basis": "metadata_fov_center_crop",
                    "parked_status": "parked_for_reference_only",
                    "do_not_use_as_final": "yes",
                    "reason_not_final": "Manifest unavailable; old Part B superpixel assets should not be treated as final.",
                    "old_superpixel_overlay_path": f"outputs/part_b/superpixels/{image_id}_superpixel_overlay.png",
                    "old_segment_boundary_overlay_path": f"outputs/part_b/superpixels/{image_id}_segment_boundary_overlay.png",
                    "old_segment_id_map_path": f"outputs/part_b/superpixels/{image_id}_segment_id_map.png",
                    "old_segment_summary_path": f"outputs/part_b/superpixels/{image_id}_segment_summary.csv",
                    "old_annotation_template_path": f"data/annotations/part_b_round1/{image_id}_segment_annotation_template.csv",
                    "new_part_c_superpixel_dir": relative_posix(SUPERPIXEL_DIR / image_id),
                }
            )
    write_rows_csv(
        EARLY_DRAFT_MANIFEST_CSV,
        rows,
        [
            "image_id",
            "pair_id",
            "draft_source_stage",
            "old_roi_basis",
            "parked_status",
            "do_not_use_as_final",
            "reason_not_final",
            "old_superpixel_overlay_path",
            "old_segment_boundary_overlay_path",
            "old_segment_id_map_path",
            "old_segment_summary_path",
            "old_annotation_template_path",
            "new_part_c_superpixel_dir",
        ],
    )


def load_optional_csv(path: Path) -> pd.DataFrame | None:
    if not path.is_file():
        return None
    return pd.read_csv(path)


def process_pair(
    row: pd.Series,
    grid_df: pd.DataFrame,
    footprints_df: pd.DataFrame,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    pair_id = str(row["pair_id"])
    image_id = str(row["image_id"])
    pair_surface_dir = SURFACE_REVIEW_DIR / image_id
    pair_superpixel_dir = SUPERPIXEL_DIR / image_id
    pair_luhk_dir = LUHK_DIR / image_id

    refined_roi, resized_roi, bbox = crop_refined_visible_roi(row)
    thermal = load_rgb(resolve_project_path(row["t_path"]))
    thermal_rgb = thermal_preview(thermal, resized_roi.size)
    bbox_preview = draw_refined_bbox_preview(row, bbox)

    refined_roi_path = save_image(pair_surface_dir / f"{image_id}_refined_visible_roi.png", refined_roi)
    resized_roi_path = save_image(
        pair_surface_dir / f"{image_id}_refined_visible_roi_resized_to_thermal_grid.png",
        resized_roi,
    )
    bbox_preview_path = save_image(
        pair_surface_dir / f"{image_id}_refined_visible_roi_preview.png",
        bbox_preview,
    )
    thermal_preview_path = save_image(pair_surface_dir / f"{image_id}_thermal_preview_no_temperature.png", thermal_rgb)

    labels, boundary_overlay, superpixel_overlay, id_map_color, _ = run_slic(resized_roi)
    image_array = image_to_array01(resized_roi)
    segment_rows = summarize_segments(labels, image_array, pair_id, image_id)
    segment_count = len(segment_rows)

    boundary_overlay_path = save_image(pair_superpixel_dir / f"{image_id}_segment_boundary_overlay.png", boundary_overlay)
    superpixel_overlay_path = save_image(pair_superpixel_dir / f"{image_id}_superpixel_overlay.png", superpixel_overlay)
    id_map_color_path = save_image(pair_superpixel_dir / f"{image_id}_segment_id_map_color.png", id_map_color)
    id_map_16bit_path = write_label_png(pair_superpixel_dir / f"{image_id}_segment_id_map_16bit.png", labels)
    segment_id_labels_full = make_segment_id_label_map(boundary_overlay, segment_rows, scale=2)
    segment_id_labels_full_path = save_image(
        pair_superpixel_dir / f"{image_id}_segment_id_labels_full.png",
        segment_id_labels_full,
    )
    segment_id_labels_quadrants_path = make_segment_quadrant_label_sheet(
        boundary_overlay,
        segment_rows,
        pair_superpixel_dir / f"{image_id}_segment_id_labels_quadrants.png",
    )

    segment_summary_path = pair_superpixel_dir / f"{image_id}_segment_summary.csv"
    write_rows_csv(
        segment_summary_path,
        segment_rows,
        [
            "pair_id",
            "image_id",
            "segment_id",
            "pixel_count",
            "pixel_fraction",
            "bbox_x_min",
            "bbox_y_min",
            "bbox_x_max",
            "bbox_y_max",
            "centroid_x",
            "centroid_y",
            "mean_r",
            "mean_g",
            "mean_b",
            "mean_h",
            "mean_s",
            "mean_v",
            "suggested_class",
            "suggestion_confidence",
            "review_status",
            "notes",
        ],
    )

    pair_annotation_path = ANNOTATION_DIR / f"{image_id}_surface_cover_annotations.csv"
    pair_annotation_rows = annotation_rows(segment_rows)
    write_rows_csv(
        pair_annotation_path,
        pair_annotation_rows,
        ["pair_id", "segment_id", "suggested_class", "manual_class", "confidence", "review_status", "notes"],
    )

    thermal_rows, luhk_rows = luhk_context_for_pair(grid_df, pair_id)
    luhk_context_path = pair_luhk_dir / f"{image_id}_luhk_context.csv"
    write_rows_csv(
        luhk_context_path,
        luhk_rows,
        [
            "pair_id",
            "luhk_category_code",
            "luhk_category_name",
            "area_m2_weighted_by_thermal_overlap",
            "proportion",
            "spatial_uncertainty_note",
        ],
    )
    thermal_footprint = footprint_for_pair(footprints_df, pair_id, "thermal")
    luhk_preview_path = plot_luhk_preview(
        thermal_rows,
        thermal_footprint,
        image_id,
        pair_luhk_dir / f"{image_id}_luhk_context_preview.png",
    )
    luhk_overlay_on_thermal = make_luhk_image_overlay(thermal_rgb, thermal_rows, thermal_footprint)
    luhk_overlay_on_visible_roi = make_luhk_image_overlay(resized_roi, thermal_rows, thermal_footprint)
    luhk_overlay_on_thermal_path = save_image(
        pair_luhk_dir / f"{image_id}_luhk_overlay_on_thermal_preview.png",
        luhk_overlay_on_thermal,
    )
    luhk_overlay_on_visible_roi_path = save_image(
        pair_luhk_dir / f"{image_id}_luhk_overlay_on_refined_visible_roi_thermal_grid.png",
        luhk_overlay_on_visible_roi,
    )
    luhk_legend = make_luhk_legend(luhk_rows, image_id)
    luhk_preview_image = load_rgb(resolve_project_path(luhk_preview_path))
    luhk_overlay_contact_sheet_path = make_contact_sheet(
        [
            ("Approx LUHK map", luhk_preview_image),
            ("LUHK on thermal preview", luhk_overlay_on_thermal),
            ("LUHK on thermal-grid visible ROI", luhk_overlay_on_visible_roi),
            ("LUHK legend and uncertainty note", luhk_legend),
        ],
        pair_luhk_dir / f"{image_id}_luhk_overlay_contact_sheet.png",
        columns=2,
    )

    pair_contact_sheet_path = make_contact_sheet(
        [
            ("Refined ROI on visible", bbox_preview),
            ("Refined visible ROI", refined_roi),
            ("ROI resized to thermal grid", resized_roi),
            ("Thermal preview, no temperature", thermal_rgb),
            ("SLIC boundary overlay", boundary_overlay),
            ("SLIC superpixel overlay", superpixel_overlay),
        ],
        pair_surface_dir / f"{image_id}_part_c_review_contact_sheet.png",
        columns=2,
    )
    segmentation_contact_sheet_path = make_contact_sheet(
        [
            ("Thermal-grid visible ROI", resized_roi),
            ("Segment boundary overlay", boundary_overlay),
            ("Superpixel average overlay", superpixel_overlay),
            ("Segment ID color map", id_map_color),
            ("Segment IDs full map", segment_id_labels_full),
            ("Segment IDs quadrants", load_rgb(resolve_project_path(segment_id_labels_quadrants_path))),
        ],
        pair_superpixel_dir / f"{image_id}_segmentation_contact_sheet.png",
        columns=2,
    )

    dominant_luhk = luhk_rows[0] if luhk_rows else {}
    summary_row = {
        "pair_id": pair_id,
        "image_id": image_id,
        "part_b_alignment_quality": row.get("alignment_quality", ""),
        "part_b_refined_transform_matrix_json": row.get("final_transform_matrix_json", ""),
        "refined_roi_bbox_px": json.dumps(
            {
                "x_min": bbox[0],
                "y_min": bbox[1],
                "x_max": bbox[2],
                "y_max": bbox[3],
            }
        ),
        "refined_visible_roi_path": refined_roi_path,
        "refined_visible_roi_resized_to_thermal_grid_path": resized_roi_path,
        "visible_roi_preview_path": bbox_preview_path,
        "thermal_preview_path": thermal_preview_path,
        "luhk_context_csv_path": relative_posix(luhk_context_path),
        "luhk_context_preview_path": luhk_preview_path,
        "luhk_overlay_on_thermal_preview_path": luhk_overlay_on_thermal_path,
        "luhk_overlay_on_refined_visible_roi_path": luhk_overlay_on_visible_roi_path,
        "luhk_overlay_contact_sheet_path": luhk_overlay_contact_sheet_path,
        "dominant_luhk_class": dominant_luhk.get("luhk_category_name", ""),
        "dominant_luhk_proportion": dominant_luhk.get("proportion", ""),
        "segmentation_method": "skimage.segmentation.slic",
        "slic_n_segments_requested": SLIC_PARAMS["n_segments"],
        "slic_compactness": SLIC_PARAMS["compactness"],
        "slic_sigma": SLIC_PARAMS["sigma"],
        "segmentation_image_basis": SLIC_PARAMS["image_basis"],
        "thermal_grid_width_px": resized_roi.width,
        "thermal_grid_height_px": resized_roi.height,
        "segment_count": segment_count,
        "segment_boundary_overlay_path": boundary_overlay_path,
        "superpixel_overlay_path": superpixel_overlay_path,
        "segment_id_map_color_path": id_map_color_path,
        "segment_id_map_16bit_path": id_map_16bit_path,
        "segment_id_labels_full_path": segment_id_labels_full_path,
        "segment_id_labels_quadrants_path": segment_id_labels_quadrants_path,
        "segment_summary_path": relative_posix(segment_summary_path),
        "pair_annotation_csv_path": relative_posix(pair_annotation_path),
        "pair_review_contact_sheet_path": pair_contact_sheet_path,
        "segmentation_contact_sheet_path": segmentation_contact_sheet_path,
        "limitations": (
            "LUHK context is approximate and not surface cover; SLIC suggestions are heuristic "
            "and require manual review before masks or thermal extraction."
        ),
    }
    return summary_row, luhk_rows, pair_annotation_rows


def write_round1_summary_md(summary_rows: list[dict[str, Any]]) -> None:
    lines = [
        "# Part C Round 1 Summary",
        "",
        "Part C Round 1 prepares LUHK context and semi-automatic surface-cover review outputs for the five accepted Part B pilot pairs.",
        "",
        "No thermal temperature extraction, supervised model training, manual annotation ingestion, or final mask generation was performed.",
        "",
        "## Inputs From Accepted Part B",
        "",
        f"- Alignment summary: `{relative_posix(PART_B_ALIGNMENT_SUMMARY_CSV)}`",
        f"- Accepted refined ROI columns: `refined_roi_*`, `final_transform_matrix_json`",
        f"- Visible camera profiles: `{relative_posix(VISIBLE_CAMERA_PROFILES_CSV)}`",
        f"- Thermal metadata table: `{relative_posix(THERMAL_METADATA_CSV)}`",
        "",
        "## Segmentation Parameters",
        "",
        f"- Method: `skimage.segmentation.slic`",
        f"- Requested segments: `{SLIC_PARAMS['n_segments']}`",
        f"- Compactness: `{SLIC_PARAMS['compactness']}`",
        f"- Sigma: `{SLIC_PARAMS['sigma']}`",
        f"- Image basis: `{SLIC_PARAMS['image_basis']}`",
        "",
        "## Image Interpretation Notes",
        "",
        "- Thermal preview images are grayscale contrast previews only; the original thermal JPG files are not modified.",
        "- `refined_visible_roi` is the accepted Part B crop at visible-image pixels.",
        "- `refined_visible_roi_resized_to_thermal_grid` is the same crop resampled to the thermal image grid, usually `640x512`; it should look visually similar in contact sheets.",
        "- LUHK image overlays use approximate metadata-based thermal footprints, so they are for uncertainty review rather than precise surface-cover labeling.",
        "",
        "## Pair Outputs To Inspect",
        "",
    ]
    for row in summary_rows:
        lines.extend(
            [
                f"### {row['image_id']}",
                "",
                f"- Dominant LUHK context: `{row['dominant_luhk_class']}` ({row['dominant_luhk_proportion']})",
                f"- LUHK overlay contact sheet: `{row['luhk_overlay_contact_sheet_path']}`",
                f"- Refined ROI: `{row['refined_visible_roi_path']}`",
                f"- Thermal-grid ROI: `{row['refined_visible_roi_resized_to_thermal_grid_path']}`",
                f"- Review contact sheet: `{row['pair_review_contact_sheet_path']}`",
                f"- Segmentation contact sheet: `{row['segmentation_contact_sheet_path']}`",
                f"- Segment ID full map: `{row['segment_id_labels_full_path']}`",
                f"- Segment ID quadrant map: `{row['segment_id_labels_quadrants_path']}`",
                f"- Segment summary: `{row['segment_summary_path']}`",
                f"- Annotation CSV to fill: `{row['pair_annotation_csv_path']}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Annotation Files",
            "",
            f"- Main annotation file: `{relative_posix(MAIN_ANNOTATION_CSV)}`",
            f"- Approved class list: `{relative_posix(SURFACE_CLASSES_CSV)}`",
            "",
            "Use the segment ID label maps to locate each `segment_id`, then fill `manual_class` during review. Suggested classes are low-confidence heuristics, not final labels.",
            "",
            "## Parked Draft Assets",
            "",
            f"- Early Part B superpixel manifest: `{relative_posix(EARLY_DRAFT_MANIFEST_CSV)}`",
            "",
            "Those early assets were generated before Part B refined alignment acceptance from the old center-crop ROI and are reference only.",
            "",
            "## Known Limitations",
            "",
            "- LUHK context comes from approximate metadata-based drone footprints and is broad land-use only.",
            "- LUHK overlays can show footprint mismatch, but they are not a corrected georegistration.",
            "- Surface-cover segmentation is generated from visible imagery only.",
            "- The thermal grid is used as the target image grid, but no thermal temperatures are extracted.",
            "- Segment suggestions are heuristic and require manual review.",
            "- Final masks are intentionally withheld until manual labels are accepted.",
            "",
            "## Next Manual Task",
            "",
            f"Review the contact sheets, then fill `manual_class` in `{relative_posix(MAIN_ANNOTATION_CSV)}` or the per-pair annotation CSVs.",
            "",
        ]
    )
    ROUND1_SUMMARY_MD.parent.mkdir(parents=True, exist_ok=True)
    ROUND1_SUMMARY_MD.write_text("\n".join(lines), encoding="utf-8")


def write_manual_review_guide(summary_rows: list[dict[str, Any]]) -> None:
    lines = [
        "# Part C Manual Review Guide",
        "",
        "Use this guide to review the Part C Round 1 pilot package. Part C labels are manually reviewed candidates, not ground truth.",
        "",
        "## Review Order",
        "",
        "1. Open the LUHK overlay contact sheet for a pair and judge whether the approximate LUHK footprint looks spatially plausible.",
        "2. Open the Part C review contact sheet and confirm the refined visible ROI covers the accepted thermal target area.",
        "3. Open the segment ID quadrant map to locate segment IDs.",
        "4. Fill `manual_class` in the main annotation CSV or the per-pair annotation CSV.",
        "5. Update `review_status` to `reviewed` only after the segment has been checked.",
        "",
        "## Segment ID Lookup",
        "",
        "The annotation CSV uses `segment_id`. To find a segment:",
        "",
        "- use `segment_id_labels_quadrants.png` first, because it is zoomed and less crowded",
        "- use `segment_id_labels_full.png` for whole-image orientation",
        "- use `segment_summary.csv` if you need centroid or bounding-box coordinates",
        "",
        "## Labeling Rules",
        "",
        "- Label surface cover from the visible ROI, not from LUHK.",
        "- Use LUHK only as broad land-use context and uncertainty evidence.",
        "- If a segment is mixed, label the dominant visible surface when one class clearly dominates.",
        "- If a segment is too mixed, shadowed, or ambiguous, use `unclear_ignore`.",
        "- Keep `suggested_class` as-is; put your decision in `manual_class`.",
        "- Confidence can stay low/medium/high according to your certainty.",
        "",
        "## Per-Pair Files",
        "",
    ]
    for row in summary_rows:
        lines.extend(
            [
                f"### {row['image_id']}",
                "",
                f"- LUHK overlay: `{row['luhk_overlay_contact_sheet_path']}`",
                f"- Review contact sheet: `{row['pair_review_contact_sheet_path']}`",
                f"- Segment ID quadrants: `{row['segment_id_labels_quadrants_path']}`",
                f"- Segment summary: `{row['segment_summary_path']}`",
                f"- Annotation CSV: `{row['pair_annotation_csv_path']}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Stop Conditions",
            "",
            "- Do not create final masks from these segments yet.",
            "- Do not extract thermal temperature yet.",
            "- Do not train a prediction model from these pilot labels.",
            "",
        ]
    )
    MANUAL_REVIEW_GUIDE_MD.parent.mkdir(parents=True, exist_ok=True)
    MANUAL_REVIEW_GUIDE_MD.write_text("\n".join(lines), encoding="utf-8")


def ensure_structure() -> None:
    for path in [ANNOTATION_DIR, LUHK_DIR, SURFACE_REVIEW_DIR, SUPERPIXEL_DIR, SUMMARY_DIR, MASK_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def main() -> int:
    ensure_structure()
    required = [PART_B_ALIGNMENT_SUMMARY_CSV, GRID_CSV, FOOTPRINTS_CSV]
    missing = [relative_posix(path) for path in required if not path.is_file()]
    if missing:
        print("Missing required Part C inputs:", file=sys.stderr)
        for path in missing:
            print(f"- {path}", file=sys.stderr)
        return 1

    alignment_df = pd.read_csv(PART_B_ALIGNMENT_SUMMARY_CSV)
    grid_df = pd.read_csv(GRID_CSV)
    footprints_df = pd.read_csv(FOOTPRINTS_CSV)
    manifest_df = load_optional_csv(PART_B_LOCAL_MANIFEST_CSV)

    accepted_df = alignment_df.copy()
    if "alignment_quality" in accepted_df.columns:
        accepted_df = accepted_df.loc[accepted_df["alignment_quality"].astype(str).str.casefold().eq("acceptable")]
    if accepted_df.empty:
        print("No accepted Part B alignment rows found.", file=sys.stderr)
        return 1

    write_surface_classes()
    write_mask_readme()
    image_ids = [str(value) for value in accepted_df["image_id"].tolist()]
    park_early_part_b_superpixels(manifest_df, image_ids)

    summary_rows: list[dict[str, Any]] = []
    all_luhk_rows: list[dict[str, Any]] = []
    all_annotation_rows: list[dict[str, Any]] = []
    for _, row in accepted_df.iterrows():
        summary_row, luhk_rows, pair_annotation_rows = process_pair(row, grid_df, footprints_df)
        summary_rows.append(summary_row)
        all_luhk_rows.extend(luhk_rows)
        all_annotation_rows.extend(pair_annotation_rows)

    write_rows_csv(
        LUHK_SUMMARY_CSV,
        all_luhk_rows,
        [
            "pair_id",
            "luhk_category_code",
            "luhk_category_name",
            "area_m2_weighted_by_thermal_overlap",
            "proportion",
            "spatial_uncertainty_note",
        ],
    )
    write_rows_csv(
        MAIN_ANNOTATION_CSV,
        all_annotation_rows,
        ["pair_id", "segment_id", "suggested_class", "manual_class", "confidence", "review_status", "notes"],
    )
    write_rows_csv(
        ROUND1_SUMMARY_CSV,
        summary_rows,
        [
            "pair_id",
            "image_id",
            "part_b_alignment_quality",
            "part_b_refined_transform_matrix_json",
            "refined_roi_bbox_px",
            "refined_visible_roi_path",
            "refined_visible_roi_resized_to_thermal_grid_path",
            "visible_roi_preview_path",
            "thermal_preview_path",
            "luhk_context_csv_path",
            "luhk_context_preview_path",
            "luhk_overlay_on_thermal_preview_path",
            "luhk_overlay_on_refined_visible_roi_path",
            "luhk_overlay_contact_sheet_path",
            "dominant_luhk_class",
            "dominant_luhk_proportion",
            "segmentation_method",
            "slic_n_segments_requested",
            "slic_compactness",
            "slic_sigma",
            "segmentation_image_basis",
            "thermal_grid_width_px",
            "thermal_grid_height_px",
            "segment_count",
            "segment_boundary_overlay_path",
            "superpixel_overlay_path",
            "segment_id_map_color_path",
            "segment_id_map_16bit_path",
            "segment_id_labels_full_path",
            "segment_id_labels_quadrants_path",
            "segment_summary_path",
            "pair_annotation_csv_path",
            "pair_review_contact_sheet_path",
            "segmentation_contact_sheet_path",
            "limitations",
        ],
    )
    write_round1_summary_md(summary_rows)
    write_manual_review_guide(summary_rows)

    print(f"Part C pilot pairs processed: {len(summary_rows)}")
    print(f"Total annotation rows: {len(all_annotation_rows)}")
    print(f"Main annotation CSV: {relative_posix(MAIN_ANNOTATION_CSV)}")
    print(f"Round 1 summary: {relative_posix(ROUND1_SUMMARY_MD)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
