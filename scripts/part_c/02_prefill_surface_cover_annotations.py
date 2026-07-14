#!/usr/bin/env python3
"""Synchronize Part C surface-cover suggestions and render review overlays.

This utility keeps the annotation XLSXs in the manual-review format:

- suggested_class stores the current suggested surface-cover label
- manual_class starts as a copy of suggested_class and is edited by the reviewer
- review_status uses only "Not yet" and "Yes"

It also renders per-pair surface-cover overlays in
outputs/part_c/surface_cover_review/<image_id>/.
"""

from __future__ import annotations

import os
import sys
import argparse
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
os.environ.setdefault("MPLCONFIGDIR", str(PROJECT_ROOT / ".matplotlib-cache"))

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageOps
from skimage import segmentation

from table_io import read_table, write_rows, write_table


ANNOTATION_DIR = PROJECT_ROOT / "data" / "annotations" / "part_c"
MAIN_ANNOTATION_XLSX = ANNOTATION_DIR / "part_c_surface_cover_annotations.xlsx"
SURFACE_CLASSES_XLSX = ANNOTATION_DIR / "surface_cover_classes.xlsx"
ROUND1_SUMMARY_XLSX = PROJECT_ROOT / "outputs" / "part_c" / "summaries" / "part_c_round1_summary.xlsx"
CLASS_COUNTS_XLSX = PROJECT_ROOT / "outputs" / "part_c" / "summaries" / "part_c_surface_cover_class_counts.xlsx"
SHADOW_COUNTS_XLSX = PROJECT_ROOT / "outputs" / "part_c" / "summaries" / "part_c_shadow_status_counts.xlsx"
OVERLAY_PATHS_XLSX = PROJECT_ROOT / "outputs" / "part_c" / "summaries" / "part_c_surface_cover_review_overlays.xlsx"

STATUS_NOT_YET = "Not yet"
STATUS_YES = "Yes"

ANNOTATION_COLUMNS = [
    "pair_id",
    "segment_id",
    "suggested_class",
    "manual_class",
    "shadow_status",
    "confidence",
    "review_status",
    "notes",
]

