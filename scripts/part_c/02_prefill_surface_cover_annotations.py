#!/usr/bin/env python3
"""Prefill Part C surface-cover annotation CSVs with reviewable draft labels.

The prefill is a Codex draft based on visible ROI segment color/texture
features. It is not ground truth, does not use LUHK as surface cover, and does
not generate final masks.
"""

from __future__ import annotations

import csv
import math
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("MPLCONFIGDIR", str(PROJECT_ROOT / ".matplotlib-cache"))

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageOps
from skimage import color, filters, segmentation


ANNOTATION_DIR = PROJECT_ROOT / "data" / "annotations" / "part_c"
MAIN_ANNOTATION_CSV = ANNOTATION_DIR / "part_c_surface_cover_annotations.csv"
SUMMARY_CSV = PROJECT_ROOT / "outputs" / "part_c" / "summaries" / "part_c_round1_summary.csv"
PREFILL_SEGMENTS_CSV = PROJECT_ROOT / "outputs" / "part_c" / "summaries" / "part_c_codex_prefill_segments.csv"
PREFILL_SUMMARY_CSV = PROJECT_ROOT / "outputs" / "part_c" / "summaries" / "part_c_codex_prefill_summary.csv"
PREFILL_SUMMARY_MD = PROJECT_ROOT / "outputs" / "part_c" / "summaries" / "part_c_codex_prefill_summary.md"
BLANK_BACKUP_CSV = ANNOTATION_DIR / "part_c_surface_cover_annotations_blank_before_codex_prefill.csv"

PREFILL_VERSION = "codex_draft_v1"
PREFILL_STATUS = "codex_prefilled_needs_review"

