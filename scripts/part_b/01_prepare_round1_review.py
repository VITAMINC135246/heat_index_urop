#!/usr/bin/env python3
"""Prepare Part B Round 1 V/T ROI and surface-cover review packages.

This script is intentionally semi-automatic. It estimates a visible-image ROI
for a small pilot set, creates review images, and generates SLIC superpixels
plus annotation templates. It does not extract thermal temperature data and it
does not train a prediction model.
"""

from __future__ import annotations

import argparse
import importlib.util
import math
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageOps


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from camera_profiles import (  # noqa: E402
    MATRICE_4T_CAMERA_RULES,
    classify_matrice_4t_camera,
    resolve_camera_parameters,
)
from table_io import read_table, write_rows  # noqa: E402


CANDIDATE_PAIRS_XLSX = PROJECT_ROOT / "data" / "metadata" / "pilot_candidate_pairs.xlsx"
DJI_METADATA_XLSX = PROJECT_ROOT / "data" / "metadata" / "dji_image_metadata.xlsx"
VISIBLE_CAMERA_PROFILES_XLSX = PROJECT_ROOT / "data" / "metadata" / "visible_camera_profiles.xlsx"
PART_B_PILOT_PAIRS_XLSX = PROJECT_ROOT / "data" / "metadata" / "part_b_pilot_pairs.xlsx"
ANNOTATION_DIR = PROJECT_ROOT / "data" / "annotations" / "part_b_round1"
COMBINED_ANNOTATION_XLSX = PROJECT_ROOT / "data" / "annotations" / "part_b_round1_segment_annotations.xlsx"
SURFACE_CLASSES_XLSX = PROJECT_ROOT / "data" / "annotations" / "surface_cover_classes.xlsx"
REVIEW_DIR = PROJECT_ROOT / "outputs" / "part_b" / "review_packages"
OVERLAY_DIR = PROJECT_ROOT / "outputs" / "part_b" / "overlays"
SUPERPIXEL_DIR = PROJECT_ROOT / "outputs" / "part_b" / "superpixels"
SUMMARY_DIR = PROJECT_ROOT / "outputs" / "part_b" / "summaries"
ROI_SUMMARY_XLSX = SUMMARY_DIR / "part_b_round1_roi_estimates.xlsx"
SEGMENT_SUMMARY_XLSX = SUMMARY_DIR / "part_b_round1_segments.xlsx"
SUMMARY_MD = SUMMARY_DIR / "part_b_round1_summary.md"

PILOT_COUNT = 5
SLIC_SEGMENTS = 250
SLIC_COMPACTNESS = 12.0

SURFACE_CLASSES = [
    ("roof", "Building roof or roof-like structure visible from above."),
    ("concrete_pavement", "Concrete, brick, plaza, footpath, or hard paving that is not asphalt."),
    ("asphalt_road", "Asphalt road, parking area, or similar dark paved surface."),
    ("vegetation_tree", "Tree canopy or elevated woody vegetation."),
    ("grass_low_vegetation", "Grass, low shrubs, or low-growing vegetation."),
    ("bare_soil", "Exposed soil, rock, or unpaved ground."),
    ("water", "Visible water surface."),
    ("shadow", "Shadow or strongly shaded region requiring manual interpretation."),
    ("vehicle_temporary_object", "Vehicle, pedestrian, equipment, or temporary object."),
    ("unclear_ignore", "Unclear, blurred, invalid, edge, or excluded region."),
]


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
    text = str(value)
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", text)
    return text.strip("_") or "item"