CLASS_COLORS = {
    "roof": "#f2f2f2",
    "concrete_pavement": "#ff8c00",
    "asphalt_road": "#555555",
    "vegetation_tree": "#1f7a3a",
    "grass_low_vegetation": "#8bc34a",
    "bare_soil": "#9b6a3c",
    "water": "#1f78b4",
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


def is_blank(value: Any) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except TypeError:
        pass
    return str(value).strip() == ""


def write_rows_xlsx(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    write_rows(path, rows, columns)


def normalize_shadow_status(value: Any) -> int:
    if is_blank(value):
        return 0
    text = str(value).strip().casefold()
    if text in {"1", "1.0", "true", "yes", "y", "shadow", "shadowed"}:
        return 1
    if text in {"0", "0.0", "false", "no", "n", "not_shadowed", "not shadowed"}:
        return 0
    try:
        number = int(float(text))
    except ValueError as exc:
        raise ValueError(f"Invalid shadow_status value: {value!r}") from exc
    if number in {0, 1}:
        return number
    raise ValueError(f"Invalid shadow_status value: {value!r}")


def load_allowed_classes() -> list[str]:
    classes_df = read_table(SURFACE_CLASSES_XLSX)
    classes = [str(value).strip() for value in classes_df["class_name"].tolist()]
    missing_colors = [class_name for class_name in classes if class_name not in CLASS_COLORS]
    if missing_colors:
        raise ValueError("Missing display colors for classes: " + ", ".join(missing_colors))
    return classes


def normalize_annotations(allowed_classes: list[str], reset_review_baseline: bool, write_main: bool) -> pd.DataFrame:
    if not MAIN_ANNOTATION_XLSX.is_file():
        raise FileNotFoundError(MAIN_ANNOTATION_XLSX)

    df = read_table(MAIN_ANNOTATION_XLSX)
    required = ["pair_id", "segment_id", "suggested_class", "manual_class", "confidence", "review_status", "notes"]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError("Missing required annotation columns: " + ", ".join(missing))
    if "shadow_status" not in df.columns:
        df["shadow_status"] = 0

    for column in required + ["shadow_status"]:
        df[column] = df[column].astype("object")

    manual_labels: list[str] = []
    suggested_labels: list[str] = []
    shadow_statuses: list[int] = []
    for _, row in df.iterrows():
        suggested = "" if is_blank(row["suggested_class"]) else str(row["suggested_class"]).strip()
        manual = "" if is_blank(row["manual_class"]) else str(row["manual_class"]).strip()
        shadow_status = normalize_shadow_status(row.get("shadow_status", 0))
        if reset_review_baseline:
            latest = manual or suggested
            suggested = latest
            manual = latest
        else:
            if not manual:
                manual = suggested
            if not suggested:
                suggested = manual
        if suggested == "shadow":
            suggested = "unclear_ignore"
            shadow_status = 1
        if manual == "shadow":
            manual = "unclear_ignore"
            shadow_status = 1
        suggested_labels.append(suggested)
        manual_labels.append(manual)
        shadow_statuses.append(shadow_status)

    invalid = sorted(
        {
            label
            for label in suggested_labels + manual_labels
            if label not in allowed_classes
        }
    )
    if invalid:
        raise ValueError("Annotation labels outside the approved class list: " + ", ".join(invalid))

    df["suggested_class"] = suggested_labels
    df["manual_class"] = manual_labels
    df["shadow_status"] = shadow_statuses
    df["review_status"] = df["review_status"].map(lambda value: STATUS_YES if str(value).strip() == STATUS_YES else STATUS_NOT_YET)
    df["notes"] = ""
    if write_main:
        write_table(MAIN_ANNOTATION_XLSX, df, ANNOTATION_COLUMNS)

    for pair_id, pair_df in df.groupby("pair_id", sort=False):
        image_id = str(pair_id).split("::")[-1]
        pair_path = ANNOTATION_DIR / f"{image_id}_surface_cover_annotations.xlsx"
        write_table(pair_path, pair_df, ANNOTATION_COLUMNS)

    return df


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def colorized_overlay(base_image: Image.Image, labels: np.ndarray, label_by_segment: dict[int, str]) -> Image.Image:
    base = np.asarray(base_image.convert("RGB"), dtype=np.float32)
    class_rgb = np.zeros_like(base)
    for segment_id, class_name in label_by_segment.items():
        class_rgb[labels == segment_id] = hex_to_rgb(CLASS_COLORS[class_name])
    blended = np.clip(0.48 * base + 0.52 * class_rgb, 0, 255).astype(np.uint8)
    boundary = segmentation.mark_boundaries(blended / 255.0, labels, color=(1.0, 1.0, 0.0), mode="thick")
    return Image.fromarray((boundary * 255.0 + 0.5).astype(np.uint8), mode="RGB")


def legend_image(class_counts: pd.Series, shadowed_count: int) -> Image.Image:
    image = Image.new("RGB", (640, 512), "white")
    draw = ImageDraw.Draw(image)
    draw.text((18, 18), "Surface-cover class legend", fill=(0, 0, 0))
    y = 62
    for class_name, hex_color in CLASS_COLORS.items():
        count = int(class_counts.get(class_name, 0))
        draw.rectangle((24, y, 56, y + 24), fill=hex_color, outline=(0, 0, 0))
        draw.text((70, y + 4), f"{class_name} ({count})", fill=(0, 0, 0))
        y += 38
    draw.text((24, y + 4), f"shadow_status=1 ({shadowed_count})", fill=(0, 0, 0))
    return image


def review_sheet(overlay: Image.Image, legend: Image.Image, image_id: str) -> Image.Image:
    tile_w, tile_h = 640, 560
    label_h = 30
    sheet = Image.new("RGB", (tile_w * 2, tile_h), "white")
    items = [(f"{image_id} surface-cover overlay", overlay), ("legend", legend)]
    for index, (label, image) in enumerate(items):
        tile = Image.new("RGB", (tile_w, tile_h), "white")
        body = image.copy()
        body.thumbnail((tile_w, tile_h - label_h), Image.Resampling.LANCZOS)
        x = (tile_w - body.width) // 2
        y = label_h + (tile_h - label_h - body.height) // 2
        tile.paste(body, (x, y))
        draw = ImageDraw.Draw(tile)
        draw.text((8, 8), label, fill=(0, 0, 0))
        sheet.paste(tile, (index * tile_w, 0))
    return sheet


def render_pair_overlays(annotations_df: pd.DataFrame) -> list[dict[str, Any]]:
    summary_df = read_table(ROUND1_SUMMARY_XLSX)
    rows: list[dict[str, Any]] = []
    for _, summary_row in summary_df.iterrows():
        pair_id = str(summary_row["pair_id"])
        image_id = str(summary_row["image_id"])
        pair_df = annotations_df.loc[annotations_df["pair_id"].astype(str).eq(pair_id)].copy()
        if pair_df.empty:
            continue

        base_path = resolve_project_path(summary_row["refined_visible_roi_resized_to_thermal_grid_path"])
        label_path = resolve_project_path(summary_row["segment_id_map_16bit_path"])
        base_image = ImageOps.exif_transpose(Image.open(base_path)).convert("RGB")
        labels = np.asarray(Image.open(label_path), dtype=np.int32)
        label_by_segment = {
            int(row["segment_id"]): str(row["manual_class"]).strip()
            for _, row in pair_df.iterrows()
        }
        class_counts = pair_df["manual_class"].value_counts()
        shadowed_count = int(pd.to_numeric(pair_df["shadow_status"], errors="coerce").fillna(0).astype(int).sum())
        overlay = colorized_overlay(base_image, labels, label_by_segment)
        legend = legend_image(class_counts, shadowed_count)
        sheet = review_sheet(overlay, legend, image_id)

        out_dir = PROJECT_ROOT / "outputs" / "part_c" / "surface_cover_review" / image_id
        out_dir.mkdir(parents=True, exist_ok=True)
        overlay_path = out_dir / f"{image_id}_surface_cover_class_overlay.png"
        legend_path = out_dir / f"{image_id}_surface_cover_class_legend.png"
        sheet_path = out_dir / f"{image_id}_surface_cover_class_review_sheet.png"
        overlay.save(overlay_path)
        legend.save(legend_path)
        sheet.save(sheet_path)
        rows.append(
            {
                "pair_id": pair_id,
                "image_id": image_id,
                "surface_cover_class_overlay_path": relative_posix(overlay_path),
                "surface_cover_class_legend_path": relative_posix(legend_path),
                "surface_cover_class_review_sheet_path": relative_posix(sheet_path),
            }
        )
    return rows


def write_class_counts(annotations_df: pd.DataFrame, allowed_classes: list[str]) -> None:
    counts = annotations_df["manual_class"].value_counts()
    rows = [
        {
            "class_name": class_name,
            "segment_count": int(counts.get(class_name, 0)),
        }
        for class_name in allowed_classes
    ]
    write_rows_xlsx(CLASS_COUNTS_XLSX, rows, ["class_name", "segment_count"])


def write_shadow_counts(annotations_df: pd.DataFrame) -> None:
    statuses = pd.to_numeric(annotations_df["shadow_status"], errors="coerce").fillna(0).astype(int)
    counts = statuses.value_counts()
    rows = [
        {"shadow_status": 0, "segment_count": int(counts.get(0, 0))},
        {"shadow_status": 1, "segment_count": int(counts.get(1, 0))},
    ]
    write_rows_xlsx(SHADOW_COUNTS_XLSX, rows, ["shadow_status", "segment_count"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate Part C surface-cover annotations and render per-pair review overlays."
    )
    parser.add_argument(
        "--reset-review-baseline",
        action="store_true",
        help=(
            "Copy the latest existing label into both suggested_class and manual_class, "
            "then reset review_status to Not yet. Use this only when starting a fresh review pass."
        ),
    )
    parser.add_argument(
        "--skip-main-write",
        action="store_true",
        help=(
            "Regenerate per-pair annotation workbooks, summaries, and overlays without "
            "writing the main annotation workbook. Useful when the main workbook is open in Excel."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    required = [MAIN_ANNOTATION_XLSX, SURFACE_CLASSES_XLSX, ROUND1_SUMMARY_XLSX]
    missing = [relative_posix(path) for path in required if not path.is_file()]
    if missing:
        print("Missing required Part C files:", file=sys.stderr)
        for path in missing:
            print(f"- {path}", file=sys.stderr)
        return 1

    allowed_classes = load_allowed_classes()
    annotations_df = normalize_annotations(
        allowed_classes,
        reset_review_baseline=args.reset_review_baseline,
        write_main=not args.skip_main_write,
    )
    write_class_counts(annotations_df, allowed_classes)
    write_shadow_counts(annotations_df)
    overlay_rows = render_pair_overlays(annotations_df)
    write_rows_xlsx(
        OVERLAY_PATHS_XLSX,
        overlay_rows,
        [
            "pair_id",
            "image_id",
            "surface_cover_class_overlay_path",
            "surface_cover_class_legend_path",
            "surface_cover_class_review_sheet_path",
        ],
    )
    print(f"Annotation rows: {len(annotations_df)}")
    print(f"Review status values: {', '.join(sorted(annotations_df['review_status'].unique()))}")
    print(f"Overlay manifest: {relative_posix(OVERLAY_PATHS_XLSX)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