CLASS_COLORS = {
    "roof": "#f2f2f2",
    "concrete_pavement": "#c9c3b6",
    "asphalt_road": "#555555",
    "vegetation_tree": "#1f7a3a",
    "grass_low_vegetation": "#8bc34a",
    "bare_soil": "#9b6a3c",
    "water": "#1f78b4",
    "shadow": "#2f2147",
    "vehicle_temporary_object": "#ffcc00",
    "unclear_ignore": "#d94fd6",
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


def is_blank(value: Any) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except TypeError:
        pass
    return str(value).strip() == ""


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
        return image.convert("RGB")


def load_label_map(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        image.load()
        return np.asarray(image, dtype=np.int32)


def rgb_hex_to_uint8(hex_color: str) -> tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def segment_texture(gray: np.ndarray, mask: np.ndarray) -> float:
    if mask.sum() == 0:
        return 0.0
    edges = filters.sobel(gray)
    return float(edges[mask].mean())


def segment_compactness(mask: np.ndarray) -> float:
    area = float(mask.sum())
    if area <= 0:
        return 0.0
    ys, xs = np.where(mask)
    bbox_area = float((xs.max() - xs.min() + 1) * (ys.max() - ys.min() + 1))
    return area / bbox_area if bbox_area > 0 else 0.0


def classify_features(features: dict[str, float]) -> tuple[str, str, str]:
    r = features["mean_r"]
    g = features["mean_g"]
    b = features["mean_b"]
    h = features["mean_h"]
    s = features["mean_s"]
    v = features["mean_v"]
    std_v = features["std_v"]
    texture = features["texture"]
    area_fraction = features["pixel_fraction"]
    compactness = features["compactness"]
    gray_range = max(r, g, b) - min(r, g, b)
    green_excess = g - max(r, b)
    blue_excess = b - max(r, g)
    red_excess = r - max(g, b)
    brightness255 = v * 255.0

    # Tiny bright or saturated specks are often cars or temporary objects in
    # the parking/road parts of the pilot ROIs. Keep this deliberately narrow.
    if area_fraction < 0.0018 and brightness255 > 150 and (s > 0.22 or gray_range < 24):
        return "vehicle_temporary_object", "low", "tiny bright/saturated segment; likely vehicle/object but must be checked"

    # Water is intentionally very restrictive because shaded canopy can look
    # blue in visible imagery. Require a brighter, strongly blue, smooth region.
    if (
        blue_excess > 12
        and b > 125
        and (b - r) > 34
        and v > 0.48
        and s > 0.20
        and texture < 0.045
        and area_fraction > 0.003
        and compactness > 0.38
    ):
        return "water", "low", "blue-dominant low-texture segment; verify against visible ROI"

    # Vegetation: most pilot pixels are canopy. Separate tree canopy from grass
    # using brightness and texture/open-area smoothness.
    if blue_excess > 8 and g > r and brightness255 < 145:
        return "vegetation_tree", "low", "cool-toned shaded canopy-like segment"
    if green_excess > 4 or (0.18 <= h <= 0.46 and s > 0.10 and g >= r and g >= b - 4):
        if brightness255 > 120 and texture < 0.055 and compactness > 0.45:
            return "grass_low_vegetation", "medium", "bright smoother green segment"
        return "vegetation_tree", "medium", "green or textured canopy-like segment"

    # Deep non-green low-brightness regions are shadows.
    if brightness255 < 64 and s < 0.24:
        return "shadow", "medium", "dark low-saturation segment"
    if brightness255 < 52:
        return "shadow", "low", "very dark segment"

    # Bare soil and exposed earth tend toward brown/orange.
    if red_excess > 5 and r > 80 and 0.04 <= h <= 0.16 and 0.12 <= s <= 0.55:
        return "bare_soil", "low", "brown/orange exposed-ground color heuristic"

    # Built/paved surfaces. Roofs are usually brighter and smaller/more compact;
    # concrete and asphalt catch the larger hardscape pieces.
    if s < 0.18 and brightness255 > 178:
        if area_fraction < 0.009 and compactness > 0.36:
            return "roof", "medium", "bright low-saturation compact segment"
        return "concrete_pavement", "medium", "bright low-saturation hardscape segment"
    if s < 0.22 and brightness255 > 128:
        if area_fraction < 0.006 and std_v > 0.045:
            return "roof", "low", "medium-bright compact built-surface segment"
        return "concrete_pavement", "medium", "medium-bright hardscape segment"
    if s < 0.20 and 62 <= brightness255 <= 128:
        return "asphalt_road", "low", "dark gray low-saturation hardscape heuristic"

    # Yellowed grass/open ground can fall outside the green test.
    if 0.12 <= h <= 0.24 and s > 0.12 and brightness255 > 100:
        return "grass_low_vegetation", "low", "yellow-green open vegetation heuristic"

    return "unclear_ignore", "low", "ambiguous mixed segment; human review needed"


def compute_segment_features(image: Image.Image, labels: np.ndarray) -> list[dict[str, Any]]:
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0
    hsv = color.rgb2hsv(rgb)
    gray = color.rgb2gray(rgb)
    rows: list[dict[str, Any]] = []
    for segment_id in sorted(int(value) for value in np.unique(labels) if int(value) > 0):
        mask = labels == segment_id
        if mask.sum() == 0:
            continue
        ys, xs = np.where(mask)
        rgb_values = rgb[mask]
        hsv_values = hsv[mask]
        mean_rgb = rgb_values.mean(axis=0)
        mean_hsv = hsv_values.mean(axis=0)
        std_hsv = hsv_values.std(axis=0)
        area_px = int(mask.sum())
        features = {
            "segment_id": segment_id,
            "pixel_count": area_px,
            "pixel_fraction": area_px / float(labels.size),
            "bbox_x_min": int(xs.min()),
            "bbox_y_min": int(ys.min()),
            "bbox_x_max": int(xs.max()),
            "bbox_y_max": int(ys.max()),
            "centroid_x": float(xs.mean()),
            "centroid_y": float(ys.mean()),
            "mean_r": float(mean_rgb[0] * 255.0),
            "mean_g": float(mean_rgb[1] * 255.0),
            "mean_b": float(mean_rgb[2] * 255.0),
            "mean_h": float(mean_hsv[0]),
            "mean_s": float(mean_hsv[1]),
            "mean_v": float(mean_hsv[2]),
            "std_h": float(std_hsv[0]),
            "std_s": float(std_hsv[1]),
            "std_v": float(std_hsv[2]),
            "texture": segment_texture(gray, mask),
            "compactness": segment_compactness(mask),
        }
        draft_class, confidence, reason = classify_features(features)
        features.update(
            {
                "codex_prefill_class": draft_class,
                "codex_prefill_confidence": confidence,
                "codex_prefill_reason": reason,
            }
        )
        rows.append(features)
    return rows


def make_class_overlay(
    image: Image.Image,
    labels: np.ndarray,
    feature_rows: list[dict[str, Any]],
    output_path: Path,
) -> str:
    base = np.asarray(image.convert("RGB"), dtype=np.float32)
    class_rgb = np.zeros_like(base)
    class_by_segment = {int(row["segment_id"]): row["codex_prefill_class"] for row in feature_rows}
    for segment_id, class_name in class_by_segment.items():
        class_rgb[labels == segment_id] = rgb_hex_to_uint8(CLASS_COLORS[class_name])
    blended = np.clip(0.48 * base + 0.52 * class_rgb, 0, 255).astype(np.uint8)
    boundary = segmentation.mark_boundaries(blended / 255.0, labels, color=(1.0, 1.0, 0.0), mode="thick")
    overlay = Image.fromarray((boundary * 255.0 + 0.5).astype(np.uint8), mode="RGB")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    overlay.save(output_path)
    return relative_posix(output_path)


def make_legend(output_path: Path) -> str:
    width, height = 620, 360
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.text((18, 18), f"Surface-cover prefill legend ({PREFILL_VERSION})", fill=(0, 0, 0))
    y = 62
    for class_name, hex_color in CLASS_COLORS.items():
        draw.rectangle((24, y, 54, y + 22), fill=rgb_hex_to_uint8(hex_color), outline=(0, 0, 0))
        draw.text((66, y + 3), class_name, fill=(0, 0, 0))
        y += 29
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)
    return relative_posix(output_path)


def write_prefill_summary_md(pair_rows: list[dict[str, Any]], class_counts: pd.DataFrame) -> None:
    lines = [
        "# Part C Codex Prefill Summary",
        "",
        f"Prefill version: `{PREFILL_VERSION}`",
        "",
        "These labels are a draft for human review. They were inferred from visible ROI segment color, brightness, texture, and shape features. LUHK was not used as surface-cover evidence.",
        "",
        "## Overall Class Counts",
        "",
    ]
    for _, row in class_counts.iterrows():
        lines.append(f"- `{row['manual_class']}`: {int(row['count'])}")
    lines.extend(["", "## Per-Pair Review Files", ""])
    for row in pair_rows:
        lines.extend(
            [
                f"### {row['image_id']}",
                "",
                f"- Annotation CSV: `{row['annotation_csv_path']}`",
                f"- Prefill class overlay: `{row['prefill_class_overlay_path']}`",
                f"- Segment ID quadrants: `{row['segment_id_labels_quadrants_path']}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Review Notes",
            "",
            "- Check `roof` versus `concrete_pavement` carefully around buildings.",
            "- Check dark roofs and solar panels; color rules may label them as `vegetation_tree`.",
            "- Check dark canopy versus `shadow` carefully.",
            "- Check `water`; this draft uses a restrictive blue/low-texture rule, but shaded surfaces can still confuse it.",
            "- Change `manual_class` directly where needed and set `review_status` to `reviewed` after human review.",
            "",
        ]
    )
    PREFILL_SUMMARY_MD.parent.mkdir(parents=True, exist_ok=True)
    PREFILL_SUMMARY_MD.write_text("\n".join(lines), encoding="utf-8")


def backup_blank_annotations() -> None:
    if BLANK_BACKUP_CSV.exists() or not MAIN_ANNOTATION_CSV.exists():
        return
    df = pd.read_csv(MAIN_ANNOTATION_CSV)
    if "manual_class" in df.columns and df["manual_class"].fillna("").astype(str).str.strip().eq("").all():
        shutil.copy2(MAIN_ANNOTATION_CSV, BLANK_BACKUP_CSV)


def base_annotation_note(value: Any) -> str:
    if is_blank(value):
        return ""
    text = str(value)
    marker = " | original_note: "
    while text.startswith(f"{PREFILL_VERSION}:") and marker in text:
        text = text.split(marker, 1)[1]
    return text


def update_annotation_file(path: Path, prefill_df: pd.DataFrame) -> None:
    df = pd.read_csv(path)
    for column in ["manual_class", "confidence", "review_status", "notes"]:
        if column in df.columns:
            df[column] = df[column].astype("object")
    key_cols = ["pair_id", "segment_id"]
    merged = df.merge(
        prefill_df[
            key_cols
            + [
                "codex_prefill_class",
                "codex_prefill_confidence",
                "codex_prefill_reason",
            ]
        ],
        on=key_cols,
        how="left",
    )
    for index, row in merged.iterrows():
        if is_blank(row.get("codex_prefill_class")):
            continue
        if not is_blank(row.get("manual_class")) and row.get("review_status") != PREFILL_STATUS:
            continue
        merged.at[index, "manual_class"] = row["codex_prefill_class"]
        merged.at[index, "confidence"] = row["codex_prefill_confidence"]
        merged.at[index, "review_status"] = PREFILL_STATUS
        old_note = base_annotation_note(row.get("notes"))
        merged.at[index, "notes"] = (
            f"{PREFILL_VERSION}: {row['codex_prefill_reason']}"
            + (f" | original_note: {old_note}" if old_note else "")
        )
    output_cols = [column for column in df.columns]
    merged[output_cols].to_csv(path, index=False)


def main() -> int:
    required = [SUMMARY_CSV, MAIN_ANNOTATION_CSV]
    missing = [relative_posix(path) for path in required if not path.is_file()]
    if missing:
        print("Missing required Part C files:", file=sys.stderr)
        for path in missing:
            print(f"- {path}", file=sys.stderr)
        return 1

    summary_df = pd.read_csv(SUMMARY_CSV)
    all_feature_rows: list[dict[str, Any]] = []
    pair_summary_rows: list[dict[str, Any]] = []

    for _, pair in summary_df.iterrows():
        image_id = str(pair["image_id"])
        pair_id = str(pair["pair_id"])
        image = load_rgb(resolve_project_path(pair["refined_visible_roi_resized_to_thermal_grid_path"]))
        labels = load_label_map(resolve_project_path(pair["segment_id_map_16bit_path"]))
        feature_rows = compute_segment_features(image, labels)
        for row in feature_rows:
            row["pair_id"] = pair_id
            row["image_id"] = image_id
            row["prefill_version"] = PREFILL_VERSION
        all_feature_rows.extend(feature_rows)

        overlay_path = resolve_project_path(pair["superpixel_overlay_path"]).with_name(
            f"{safe_name(image_id)}_codex_prefill_class_overlay.png"
        )
        legend_path = overlay_path.with_name(f"{safe_name(image_id)}_codex_prefill_class_legend.png")
        overlay_rel = make_class_overlay(image, labels, feature_rows, overlay_path)
        legend_rel = make_legend(legend_path)
        pair_summary_rows.append(
            {
                "pair_id": pair_id,
                "image_id": image_id,
                "annotation_csv_path": pair["pair_annotation_csv_path"],
                "prefill_class_overlay_path": overlay_rel,
                "prefill_class_legend_path": legend_rel,
                "segment_id_labels_quadrants_path": pair["segment_id_labels_quadrants_path"],
            }
        )

    feature_columns = [
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
        "std_h",
        "std_s",
        "std_v",
        "texture",
        "compactness",
        "codex_prefill_class",
        "codex_prefill_confidence",
        "codex_prefill_reason",
        "prefill_version",
    ]
    write_rows_csv(PREFILL_SEGMENTS_CSV, all_feature_rows, feature_columns)

    prefill_df = pd.DataFrame(all_feature_rows)
    backup_blank_annotations()
    update_annotation_file(MAIN_ANNOTATION_CSV, prefill_df)
    for row in pair_summary_rows:
        update_annotation_file(resolve_project_path(row["annotation_csv_path"]), prefill_df)

    annotated = pd.read_csv(MAIN_ANNOTATION_CSV)
    class_counts = (
        annotated["manual_class"]
        .fillna("missing")
        .value_counts()
        .rename_axis("manual_class")
        .reset_index(name="count")
    )
    write_rows_csv(PREFILL_SUMMARY_CSV, class_counts.to_dict("records"), ["manual_class", "count"])
    write_prefill_summary_md(pair_summary_rows, class_counts)

    print(f"Prefilled annotation rows: {len(annotated)}")
    print(f"Manual class nonblank: {annotated['manual_class'].fillna('').astype(str).str.strip().ne('').sum()}")
    print(f"Prefill summary: {relative_posix(PREFILL_SUMMARY_MD)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