def clean_value(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except TypeError:
        pass
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


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


def ensure_directories() -> None:
    for directory in [
        VISIBLE_CAMERA_PROFILES_XLSX.parent,
        PART_B_PILOT_PAIRS_XLSX.parent,
        ANNOTATION_DIR,
        REVIEW_DIR,
        OVERLAY_DIR,
        SUPERPIXEL_DIR,
        SUMMARY_DIR,
    ]:
        directory.mkdir(parents=True, exist_ok=True)


def check_inputs() -> None:
    missing = [path for path in [CANDIDATE_PAIRS_XLSX, DJI_METADATA_XLSX] if not path.exists()]
    if missing:
        names = ", ".join(relative_posix(path) for path in missing)
        raise FileNotFoundError(f"Missing required Part A metadata input(s): {names}")


def load_metadata() -> tuple[pd.DataFrame, pd.DataFrame]:
    candidates = read_table(CANDIDATE_PAIRS_XLSX, dtype=str).fillna("")
    metadata = read_table(DJI_METADATA_XLSX, dtype=str).fillna("")
    return candidates, metadata


def path_exists_from_row(row: pd.Series, key: str) -> bool:
    value = row.get(key, "")
    return bool(value) and resolve_project_path(value).exists()


def select_pilot_pairs(candidates: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    if PART_B_PILOT_PAIRS_XLSX.exists():
        existing = read_table(PART_B_PILOT_PAIRS_XLSX, dtype=str).fillna("")
        existing_ids = [pid for pid in existing.get("pair_id", []) if pid]
        selected = candidates.loc[candidates["pair_id"].isin(existing_ids)].copy()
        order = {pair_id: index for index, pair_id in enumerate(existing_ids)}
        selected["part_b_existing_order"] = selected["pair_id"].map(order)
        selected = selected.sort_values("part_b_existing_order")
        if len(selected) == len(existing_ids):
            return selected.head(PILOT_COUNT), "existing part_b_pilot_pairs.xlsx"

    work = candidates.copy()
    work["site_group_norm"] = work.get("site_group", "").astype(str).str.casefold()
    work["dataset_norm"] = work.get("dataset_folder", "").astype(str).str.casefold()
    work["has_local_v"] = work.apply(lambda row: path_exists_from_row(row, "v_path"), axis=1)
    work["has_local_t"] = work.apply(lambda row: path_exists_from_row(row, "t_path"), axis=1)
    work["priority_rank"] = work.get("candidate_priority", "").map({"high": 0, "medium": 1, "low": 2}).fillna(9)
    work["existing_grid_rank"] = work.get("existing_pilot_grid_output", "").map({"yes": 0, "no": 1}).fillna(2)
    work["sample_0016_rank"] = work.get("contains_sample_0016", "").map({"no": 0, "yes": 1}).fillna(2)
    work["capture_sort"] = work.get("visible_capture_datetime", "")

    filtered = work.loc[
        work["site_group_norm"].eq("hkust")
        & ~work["dataset_norm"].str.contains("gardenhill", na=False)
        & work["has_local_v"]
        & work["has_local_t"]
    ].copy()
    filtered = filtered.sort_values(
        ["priority_rank", "existing_grid_rank", "sample_0016_rank", "capture_sort", "pair_id"],
        kind="stable",
    )
    if len(filtered) < PILOT_COUNT:
        raise ValueError(f"Only {len(filtered)} usable HKUST local V/T pairs found; need {PILOT_COUNT}.")
    return filtered.head(PILOT_COUNT), "selected from pilot_candidate_pairs.xlsx"


def metadata_row(metadata: pd.DataFrame, pair_id: str, image_type: str) -> pd.Series:
    rows = metadata.loc[
        metadata["pair_id"].astype(str).eq(str(pair_id))
        & metadata["image_type"].astype(str).str.casefold().eq(image_type)
    ]
    if rows.empty:
        raise ValueError(f"No {image_type} metadata row found for pair_id={pair_id}")
    return rows.iloc[0]


def build_visible_camera_profiles(metadata: pd.DataFrame) -> list[dict[str, Any]]:
    visible = metadata.loc[metadata["image_type"].astype(str).str.casefold().eq("visible")].copy()
    classifications = [classify_matrice_4t_camera(row) for _, row in visible.iterrows()]
    visible["profile_key"] = [item["camera_key"] for item in classifications]
    visible["profile_confidence"] = [item["confidence"] for item in classifications]

    rows: list[dict[str, Any]] = []
    for key in ["wide_visible", "medium_tele_visible", "tele_visible"]:
        rule = MATRICE_4T_CAMERA_RULES[key]
        subset = visible.loc[visible["profile_key"].eq(key)]
        rows.append(
            {
                "profile_key": key,
                "image_type": "visible",
                "expected_camera": rule["notes"],
                "rule_actual_focal_length_mm": rule["actual_focal_length_mm"],
                "rule_focal_length_35mm": rule["focal_length_35mm"],
                "rule_f_number": rule["f_number"],
                "sensor": rule["sensor"],
                "observed_rows": int(len(subset)),
                "observed_image_widths": ";".join(sorted(set(subset.get("image_width", pd.Series(dtype=str)).astype(str)))),
                "observed_image_heights": ";".join(sorted(set(subset.get("image_height", pd.Series(dtype=str)).astype(str)))),
                "observed_focal_lengths_mm": ";".join(sorted(set(subset.get("focal_length", pd.Series(dtype=str)).astype(str)))),
                "observed_focal_lengths_35mm": ";".join(sorted(set(subset.get("focal_length_35mm", pd.Series(dtype=str)).astype(str)))),
                "confidence_rule": "high when focal_length_35mm and actual focal length match the Matrice 4T rule",
                "notes": "Profile inferred from per-image EXIF/XMP focal metadata; visual QA still required.",
            }
        )

    unknown = visible.loc[~visible["profile_key"].isin(["wide_visible", "medium_tele_visible", "tele_visible"])]
    if not unknown.empty:
        rows.append(
            {
                "profile_key": "visible_unclassified",
                "image_type": "visible",
                "expected_camera": "Unclassified visible camera",
                "rule_actual_focal_length_mm": "",
                "rule_focal_length_35mm": "",
                "rule_f_number": "",
                "sensor": "",
                "observed_rows": int(len(unknown)),
                "observed_image_widths": ";".join(sorted(set(unknown.get("image_width", pd.Series(dtype=str)).astype(str)))),
                "observed_image_heights": ";".join(sorted(set(unknown.get("image_height", pd.Series(dtype=str)).astype(str)))),
                "observed_focal_lengths_mm": ";".join(sorted(set(unknown.get("focal_length", pd.Series(dtype=str)).astype(str)))),
                "observed_focal_lengths_35mm": ";".join(sorted(set(unknown.get("focal_length_35mm", pd.Series(dtype=str)).astype(str)))),
                "confidence_rule": "needs_review",
                "notes": "Rows that do not match the current Matrice 4T visible focal-length rules.",
            }
        )
    return rows


def write_rows_xlsx(path: Path, rows: list[dict[str, Any]], columns: list[str] | None = None) -> None:
    write_rows(path, rows, columns)


def write_surface_classes() -> None:
    rows = [
        {"class_name": name, "notes": notes, "part_b_round1_allowed": "yes"}
        for name, notes in SURFACE_CLASSES
    ]
    write_rows_xlsx(SURFACE_CLASSES_XLSX, rows, ["class_name", "notes", "part_b_round1_allowed"])


def positive_fov(params: dict[str, Any]) -> bool:
    return (
        as_float(params.get("horizontal_fov_deg")) is not None
        and as_float(params.get("vertical_fov_deg")) is not None
        and as_float(params.get("horizontal_fov_deg")) > 0
        and as_float(params.get("vertical_fov_deg")) > 0
    )


def estimate_visible_roi(
    visible_meta: pd.Series,
    thermal_meta: pd.Series,
    visible_size: tuple[int, int],
    thermal_size: tuple[int, int],
) -> dict[str, Any]:
    visible_params = resolve_camera_parameters(visible_meta, "visible", visible_size)
    thermal_params = resolve_camera_parameters(thermal_meta, "thermal", thermal_size)
    visible_width, visible_height = visible_size
    thermal_width, thermal_height = thermal_size
    target_aspect = thermal_width / thermal_height

    if positive_fov(visible_params) and positive_fov(thermal_params):
        visible_hfov = float(visible_params["horizontal_fov_deg"])
        visible_vfov = float(visible_params["vertical_fov_deg"])
        thermal_hfov = float(thermal_params["horizontal_fov_deg"])
        thermal_vfov = float(thermal_params["vertical_fov_deg"])
        width_ratio = math.tan(math.radians(thermal_hfov / 2.0)) / math.tan(math.radians(visible_hfov / 2.0))
        height_ratio = math.tan(math.radians(thermal_vfov / 2.0)) / math.tan(math.radians(visible_vfov / 2.0))
        crop_width = int(round(visible_width * min(width_ratio, 1.0)))
        crop_height = int(round(visible_height * min(height_ratio, 1.0)))
        method = "metadata_fov_center_crop"
        confidence = "medium"
        notes = (
            "Centered crop from visible image using thermal/visible FOV ratio; "
            "no feature matching or georeferenced registration applied."
        )
    else:
        width_ratio = None
        height_ratio = None
        crop_height = int(round(visible_height * 0.55))
        crop_width = int(round(crop_height * target_aspect))
        if crop_width > visible_width:
            crop_width = int(round(visible_width * 0.55))
            crop_height = int(round(crop_width / target_aspect))
        method = "center_crop_thermal_aspect_fallback"
        confidence = "low"
        notes = (
            "Fallback centered crop matching thermal aspect; metadata FOV was incomplete. "
            "Manual review is required before using this ROI."
        )

    crop_width = max(1, min(crop_width, visible_width))
    crop_height = max(1, min(crop_height, visible_height))
    current_aspect = crop_width / crop_height
    if abs(current_aspect - target_aspect) > 0.01:
        if current_aspect > target_aspect:
            crop_width = int(round(crop_height * target_aspect))
        else:
            crop_height = int(round(crop_width / target_aspect))
        crop_width = max(1, min(crop_width, visible_width))
        crop_height = max(1, min(crop_height, visible_height))

    x_min = int(round((visible_width - crop_width) / 2.0))
    y_min = int(round((visible_height - crop_height) / 2.0))
    x_max = x_min + crop_width
    y_max = y_min + crop_height

    return {
        "roi_method": method,
        "roi_confidence": confidence,
        "roi_x_min_px": x_min,
        "roi_y_min_px": y_min,
        "roi_x_max_px": x_max,
        "roi_y_max_px": y_max,
        "roi_width_px": crop_width,
        "roi_height_px": crop_height,
        "roi_width_fraction_of_visible": crop_width / visible_width,
        "roi_height_fraction_of_visible": crop_height / visible_height,
        "thermal_visible_fov_width_ratio": width_ratio if width_ratio is not None else "",
        "thermal_visible_fov_height_ratio": height_ratio if height_ratio is not None else "",
        "visible_horizontal_fov_deg": visible_params.get("horizontal_fov_deg") or "",
        "visible_vertical_fov_deg": visible_params.get("vertical_fov_deg") or "",
        "thermal_horizontal_fov_deg": thermal_params.get("horizontal_fov_deg") or "",
        "thermal_vertical_fov_deg": thermal_params.get("vertical_fov_deg") or "",
        "visible_fov_source": visible_params.get("fov_source", ""),
        "thermal_fov_source": thermal_params.get("fov_source", ""),
        "roi_notes": notes,
    }


def load_preview_image(path: Path) -> Image.Image:
    with Image.open(path) as image:
        image.load()
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        elif image.mode == "L":
            image = ImageOps.autocontrast(image).convert("RGB")
        else:
            image = image.convert("RGB")
        return image


def thumbnail_copy(image: Image.Image, max_size: tuple[int, int]) -> Image.Image:
    copy = image.copy()
    copy.thumbnail(max_size, Image.Resampling.LANCZOS)
    return copy


def save_labelled_image(image: Image.Image, path: Path, label: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    labelled = image.copy()
    draw = ImageDraw.Draw(labelled)
    margin = 8
    bbox = draw.textbbox((0, 0), label)
    width = bbox[2] - bbox[0] + margin * 2
    height = bbox[3] - bbox[1] + margin * 2
    draw.rectangle((0, 0, width, height), fill=(255, 255, 255))
    draw.text((margin, margin), label, fill=(0, 0, 0))
    labelled.save(path)


def draw_roi_overlay(visible: Image.Image, roi: dict[str, Any]) -> Image.Image:
    preview = thumbnail_copy(visible, (1400, 1050))
    scale_x = preview.width / visible.width
    scale_y = preview.height / visible.height
    box = (
        int(roi["roi_x_min_px"] * scale_x),
        int(roi["roi_y_min_px"] * scale_y),
        int(roi["roi_x_max_px"] * scale_x),
        int(roi["roi_y_max_px"] * scale_y),
    )
    draw = ImageDraw.Draw(preview)
    for offset in range(4):
        draw.rectangle(
            (box[0] - offset, box[1] - offset, box[2] + offset, box[3] + offset),
            outline=(255, 45, 45),
        )
    return preview


def normalize_thermal_preview(thermal: Image.Image, size: tuple[int, int]) -> Image.Image:
    preview = thermal.convert("RGB")
    preview = ImageOps.autocontrast(preview)
    if preview.size != size:
        preview = preview.resize(size, Image.Resampling.BILINEAR)
    return preview


def labelled_tile(image: Image.Image, label: str, tile_size: tuple[int, int]) -> Image.Image:
    tile_width, tile_height = tile_size
    canvas = Image.new("RGB", tile_size, "white")
    draw = ImageDraw.Draw(canvas)
    label_height = 24
    body = thumbnail_copy(image, (tile_width, tile_height - label_height))
    x = (tile_width - body.width) // 2
    y = label_height + (tile_height - label_height - body.height) // 2
    canvas.paste(body, (x, y))
    draw.text((8, 6), label, fill=(0, 0, 0))
    return canvas


def make_contact_sheet(items: list[tuple[str, Image.Image]], path: Path) -> None:
    tile_size = (520, 390)
    columns = 2
    rows = math.ceil(len(items) / columns)
    sheet = Image.new("RGB", (tile_size[0] * columns, tile_size[1] * rows), "white")
    for index, (label, image) in enumerate(items):
        tile = labelled_tile(image, label, tile_size)
        x = (index % columns) * tile_size[0]
        y = (index // columns) * tile_size[1]
        sheet.paste(tile, (x, y))
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)


def generate_review_images(
    image_id: str,
    visible: Image.Image,
    thermal: Image.Image,
    roi: dict[str, Any],
) -> tuple[dict[str, str], Image.Image, Image.Image]:
    package_dir = REVIEW_DIR / safe_name(image_id)
    package_dir.mkdir(parents=True, exist_ok=True)

    box = (
        int(roi["roi_x_min_px"]),
        int(roi["roi_y_min_px"]),
        int(roi["roi_x_max_px"]),
        int(roi["roi_y_max_px"]),
    )
    visible_preview = thumbnail_copy(visible, (1400, 1050))
    thermal_preview = normalize_thermal_preview(thermal, thermal.size)
    roi_overlay = draw_roi_overlay(visible, roi)
    roi_crop = visible.crop(box)
    roi_resized = roi_crop.resize(thermal.size, Image.Resampling.LANCZOS)
    thermal_for_overlay = normalize_thermal_preview(thermal, thermal.size)
    blend_overlay = Image.blend(roi_resized.convert("RGB"), thermal_for_overlay.convert("RGB"), 0.45)

    side_by_side = Image.new("RGB", (thermal.size[0] * 2, thermal.size[1] + 34), "white")
    side_by_side.paste(roi_resized, (0, 34))
    side_by_side.paste(thermal_for_overlay, (thermal.size[0], 34))
    draw = ImageDraw.Draw(side_by_side)
    draw.text((8, 8), "Visible ROI resized to thermal grid", fill=(0, 0, 0))
    draw.text((thermal.size[0] + 8, 8), "Thermal image preview", fill=(0, 0, 0))

    paths = {
        "review_package_dir": relative_posix(package_dir),
        "visible_preview_path": relative_posix(package_dir / "01_original_visible_preview.png"),
        "thermal_preview_path": relative_posix(package_dir / "02_original_thermal_preview.png"),
        "visible_roi_overlay_path": relative_posix(package_dir / "03_estimated_visible_roi_overlay.png"),
        "visible_roi_resized_path": relative_posix(package_dir / "04_visible_roi_resized_to_thermal_grid.png"),
        "thermal_visible_overlay_path": relative_posix(package_dir / "05_thermal_visible_blend_overlay.png"),
        "side_by_side_path": relative_posix(package_dir / "06_side_by_side_visible_roi_and_thermal.png"),
        "contact_sheet_path": relative_posix(package_dir / "07_contact_sheet.png"),
    }

    save_labelled_image(visible_preview, PROJECT_ROOT / paths["visible_preview_path"], "Original visible preview")
    save_labelled_image(thermal_preview, PROJECT_ROOT / paths["thermal_preview_path"], "Original thermal preview")
    save_labelled_image(roi_overlay, PROJECT_ROOT / paths["visible_roi_overlay_path"], "Estimated visible ROI")
    save_labelled_image(roi_resized, PROJECT_ROOT / paths["visible_roi_resized_path"], "Visible ROI resized to thermal grid")
    save_labelled_image(blend_overlay, PROJECT_ROOT / paths["thermal_visible_overlay_path"], "Visible ROI / thermal blend preview")
    side_by_side.save(PROJECT_ROOT / paths["side_by_side_path"])

    overlay_roi_path = OVERLAY_DIR / f"{safe_name(image_id)}_visible_roi_overlay.png"
    overlay_blend_path = OVERLAY_DIR / f"{safe_name(image_id)}_thermal_visible_blend_overlay.png"
    roi_overlay.save(overlay_roi_path)
    blend_overlay.save(overlay_blend_path)
    paths["overlay_dir_visible_roi_overlay_path"] = relative_posix(overlay_roi_path)
    paths["overlay_dir_thermal_visible_overlay_path"] = relative_posix(overlay_blend_path)

    contact_items = [
        ("Visible preview", visible_preview),
        ("Thermal preview", thermal_preview),
        ("Estimated visible ROI", roi_overlay),
        ("ROI resized to T grid", roi_resized),
        ("Thermal/visible blend", blend_overlay),
        ("Side by side", side_by_side),
    ]
    make_contact_sheet(contact_items, PROJECT_ROOT / paths["contact_sheet_path"])
    return paths, roi_resized, thermal_for_overlay


def slic_like_fallback(rgb: np.ndarray, n_segments: int, compactness: float, iterations: int = 6) -> np.ndarray:
    height, width, _ = rgb.shape
    step = max(8, int(round(math.sqrt(height * width / n_segments))))
    ys = np.arange(step // 2, height, step)
    xs = np.arange(step // 2, width, step)
    centers = []
    for y in ys:
        for x in xs:
            centers.append([rgb[y, x, 0], rgb[y, x, 1], rgb[y, x, 2], float(y), float(x)])
    centers_array = np.asarray(centers, dtype=np.float64)
    labels = np.full((height, width), -1, dtype=np.int32)
    distances = np.full((height, width), np.inf, dtype=np.float64)

    for _ in range(iterations):
        distances.fill(np.inf)
        for index, center in enumerate(centers_array):
            cy = int(round(center[3]))
            cx = int(round(center[4]))
            y0 = max(0, cy - 2 * step)
            y1 = min(height, cy + 2 * step + 1)
            x0 = max(0, cx - 2 * step)
            x1 = min(width, cx + 2 * step + 1)
            patch = rgb[y0:y1, x0:x1]
            yy, xx = np.mgrid[y0:y1, x0:x1]
            color_distance = np.sum((patch - center[:3]) ** 2, axis=2)
            spatial_distance = ((yy - center[3]) ** 2 + (xx - center[4]) ** 2) * (compactness / step) ** 2
            distance = color_distance + spatial_distance
            distance_patch = distances[y0:y1, x0:x1]
            label_patch = labels[y0:y1, x0:x1]
            mask = distance < distance_patch
            distance_patch[mask] = distance[mask]
            label_patch[mask] = index

        flat_labels = labels.ravel()
        valid = flat_labels >= 0
        label_count = len(centers_array)
        counts = np.bincount(flat_labels[valid], minlength=label_count)
        for channel in range(3):
            sums = np.bincount(flat_labels[valid], weights=rgb[:, :, channel].ravel()[valid], minlength=label_count)
            centers_array[:, channel] = np.where(counts > 0, sums / np.maximum(counts, 1), centers_array[:, channel])
        yy_full, xx_full = np.mgrid[0:height, 0:width]
        y_sums = np.bincount(flat_labels[valid], weights=yy_full.ravel()[valid], minlength=label_count)
        x_sums = np.bincount(flat_labels[valid], weights=xx_full.ravel()[valid], minlength=label_count)
        centers_array[:, 3] = np.where(counts > 0, y_sums / np.maximum(counts, 1), centers_array[:, 3])
        centers_array[:, 4] = np.where(counts > 0, x_sums / np.maximum(counts, 1), centers_array[:, 4])

    unique = np.unique(labels)
    remap = {old: new for new, old in enumerate(unique, start=1)}
    return np.vectorize(remap.get)(labels).astype(np.int32)


def run_slic(roi_resized: Image.Image) -> tuple[np.ndarray, str]:
    rgb = np.asarray(roi_resized.convert("RGB"), dtype=np.float64) / 255.0
    if importlib.util.find_spec("skimage") is not None:
        from skimage.segmentation import slic

        labels = slic(
            rgb,
            n_segments=SLIC_SEGMENTS,
            compactness=SLIC_COMPACTNESS,
            sigma=1,
            start_label=1,
            channel_axis=-1,
        )
        return labels.astype(np.int32), "skimage_slic"
    labels = slic_like_fallback(rgb, SLIC_SEGMENTS, SLIC_COMPACTNESS)
    return labels, "slic_like_rgbxy_fallback"


def boundary_mask(labels: np.ndarray) -> np.ndarray:
    boundaries = np.zeros(labels.shape, dtype=bool)
    boundaries[:, 1:] |= labels[:, 1:] != labels[:, :-1]
    boundaries[1:, :] |= labels[1:, :] != labels[:-1, :]
    return boundaries


def colorize_labels(labels: np.ndarray) -> Image.Image:
    unique = np.unique(labels)
    colors = np.zeros((int(unique.max()) + 1, 3), dtype=np.uint8)
    for label in unique:
        colors[int(label)] = (
            (37 * int(label)) % 255,
            (89 * int(label)) % 255,
            (149 * int(label)) % 255,
        )
    return Image.fromarray(colors[labels], mode="RGB")


def average_color_overlay(roi_resized: Image.Image, labels: np.ndarray) -> Image.Image:
    rgb = np.asarray(roi_resized.convert("RGB"), dtype=np.float64)
    flat_labels = labels.ravel()
    max_label = int(labels.max())
    counts = np.bincount(flat_labels, minlength=max_label + 1)
    mean = np.zeros((max_label + 1, 3), dtype=np.float64)
    for channel in range(3):
        sums = np.bincount(flat_labels, weights=rgb[:, :, channel].ravel(), minlength=max_label + 1)
        mean[:, channel] = np.where(counts > 0, sums / np.maximum(counts, 1), 0)
    segment_rgb = mean[labels]
    blended = (0.52 * rgb + 0.48 * segment_rgb).clip(0, 255).astype(np.uint8)
    return Image.fromarray(blended, mode="RGB")


def save_superpixel_outputs(
    image_id: str,
    pair_id: str,
    roi_resized: Image.Image,
) -> tuple[dict[str, str], list[dict[str, Any]], list[dict[str, Any]], str, int]:
    labels, method = run_slic(roi_resized)
    boundaries = boundary_mask(labels)
    label_map = colorize_labels(labels)
    overlay = average_color_overlay(roi_resized, labels)
    boundary_overlay = roi_resized.convert("RGB")
    boundary_array = np.asarray(boundary_overlay).copy()
    boundary_array[boundaries] = [255, 30, 30]
    boundary_overlay = Image.fromarray(boundary_array, mode="RGB")

    base = safe_name(image_id)
    paths = {
        "superpixel_overlay_path": relative_posix(SUPERPIXEL_DIR / f"{base}_superpixel_overlay.png"),
        "segment_id_map_path": relative_posix(SUPERPIXEL_DIR / f"{base}_segment_id_map.png"),
        "segment_boundary_overlay_path": relative_posix(SUPERPIXEL_DIR / f"{base}_segment_boundary_overlay.png"),
        "segment_summary_path": relative_posix(SUPERPIXEL_DIR / f"{base}_segment_summary.xlsx"),
        "annotation_template_path": relative_posix(ANNOTATION_DIR / f"{base}_segment_annotation_template.xlsx"),
    }
    overlay.save(PROJECT_ROOT / paths["superpixel_overlay_path"])
    label_map.save(PROJECT_ROOT / paths["segment_id_map_path"])
    boundary_overlay.save(PROJECT_ROOT / paths["segment_boundary_overlay_path"])

    rgb = np.asarray(roi_resized.convert("RGB"), dtype=np.float64)
    rows: list[dict[str, Any]] = []
    annotation_rows: list[dict[str, Any]] = []
    total_pixels = labels.size
    for segment_id in sorted(int(value) for value in np.unique(labels)):
        mask = labels == segment_id
        ys, xs = np.where(mask)
        pixels = int(mask.sum())
        mean_rgb = rgb[mask].mean(axis=0)
        row = {
            "pair_id": pair_id,
            "image_id": image_id,
            "segment_id": segment_id,
            "segmentation_method": method,
            "pixel_count": pixels,
            "area_fraction": pixels / total_pixels,
            "mean_r": round(float(mean_rgb[0]), 3),
            "mean_g": round(float(mean_rgb[1]), 3),
            "mean_b": round(float(mean_rgb[2]), 3),
            "bbox_x_min": int(xs.min()),
            "bbox_y_min": int(ys.min()),
            "bbox_x_max": int(xs.max()),
            "bbox_y_max": int(ys.max()),
        }
        rows.append(row)
        annotation_rows.append(
            {
                "pair_id": pair_id,
                "segment_id": segment_id,
                "suggested_class": "",
                "manual_class": "",
                "confidence": "",
                "review_status": "needs_manual_review",
                "notes": "",
            }
        )

    write_rows_xlsx(
        PROJECT_ROOT / paths["segment_summary_path"],
        rows,
        [
            "pair_id",
            "image_id",
            "segment_id",
            "segmentation_method",
            "pixel_count",
            "area_fraction",
            "mean_r",
            "mean_g",
            "mean_b",
            "bbox_x_min",
            "bbox_y_min",
            "bbox_x_max",
            "bbox_y_max",
        ],
    )
    write_rows_xlsx(
        PROJECT_ROOT / paths["annotation_template_path"],
        annotation_rows,
        ["pair_id", "segment_id", "suggested_class", "manual_class", "confidence", "review_status", "notes"],
    )
    return paths, rows, annotation_rows, method, len(rows)


def pair_output_row(
    rank: int,
    selection_source: str,
    candidate: pd.Series,
    visible_meta: pd.Series,
    thermal_meta: pd.Series,
    visible_size: tuple[int, int],
    thermal_size: tuple[int, int],
    roi: dict[str, Any],
    visible_camera: dict[str, Any],
    review_paths: dict[str, str],
    superpixel_paths: dict[str, str],
    segmentation_method: str,
    segment_count: int,
) -> dict[str, Any]:
    image_id = clean_value(candidate.get("image_id")) or Path(clean_value(candidate.get("v_path"))).stem.removesuffix("_V")
    notes = (
        f"{visible_camera.get('reason', '')}; ROI is a first-pass center estimate for manual review, "
        "not precise V/T registration."
    )
    return {
        "selection_rank": rank,
        "selection_source": selection_source,
        "selection_criteria": (
            "HKUST high-priority local V/T pair; Garden Hill excluded; existing pilot grid output preferred."
        ),
        "pair_id": clean_value(candidate.get("pair_id")),
        "image_id": image_id,
        "v_path": clean_value(candidate.get("v_path")) or clean_value(visible_meta.get("image_path")),
        "t_path": clean_value(candidate.get("t_path")) or clean_value(thermal_meta.get("image_path")),
        "v_image_width": visible_size[0],
        "v_image_height": visible_size[1],
        "t_image_width": thermal_size[0],
        "t_image_height": thermal_size[1],
        "v_camera_model": clean_value(visible_meta.get("camera_model")),
        "t_camera_model": clean_value(thermal_meta.get("camera_model")),
        "v_focal_length": clean_value(visible_meta.get("focal_length")),
        "t_focal_length": clean_value(thermal_meta.get("focal_length")),
        "v_focal_length_35mm": clean_value(visible_meta.get("focal_length_35mm")),
        "t_focal_length_35mm": clean_value(thermal_meta.get("focal_length_35mm")),
        "v_relative_altitude": clean_value(visible_meta.get("relative_altitude")),
        "t_relative_altitude": clean_value(thermal_meta.get("relative_altitude")),
        "gps_latitude": clean_value(thermal_meta.get("gps_latitude")) or clean_value(visible_meta.get("gps_latitude")),
        "gps_longitude": clean_value(thermal_meta.get("gps_longitude")) or clean_value(visible_meta.get("gps_longitude")),
        "v_gimbal_yaw_degree": clean_value(visible_meta.get("gimbal_yaw_degree")),
        "v_gimbal_pitch_degree": clean_value(visible_meta.get("gimbal_pitch_degree")),
        "v_gimbal_roll_degree": clean_value(visible_meta.get("gimbal_roll_degree")),
        "t_gimbal_yaw_degree": clean_value(thermal_meta.get("gimbal_yaw_degree")),
        "t_gimbal_pitch_degree": clean_value(thermal_meta.get("gimbal_pitch_degree")),
        "t_gimbal_roll_degree": clean_value(thermal_meta.get("gimbal_roll_degree")),
        "inferred_visible_camera_profile": visible_camera.get("camera_key", ""),
        "inferred_visible_camera_confidence": visible_camera.get("confidence", ""),
        "camera_inference_notes": visible_camera.get("reason", ""),
        "roi_method": roi["roi_method"],
        "roi_confidence": roi["roi_confidence"],
        "roi_x_min_px": roi["roi_x_min_px"],
        "roi_y_min_px": roi["roi_y_min_px"],
        "roi_x_max_px": roi["roi_x_max_px"],
        "roi_y_max_px": roi["roi_y_max_px"],
        "roi_width_px": roi["roi_width_px"],
        "roi_height_px": roi["roi_height_px"],
        "roi_width_fraction_of_visible": roi["roi_width_fraction_of_visible"],
        "roi_height_fraction_of_visible": roi["roi_height_fraction_of_visible"],
        "roi_notes": roi["roi_notes"],
        "segmentation_method": segmentation_method,
        "segment_count": segment_count,
        "notes": notes,
        **review_paths,
        **superpixel_paths,
    }


def write_summary_report(
    pilot_rows: list[dict[str, Any]],
    profile_rows: list[dict[str, Any]],
    selection_source: str,
    used_existing_pilot_file: bool,
) -> None:
    lines: list[str] = []
    lines.append("# Part B Round 1 Summary")
    lines.append("")
    lines.append("This Round 1 package prepares semi-automatic visible-image surface-cover review aids for five selected HKUST V/T pairs. It does not extract thermal temperature values and does not train a classification model.")
    lines.append("")
    lines.append("## Files Created")
    lines.append("")
    lines.append("- data/metadata/visible_camera_profiles.xlsx")
    lines.append("- data/metadata/part_b_pilot_pairs.xlsx")
    lines.append("- data/annotations/surface_cover_classes.xlsx")
    lines.append("- data/annotations/part_b_round1_segment_annotations.xlsx")
    lines.append("- data/annotations/part_b_round1/*_segment_annotation_template.xlsx")
    lines.append("- outputs/part_b/review_packages/<image_id>/")
    lines.append("- outputs/part_b/overlays/")
    lines.append("- outputs/part_b/superpixels/")
    lines.append("- outputs/part_b/summaries/part_b_round1_roi_estimates.xlsx")
    lines.append("- outputs/part_b/summaries/part_b_round1_segments.xlsx")
    lines.append("")
    lines.append("## Pilot Selection")
    lines.append("")
    if used_existing_pilot_file:
        lines.append(f"Selection source: {selection_source}. Existing Part B pilot rows were reused and refreshed.")
    else:
        lines.append(f"Selection source: {selection_source}. The selected pairs are the first five HKUST high-priority candidate rows with local V/T files, Garden Hill excluded, and existing pilot grid output preferred.")
    lines.append("")
    for row in pilot_rows:
        lines.append(f"- {row['selection_rank']}. {row['image_id']} ({row['pair_id']})")
    lines.append("")
    lines.append("## Visible Camera Profiles")
    lines.append("")
    for profile in profile_rows:
        lines.append(
            f"- {profile['profile_key']}: {profile['observed_rows']} visible metadata rows observed; "
            f"rule 35mm focal length={profile['rule_focal_length_35mm']}."
        )
    lines.append("")
    lines.append("## ROI Estimation")
    lines.append("")
    for row in pilot_rows:
        lines.append(
            f"- {row['image_id']}: {row['roi_method']} ({row['roi_confidence']} confidence), "
            f"crop {row['roi_x_min_px']},{row['roi_y_min_px']} to {row['roi_x_max_px']},{row['roi_y_max_px']}."
        )
    lines.append("")
    lines.append("## Segmentation")
    lines.append("")
    for row in pilot_rows:
        lines.append(
            f"- {row['image_id']}: {row['segmentation_method']} produced {row['segment_count']} review segments."
        )
    lines.append("")
    lines.append("## Manual Review Next")
    lines.append("")
    lines.append("- Inspect each contact sheet under outputs/part_b/review_packages/<image_id>/07_contact_sheet.png.")
    lines.append("- Check whether the red visible ROI rectangle plausibly matches the thermal image coverage.")
    lines.append("- Inspect outputs/part_b/superpixels/*_segment_boundary_overlay.png for over- or under-segmentation.")
    lines.append("- Fill manual_class, confidence, review_status, and notes in the annotation XLSX templates.")
    lines.append("")
    lines.append("## Known Limitations")
    lines.append("")
    lines.append("- ROI alignment is a metadata/FOV center-crop estimate, not feature registration or precise georeferencing.")
    lines.append("- The workflow assumes the thermal ROI is centered in the visible frame; camera offsets and lens distortion are not modeled.")
    lines.append("- SLIC segments are candidate annotation units only; they are not trusted surface-cover labels.")
    lines.append("- Shadow is included as an allowed review class for now, but later analysis may separate illumination from physical surface cover.")
    lines.append("- Generated PNG review images are local review artifacts and are ignored by git under the current repository rules.")
    SUMMARY_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refresh-pilot-selection",
        action="store_true",
        help="Ignore an existing part_b_pilot_pairs.xlsx and reselect from pilot_candidate_pairs.xlsx.",
    )
    args = parser.parse_args()

    ensure_directories()
    check_inputs()
    candidates, metadata = load_metadata()

    existing_pilot_file = PART_B_PILOT_PAIRS_XLSX.exists() and not args.refresh_pilot_selection
    if args.refresh_pilot_selection and PART_B_PILOT_PAIRS_XLSX.exists():
        PART_B_PILOT_PAIRS_XLSX.unlink()
    selected, selection_source = select_pilot_pairs(candidates)

    profile_rows = build_visible_camera_profiles(metadata)
    write_rows_xlsx(
        VISIBLE_CAMERA_PROFILES_XLSX,
        profile_rows,
        [
            "profile_key",
            "image_type",
            "expected_camera",
            "rule_actual_focal_length_mm",
            "rule_focal_length_35mm",
            "rule_f_number",
            "sensor",
            "observed_rows",
            "observed_image_widths",
            "observed_image_heights",
            "observed_focal_lengths_mm",
            "observed_focal_lengths_35mm",
            "confidence_rule",
            "notes",
        ],
    )
    write_surface_classes()

    pilot_rows: list[dict[str, Any]] = []
    roi_rows: list[dict[str, Any]] = []
    combined_segment_rows: list[dict[str, Any]] = []
    combined_annotation_rows: list[dict[str, Any]] = []

    for rank, (_, candidate) in enumerate(selected.iterrows(), start=1):
        pair_id = clean_value(candidate.get("pair_id"))
        image_id = clean_value(candidate.get("image_id")) or safe_name(pair_id.split("::")[-1])
        visible_meta = metadata_row(metadata, pair_id, "visible")
        thermal_meta = metadata_row(metadata, pair_id, "thermal")
        visible_path = resolve_project_path(clean_value(candidate.get("v_path")) or clean_value(visible_meta.get("image_path")))
        thermal_path = resolve_project_path(clean_value(candidate.get("t_path")) or clean_value(thermal_meta.get("image_path")))

        visible_image = load_preview_image(visible_path)
        thermal_image = load_preview_image(thermal_path)
        roi = estimate_visible_roi(visible_meta, thermal_meta, visible_image.size, thermal_image.size)
        visible_camera = classify_matrice_4t_camera(visible_meta)
        review_paths, roi_resized, _thermal_preview = generate_review_images(image_id, visible_image, thermal_image, roi)
        superpixel_paths, segment_rows, annotation_rows, segmentation_method, segment_count = save_superpixel_outputs(
            image_id,
            pair_id,
            roi_resized,
        )
        pilot_row = pair_output_row(
            rank,
            selection_source,
            candidate,
            visible_meta,
            thermal_meta,
            visible_image.size,
            thermal_image.size,
            roi,
            visible_camera,
            review_paths,
            superpixel_paths,
            segmentation_method,
            segment_count,
        )
        pilot_rows.append(pilot_row)
        roi_rows.append({"pair_id": pair_id, "image_id": image_id, **roi})
        combined_segment_rows.extend(segment_rows)
        combined_annotation_rows.extend(annotation_rows)

    pilot_columns = [
        "selection_rank",
        "selection_source",
        "selection_criteria",
        "pair_id",
        "image_id",
        "v_path",
        "t_path",
        "v_image_width",
        "v_image_height",
        "t_image_width",
        "t_image_height",
        "v_camera_model",
        "t_camera_model",
        "v_focal_length",
        "t_focal_length",
        "v_focal_length_35mm",
        "t_focal_length_35mm",
        "v_relative_altitude",
        "t_relative_altitude",
        "gps_latitude",
        "gps_longitude",
        "v_gimbal_yaw_degree",
        "v_gimbal_pitch_degree",
        "v_gimbal_roll_degree",
        "t_gimbal_yaw_degree",
        "t_gimbal_pitch_degree",
        "t_gimbal_roll_degree",
        "inferred_visible_camera_profile",
        "inferred_visible_camera_confidence",
        "camera_inference_notes",
        "roi_method",
        "roi_confidence",
        "roi_x_min_px",
        "roi_y_min_px",
        "roi_x_max_px",
        "roi_y_max_px",
        "roi_width_px",
        "roi_height_px",
        "roi_width_fraction_of_visible",
        "roi_height_fraction_of_visible",
        "roi_notes",
        "segmentation_method",
        "segment_count",
        "review_package_dir",
        "visible_preview_path",
        "thermal_preview_path",
        "visible_roi_overlay_path",
        "visible_roi_resized_path",
        "thermal_visible_overlay_path",
        "side_by_side_path",
        "contact_sheet_path",
        "superpixel_overlay_path",
        "segment_id_map_path",
        "segment_boundary_overlay_path",
        "segment_summary_path",
        "annotation_template_path",
        "notes",
    ]
    write_rows_xlsx(PART_B_PILOT_PAIRS_XLSX, pilot_rows, pilot_columns)
    write_rows_xlsx(ROI_SUMMARY_XLSX, roi_rows)
    write_rows_xlsx(
        SEGMENT_SUMMARY_XLSX,
        combined_segment_rows,
        [
            "pair_id",
            "image_id",
            "segment_id",
            "segmentation_method",
            "pixel_count",
            "area_fraction",
            "mean_r",
            "mean_g",
            "mean_b",
            "bbox_x_min",
            "bbox_y_min",
            "bbox_x_max",
            "bbox_y_max",
        ],
    )
    write_rows_xlsx(
        COMBINED_ANNOTATION_XLSX,
        combined_annotation_rows,
        ["pair_id", "segment_id", "suggested_class", "manual_class", "confidence", "review_status", "notes"],
    )
    write_summary_report(pilot_rows, profile_rows, selection_source, existing_pilot_file)

    print(f"Wrote {relative_posix(PART_B_PILOT_PAIRS_XLSX)}")
    print(f"Wrote {len(pilot_rows)} review packages under {relative_posix(REVIEW_DIR)}")
    print(f"Wrote combined annotation template {relative_posix(COMBINED_ANNOTATION_XLSX)}")
    print(f"Wrote summary {relative_posix(SUMMARY_MD)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
