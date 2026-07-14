#!/usr/bin/env python3
"""Generate Part C final pilot masks and summaries from reviewed annotations.

This script does not redo Part C Round 1 segmentation and does not extract
thermal temperatures. It ingests the reviewed manual labels, validates them,
maps segment IDs to physical surface-cover class IDs on the thermal grid, and
writes separate shadow_flag masks.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageOps

from table_io import read_table, write_rows, write_table


ANNOTATION_DIR = PROJECT_ROOT / "data" / "annotations" / "part_c"
BACKUP_DIR = ANNOTATION_DIR / "backups"
SUMMARY_DIR = PROJECT_ROOT / "outputs" / "part_c" / "summaries"
MASK_DIR = PROJECT_ROOT / "outputs" / "part_c" / "masks"

MAIN_ANNOTATION_XLSX = ANNOTATION_DIR / "part_c_surface_cover_annotations.xlsx"
ROUND1_SUMMARY_XLSX = SUMMARY_DIR / "part_c_round1_summary.xlsx"
LUHK_CONTEXT_SUMMARY_XLSX = SUMMARY_DIR / "part_c_luhk_context_summary.xlsx"
PART_B_PILOT_PAIRS_XLSX = PROJECT_ROOT / "data" / "metadata" / "part_b_pilot_pairs.xlsx"
PART_B_ALIGNMENT_SUMMARY_XLSX = (
    PROJECT_ROOT / "outputs" / "part_b" / "summaries" / "part_b_round1_1_alignment_summary.xlsx"
)

CLASS_MAPPING_XLSX = ANNOTATION_DIR / "surface_cover_class_mapping.xlsx"
SHADOW_MAPPING_XLSX = ANNOTATION_DIR / "shadow_flag_mapping.xlsx"

VALIDATION_XLSX = SUMMARY_DIR / "part_c_manual_annotation_validation.xlsx"
VALIDATION_MD = SUMMARY_DIR / "part_c_manual_annotation_validation.md"
MASK_MANIFEST_XLSX = SUMMARY_DIR / "part_c_final_mask_manifest.xlsx"
SURFACE_SUMMARY_XLSX = SUMMARY_DIR / "part_c_surface_cover_summary.xlsx"
SURFACE_SUMMARY_MD = SUMMARY_DIR / "part_c_surface_cover_summary.md"
SHADOW_SUMMARY_XLSX = SUMMARY_DIR / "part_c_shadow_flag_summary.xlsx"
SHADOW_SUMMARY_MD = SUMMARY_DIR / "part_c_shadow_flag_summary.md"
COMBINED_SUMMARY_XLSX = SUMMARY_DIR / "part_c_luhk_surface_cover_combined_summary.xlsx"
COMBINED_SUMMARY_MD = SUMMARY_DIR / "part_c_luhk_surface_cover_combined_summary.md"
ROUND3_FINAL_MD = SUMMARY_DIR / "part_c_round3_final_mask_generation_summary.md"
MASK_README = MASK_DIR / "README.md"

NO_DATA_CLASS = "no_data_unreviewed"
SHADOW_INPUT_COLUMNS = ["shadow_flag", "shadow_status"]

CLASS_MAPPING_ROWS = [
    {"class_id": 0, "class_name": NO_DATA_CLASS, "description": "Blank, missing, invalid, or unreviewed physical surface-cover label."},
    {"class_id": 1, "class_name": "roof", "description": "Building roof surfaces visible in the refined ROI."},
    {"class_id": 2, "class_name": "concrete_pavement", "description": "Light hardscape, plazas, walkways, and paved open areas."},
    {"class_id": 3, "class_name": "asphalt_road", "description": "Dark road carriageways and similar asphalt surfaces."},
    {"class_id": 4, "class_name": "vegetation_tree", "description": "Tree canopy and taller woody vegetation."},
    {"class_id": 5, "class_name": "grass_low_vegetation", "description": "Grass, planted ground cover, and low vegetation."},
    {"class_id": 6, "class_name": "bare_soil", "description": "Exposed soil or unsealed ground."},
    {"class_id": 7, "class_name": "water", "description": "Water surfaces."},
    {"class_id": 8, "class_name": "vehicle_temporary_object", "description": "Vehicles, movable equipment, or temporary objects."},
    {"class_id": 9, "class_name": "unclear_ignore", "description": "Reviewed ambiguous or out-of-scope segments to exclude from final analysis."},
]

SHADOW_MAPPING_ROWS = [
    {"shadow_flag": 0, "shadow_name": "no_shadow", "description": "No shadow recorded for the segment or pixel."},
    {"shadow_flag": 1, "shadow_name": "shadow_present", "description": "Shadow affects the segment or pixel."},
]

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

SHADOW_COLORS = {
    0: "#f2f2f2",
    1: "#5b2a86",
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


def ensure_dirs() -> None:
    for path in [BACKUP_DIR, SUMMARY_DIR, MASK_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def copy_review_backups() -> list[str]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    copied: list[str] = []
    candidates = [MAIN_ANNOTATION_XLSX, ANNOTATION_DIR / "surface_cover_classes.xlsx"]
    candidates.extend(sorted(ANNOTATION_DIR.glob("DJI_*_surface_cover_annotations.xlsx")))
    for source in candidates:
        if not source.is_file() or source.name.startswith("~$"):
            continue
        target = BACKUP_DIR / f"{source.stem}_manual_backup_{timestamp}{source.suffix}"
        shutil.copy2(source, target)
        copied.append(relative_posix(target))
    return copied


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[index : index + 2], 16) for index in (0, 2, 4))


def mask_to_color(mask: np.ndarray, colors: dict[int, str]) -> Image.Image:
    rgb = np.zeros((mask.shape[0], mask.shape[1], 3), dtype=np.uint8)
    for value, color_hex in colors.items():
        rgb[mask == value] = hex_to_rgb(color_hex)
    return Image.fromarray(rgb, mode="RGB")


def overlay_mask(base_image: Image.Image, mask: np.ndarray, colors: dict[int, str], alpha: float = 0.46) -> Image.Image:
    base = np.asarray(base_image.convert("RGB"), dtype=np.float32)
    color = np.asarray(mask_to_color(mask, colors), dtype=np.float32)
    overlay_pixels = mask > 0
    blended = base.copy()
    blended[overlay_pixels] = (1.0 - alpha) * base[overlay_pixels] + alpha * color[overlay_pixels]
    return Image.fromarray(np.clip(blended, 0, 255).astype(np.uint8), mode="RGB")


def shadow_overlay(base_image: Image.Image, shadow_mask: np.ndarray, alpha: float = 0.42) -> Image.Image:
    base = np.asarray(base_image.convert("RGB"), dtype=np.float32)
    color = np.zeros_like(base)
    color[shadow_mask == 1] = hex_to_rgb(SHADOW_COLORS[1])
    blended = base.copy()
    pixels = shadow_mask == 1
    blended[pixels] = (1.0 - alpha) * base[pixels] + alpha * color[pixels]
    return Image.fromarray(np.clip(blended, 0, 255).astype(np.uint8), mode="RGB")


def save_id_mask(path: Path, mask: np.ndarray) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(mask.astype(np.uint8), mode="L").save(path)
    return relative_posix(path)


def save_npy(path: Path, array: np.ndarray) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, array)
    return relative_posix(path)


def save_image(path: Path, image: Image.Image) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return relative_posix(path)


def thumbnail_with_label(image: Image.Image, label: str, tile_size: tuple[int, int]) -> Image.Image:
    label_height = 32
    tile = Image.new("RGB", tile_size, "white")
    body = image.copy()
    body.thumbnail((tile_size[0], tile_size[1] - label_height), Image.Resampling.LANCZOS)
    tile.paste(body, ((tile_size[0] - body.width) // 2, label_height + (tile_size[1] - label_height - body.height) // 2))
    draw = ImageDraw.Draw(tile)
    draw.text((8, 9), label, fill=(0, 0, 0))
    return tile


def contact_sheet(items: list[tuple[str, Image.Image]], path: Path, columns: int = 3) -> str:
    tile_size = (480, 390)
    rows = int(math.ceil(len(items) / columns))
    sheet = Image.new("RGB", (tile_size[0] * columns, tile_size[1] * rows), "white")
    for index, (label, image) in enumerate(items):
        tile = thumbnail_with_label(image, label, tile_size)
        sheet.paste(tile, ((index % columns) * tile_size[0], (index // columns) * tile_size[1]))
    return save_image(path, sheet)


def legend_image() -> Image.Image:
    image = Image.new("RGB", (640, 430), "white")
    draw = ImageDraw.Draw(image)
    draw.text((18, 18), "Physical surface-cover class IDs", fill=(0, 0, 0))
    y = 58
    for row in CLASS_MAPPING_ROWS:
        class_id = int(row["class_id"])
        draw.rectangle((24, y, 56, y + 24), fill=CLASS_COLORS[class_id], outline=(0, 0, 0))
        draw.text((70, y + 4), f"{class_id}: {row['class_name']}", fill=(0, 0, 0))
        y += 34
    draw.text((24, y + 10), "Shadow is separate: shadow_flag 0/1", fill=(0, 0, 0))
    return image


def normalize_shadow(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return 0
    text = str(value).strip().casefold()
    if text in {"0", "0.0", "false", "no", "n", "no_shadow", "not_shadowed", "not shadowed"}:
        return 0
    if text in {"1", "1.0", "true", "yes", "y", "shadow", "shadowed", "shadow_present"}:
        return 1
    try:
        number = int(float(text))
    except ValueError:
        return None
    return number if number in {0, 1} else None


def shadow_column(df: pd.DataFrame) -> str | None:
    for column in SHADOW_INPUT_COLUMNS:
        if column in df.columns:
            return column
    return None


def class_id_lookup() -> dict[str, int]:
    return {str(row["class_name"]): int(row["class_id"]) for row in CLASS_MAPPING_ROWS}


def load_required_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    required = [MAIN_ANNOTATION_XLSX, ROUND1_SUMMARY_XLSX, PART_B_ALIGNMENT_SUMMARY_XLSX]
    missing = [relative_posix(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing required Part C inputs: " + ", ".join(missing))
    annotations = read_table(MAIN_ANNOTATION_XLSX, keep_default_na=False)
    round1 = read_table(ROUND1_SUMMARY_XLSX, keep_default_na=False)
    alignment = read_table(PART_B_ALIGNMENT_SUMMARY_XLSX, keep_default_na=False)
    luhk = read_table(LUHK_CONTEXT_SUMMARY_XLSX, keep_default_na=False) if LUHK_CONTEXT_SUMMARY_XLSX.is_file() else pd.DataFrame()
    pilot_pairs = read_table(PART_B_PILOT_PAIRS_XLSX, keep_default_na=False) if PART_B_PILOT_PAIRS_XLSX.is_file() else pd.DataFrame()
    return annotations, round1, alignment, luhk, pilot_pairs


def add_validation(
    rows: list[dict[str, Any]],
    check_scope: str,
    check_name: str,
    status: str,
    severity: str,
    message: str,
    pair_id: str = "",
    segment_id: Any = "",
    path: str = "",
) -> None:
    rows.append(
        {
            "check_scope": check_scope,
            "pair_id": pair_id,
            "segment_id": segment_id,
            "check_name": check_name,
            "status": status,
            "severity": severity,
            "message": message,
            "path": path,
        }
    )


def validate_annotations(
    annotations: pd.DataFrame,
    round1: pd.DataFrame,
    alignment: pd.DataFrame,
    pilot_pairs: pd.DataFrame,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    allowed_classes = set(class_id_lookup()) - {NO_DATA_CLASS}
    required_columns = {"pair_id", "segment_id", "suggested_class", "manual_class", "confidence", "review_status", "notes"}
    missing_columns = sorted(required_columns - set(annotations.columns))
    if missing_columns:
        add_validation(rows, "annotations", "required_columns", "fail", "error", "Missing columns: " + ", ".join(missing_columns))
    else:
        add_validation(rows, "annotations", "required_columns", "pass", "info", "All required annotation columns are present.")

    shadow_col = shadow_column(annotations)
    if shadow_col is None:
        add_validation(rows, "annotations", "shadow_column", "warn", "warning", "No shadow_flag or shadow_status column found; shadow_flag will default to 0.")
    else:
        add_validation(rows, "annotations", "shadow_column", "pass", "info", f"Using `{shadow_col}` as the shadow flag source.")

    accepted_alignment = alignment.copy()
    if "alignment_quality" in accepted_alignment.columns:
        accepted_alignment = accepted_alignment.loc[
            accepted_alignment["alignment_quality"].astype(str).str.casefold().eq("acceptable")
        ]
    accepted_pair_ids = set(accepted_alignment["pair_id"].astype(str)) if "pair_id" in accepted_alignment.columns else set()
    pilot_pair_ids = set(pilot_pairs["pair_id"].astype(str)) if "pair_id" in pilot_pairs.columns else set()
    annotation_pair_ids = set(annotations["pair_id"].astype(str)) if "pair_id" in annotations.columns else set()

    unknown_accepted = sorted(annotation_pair_ids - accepted_pair_ids) if accepted_pair_ids else []
    unknown_pilot = sorted(annotation_pair_ids - pilot_pair_ids) if pilot_pair_ids else []
    if unknown_accepted:
        add_validation(rows, "annotations", "accepted_part_b_pair_ids", "fail", "error", "Annotation pair_id values not in accepted Part B alignment summary: " + "; ".join(unknown_accepted))
    else:
        add_validation(rows, "annotations", "accepted_part_b_pair_ids", "pass", "info", "All annotation pair_id values exist in the accepted Part B alignment summary.")
    if pilot_pair_ids and unknown_pilot:
        add_validation(rows, "annotations", "pilot_pair_ids", "fail", "error", "Annotation pair_id values not in Part B pilot pair list: " + "; ".join(unknown_pilot))
    elif pilot_pair_ids:
        add_validation(rows, "annotations", "pilot_pair_ids", "pass", "info", "All annotation pair_id values exist in the Part B pilot pair list.")

    invalid_manual = annotations.loc[~annotations["manual_class"].astype(str).str.strip().isin(allowed_classes)]
    blank_manual = annotations.loc[annotations["manual_class"].astype(str).str.strip().eq("")]
    legacy_shadow = annotations.loc[annotations["manual_class"].astype(str).str.strip().eq("shadow")]
    for _, row in invalid_manual.iterrows():
        add_validation(rows, "segment", "manual_class_valid", "fail", "error", f"Invalid manual_class `{row['manual_class']}`.", str(row["pair_id"]), row["segment_id"])
    if invalid_manual.empty:
        add_validation(rows, "annotations", "manual_class_valid", "pass", "info", "All manual_class values are approved physical surface-cover classes.")
    if not blank_manual.empty:
        add_validation(rows, "annotations", "blank_manual_class", "warn", "warning", f"{len(blank_manual)} blank manual_class rows will be treated as no_data_unreviewed.")
    else:
        add_validation(rows, "annotations", "blank_manual_class", "pass", "info", "No blank manual_class values.")
    if not legacy_shadow.empty:
        add_validation(rows, "annotations", "legacy_shadow_class", "fail", "error", f"{len(legacy_shadow)} rows still use manual_class=shadow.")
    else:
        add_validation(rows, "annotations", "legacy_shadow_class", "pass", "info", "No rows use shadow as a physical surface-cover class.")

    if shadow_col is not None:
        normalized = annotations[shadow_col].map(normalize_shadow)
        invalid_shadow = annotations.loc[normalized.isna()]
        for _, row in invalid_shadow.iterrows():
            add_validation(rows, "segment", "shadow_flag_binary", "fail", "error", f"Invalid shadow value `{row[shadow_col]}`.", str(row["pair_id"]), row["segment_id"])
        if invalid_shadow.empty:
            add_validation(rows, "annotations", "shadow_flag_binary", "pass", "info", "All shadow values are binary 0/1.")

    blank_confidence = annotations.loc[annotations["confidence"].astype(str).str.strip().eq("")]
    blank_status = annotations.loc[annotations["review_status"].astype(str).str.strip().eq("")]
    if blank_confidence.empty:
        add_validation(rows, "annotations", "confidence_present", "pass", "info", "All confidence values are present.")
    else:
        add_validation(rows, "annotations", "confidence_present", "warn", "warning", f"{len(blank_confidence)} rows have blank confidence.")
    if blank_status.empty:
        add_validation(rows, "annotations", "review_status_present", "pass", "info", "All review_status values are present.")
    else:
        add_validation(rows, "annotations", "review_status_present", "warn", "warning", f"{len(blank_status)} rows have blank review_status.")

    if "segment_id_map_16bit_path" not in round1.columns:
        add_validation(rows, "round1", "segment_map_paths", "fail", "error", "Round 1 summary is missing segment_id_map_16bit_path.")
    else:
        for _, summary_row in round1.iterrows():
            pair_id = str(summary_row["pair_id"])
            pair_annotations = annotations.loc[annotations["pair_id"].astype(str).eq(pair_id)].copy()
            label_path = resolve_project_path(summary_row["segment_id_map_16bit_path"])
            if pair_annotations.empty:
                add_validation(rows, "pair", "annotation_rows_present", "fail", "error", "No annotation rows for pair.", pair_id, "", relative_posix(label_path))
                continue
            if not label_path.is_file():
                add_validation(rows, "pair", "segment_map_exists", "fail", "error", "Missing segment ID map.", pair_id, "", relative_posix(label_path))
                continue
            labels = np.asarray(Image.open(label_path), dtype=np.int32)
            segment_ids_in_map = {int(value) for value in np.unique(labels) if int(value) > 0}
            segment_ids_in_annotations = {int(value) for value in pair_annotations["segment_id"].astype(int)}
            missing_in_annotations = sorted(segment_ids_in_map - segment_ids_in_annotations)
            extra_in_annotations = sorted(segment_ids_in_annotations - segment_ids_in_map)
            if missing_in_annotations:
                add_validation(rows, "pair", "segment_ids_complete", "fail", "error", f"Segment IDs missing annotations: {missing_in_annotations[:12]}", pair_id, "")
            if extra_in_annotations:
                add_validation(rows, "pair", "segment_ids_exist", "fail", "error", f"Annotation segment IDs absent from map: {extra_in_annotations[:12]}", pair_id, "")
            if not missing_in_annotations and not extra_in_annotations:
                add_validation(rows, "pair", "segment_ids_match", "pass", "info", f"{len(segment_ids_in_map)} segment IDs validated.", pair_id, "")

    severity_counts = pd.Series([row["severity"] for row in rows]).value_counts().to_dict()
    stats = {
        "annotation_rows": len(annotations),
        "pair_count": len(annotation_pair_ids),
        "validation_error_count": int(severity_counts.get("error", 0)),
        "validation_warning_count": int(severity_counts.get("warning", 0)),
        "unresolved_segment_count": int(len(invalid_manual) + len(blank_manual)),
        "legacy_shadow_segment_count": int(len(legacy_shadow)),
        "shadow_source_column": shadow_col or "",
    }
    return rows, stats


def write_validation_reports(rows: list[dict[str, Any]], stats: dict[str, Any]) -> None:
    write_rows(VALIDATION_XLSX, rows, ["check_scope", "pair_id", "segment_id", "check_name", "status", "severity", "message", "path"])
    lines = [
        "# Part C Manual Annotation Validation",
        "",
        f"- Annotation rows checked: {stats['annotation_rows']}",
        f"- Pair count: {stats['pair_count']}",
        f"- Validation errors: {stats['validation_error_count']}",
        f"- Validation warnings: {stats['validation_warning_count']}",
        f"- Unresolved segments: {stats['unresolved_segment_count']}",
        f"- Legacy manual_class=shadow rows: {stats['legacy_shadow_segment_count']}",
        f"- Shadow source column: `{stats['shadow_source_column'] or 'none'}`",
        "",
        "Shadow is validated as an independent binary state and is not included as a physical surface-cover class.",
        "",
        "## Issues",
        "",
    ]
    issue_rows = [row for row in rows if row["severity"] in {"error", "warning"}]
    if issue_rows:
        for row in issue_rows:
            segment = f" segment {row['segment_id']}" if str(row.get("segment_id", "")).strip() else ""
            pair = f" `{row['pair_id']}`" if str(row.get("pair_id", "")).strip() else ""
            lines.append(f"- [{row['severity']}] {row['check_name']}{pair}{segment}: {row['message']}")
    else:
        lines.append("- No blocking validation issues found.")
    VALIDATION_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_mapping_tables() -> None:
    write_rows(CLASS_MAPPING_XLSX, CLASS_MAPPING_ROWS, ["class_id", "class_name", "description"])
    write_rows(SHADOW_MAPPING_XLSX, SHADOW_MAPPING_ROWS, ["shadow_flag", "shadow_name", "description"])


def manual_review_status(pair_df: pd.DataFrame) -> str:
    statuses = {str(value).strip() for value in pair_df["review_status"].tolist()}
    if statuses == {"Yes"}:
        return "all_reviewed"
    if "Yes" in statuses:
        return "partially_reviewed"
    return "not_reviewed"


def generate_masks_and_summaries(
    annotations: pd.DataFrame,
    round1: pd.DataFrame,
    luhk: pd.DataFrame,
    validation_stats: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    class_ids = class_id_lookup()
    shadow_col = shadow_column(annotations)
    mask_manifest: list[dict[str, Any]] = []
    surface_summary: list[dict[str, Any]] = []
    shadow_summary: list[dict[str, Any]] = []
    combined_summary: list[dict[str, Any]] = []
    legend = legend_image()

    for _, summary_row in round1.iterrows():
        pair_id = str(summary_row["pair_id"])
        image_id = str(summary_row["image_id"])
        pair_df = annotations.loc[annotations["pair_id"].astype(str).eq(pair_id)].copy()
        label_path = resolve_project_path(summary_row["segment_id_map_16bit_path"])
        labels = np.asarray(Image.open(label_path), dtype=np.int32)
        class_mask = np.zeros(labels.shape, dtype=np.uint8)
        shadow_mask = np.zeros(labels.shape, dtype=np.uint8)
        low_conf_mask = np.zeros(labels.shape, dtype=bool)

        for _, row in pair_df.iterrows():
            segment_id = int(row["segment_id"])
            segment_pixels = labels == segment_id
            manual_class = str(row["manual_class"]).strip()
            class_id = class_ids.get(manual_class, 0)
            class_mask[segment_pixels] = class_id
            shadow_flag = normalize_shadow(row[shadow_col]) if shadow_col is not None else 0
            shadow_mask[segment_pixels] = 0 if shadow_flag is None else shadow_flag
            if str(row.get("confidence", "")).strip().casefold() == "low":
                low_conf_mask[segment_pixels] = True

        out_dir = MASK_DIR / image_id
        out_dir.mkdir(parents=True, exist_ok=True)
        thermal_shape = f"{class_mask.shape[1]}x{class_mask.shape[0]}"

        refined_visible = ImageOps.exif_transpose(Image.open(resolve_project_path(summary_row["refined_visible_roi_path"]))).convert("RGB")
        thermal_grid_visible = ImageOps.exif_transpose(Image.open(resolve_project_path(summary_row["refined_visible_roi_resized_to_thermal_grid_path"]))).convert("RGB")
        thermal_preview = ImageOps.exif_transpose(Image.open(resolve_project_path(summary_row["thermal_preview_path"]))).convert("RGB")

        class_mask_visible = np.asarray(
            Image.fromarray(class_mask, mode="L").resize(refined_visible.size, Image.Resampling.NEAREST),
            dtype=np.uint8,
        )
        shadow_mask_visible = np.asarray(
            Image.fromarray(shadow_mask, mode="L").resize(refined_visible.size, Image.Resampling.NEAREST),
            dtype=np.uint8,
        )

        class_color_thermal = mask_to_color(class_mask, CLASS_COLORS)
        class_color_visible = mask_to_color(class_mask_visible, CLASS_COLORS)
        shadow_color_thermal = mask_to_color(shadow_mask, SHADOW_COLORS)
        shadow_color_visible = mask_to_color(shadow_mask_visible, SHADOW_COLORS)
        class_overlay_visible = overlay_mask(refined_visible, class_mask_visible, CLASS_COLORS)
        class_overlay_thermal = overlay_mask(thermal_preview, class_mask, CLASS_COLORS)
        class_overlay_thermal_grid_visible = overlay_mask(thermal_grid_visible, class_mask, CLASS_COLORS)
        shadow_overlay_visible = shadow_overlay(refined_visible, shadow_mask_visible)
        shadow_overlay_thermal = shadow_overlay(thermal_preview, shadow_mask)

        paths = {
            "class_mask_thermal_grid_npy_path": save_npy(out_dir / f"{image_id}_physical_surface_cover_class_id_thermal_grid.npy", class_mask),
            "class_mask_thermal_grid_png_path": save_id_mask(out_dir / f"{image_id}_physical_surface_cover_class_id_thermal_grid.png", class_mask),
            "class_mask_visible_roi_npy_path": save_npy(out_dir / f"{image_id}_physical_surface_cover_class_id_visible_roi.npy", class_mask_visible),
            "class_mask_visible_roi_png_path": save_id_mask(out_dir / f"{image_id}_physical_surface_cover_class_id_visible_roi.png", class_mask_visible),
            "class_color_preview_thermal_grid_path": save_image(out_dir / f"{image_id}_physical_surface_cover_color_thermal_grid.png", class_color_thermal),
            "class_color_preview_visible_roi_path": save_image(out_dir / f"{image_id}_physical_surface_cover_color_visible_roi.png", class_color_visible),
            "class_overlay_on_visible_roi_path": save_image(out_dir / f"{image_id}_physical_surface_cover_overlay_on_visible_roi.png", class_overlay_visible),
            "class_overlay_on_thermal_preview_path": save_image(out_dir / f"{image_id}_physical_surface_cover_overlay_on_thermal_preview.png", class_overlay_thermal),
            "class_overlay_on_thermal_grid_visible_roi_path": save_image(out_dir / f"{image_id}_physical_surface_cover_overlay_on_thermal_grid_visible_roi.png", class_overlay_thermal_grid_visible),
            "shadow_mask_thermal_grid_npy_path": save_npy(out_dir / f"{image_id}_shadow_flag_thermal_grid.npy", shadow_mask),
            "shadow_mask_thermal_grid_png_path": save_id_mask(out_dir / f"{image_id}_shadow_flag_thermal_grid.png", shadow_mask),
            "shadow_mask_visible_roi_npy_path": save_npy(out_dir / f"{image_id}_shadow_flag_visible_roi.npy", shadow_mask_visible),
            "shadow_mask_visible_roi_png_path": save_id_mask(out_dir / f"{image_id}_shadow_flag_visible_roi.png", shadow_mask_visible),
            "shadow_preview_thermal_grid_path": save_image(out_dir / f"{image_id}_shadow_flag_preview_thermal_grid.png", shadow_color_thermal),
            "shadow_preview_visible_roi_path": save_image(out_dir / f"{image_id}_shadow_flag_preview_visible_roi.png", shadow_color_visible),
            "shadow_overlay_on_visible_roi_path": save_image(out_dir / f"{image_id}_shadow_flag_overlay_on_visible_roi.png", shadow_overlay_visible),
            "shadow_overlay_on_thermal_preview_path": save_image(out_dir / f"{image_id}_shadow_flag_overlay_on_thermal_preview.png", shadow_overlay_thermal),
            "class_legend_path": save_image(out_dir / f"{image_id}_physical_surface_cover_legend.png", legend),
        }
        paths["final_mask_contact_sheet_path"] = contact_sheet(
            [
                ("Refined visible ROI", refined_visible),
                ("Thermal preview, no temperature", thermal_preview),
                ("Physical mask, thermal grid", class_color_thermal),
                ("Physical overlay on thermal preview", class_overlay_thermal),
                ("Physical overlay on visible ROI", class_overlay_visible),
                ("Shadow flag preview", shadow_color_thermal),
            ],
            out_dir / f"{image_id}_final_mask_contact_sheet.png",
            columns=3,
        )

        total_pixels = int(class_mask.size)
        no_data_pixels = int((class_mask == 0).sum())
        unclear_pixels = int((class_mask == class_ids["unclear_ignore"]).sum())
        low_conf_pixels = int(low_conf_mask.sum())
        reviewed_pixels = total_pixels - no_data_pixels
        no_data_percent = no_data_pixels / total_pixels * 100.0
        unclear_percent = unclear_pixels / total_pixels * 100.0
        low_conf_percent = low_conf_pixels / total_pixels * 100.0
        usable_for_part_d = "yes" if no_data_pixels == 0 and validation_stats["validation_error_count"] == 0 else "no"
        usability_note = "Ready for Part D mask join; thermal temperatures not extracted in Part C." if usable_for_part_d == "yes" else "Review validation report before Part D."

        for row in CLASS_MAPPING_ROWS:
            class_id = int(row["class_id"])
            class_name = str(row["class_name"])
            pixel_count = int((class_mask == class_id).sum())
            surface_summary.append(
                {
                    "pair_id": pair_id,
                    "image_id": image_id,
                    "class_id": class_id,
                    "class_name": class_name,
                    "pixel_count": pixel_count,
                    "area_percent": round(pixel_count / total_pixels * 100.0, 6),
                    "reviewed_pixel_percent": round(reviewed_pixels / total_pixels * 100.0, 6),
                    "no_data_unreviewed_percent": round(no_data_percent, 6),
                    "unclear_ignore_percent": round(unclear_percent, 6),
                    "low_confidence_percent": round(low_conf_percent, 6),
                    "usable_for_part_d": usable_for_part_d,
                    "notes": usability_note,
                }
            )

        shadow_pixels = int((shadow_mask == 1).sum())
        non_shadow_pixels = int((shadow_mask == 0).sum())
        shadow_summary.append(
            {
                "pair_id": pair_id,
                "image_id": image_id,
                "shadow_pixel_count": shadow_pixels,
                "non_shadow_pixel_count": non_shadow_pixels,
                "shadow_percent": round(shadow_pixels / total_pixels * 100.0, 6),
                "non_shadow_percent": round(non_shadow_pixels / total_pixels * 100.0, 6),
                "shadow_data_available": "yes" if shadow_col is not None else "no",
                "notes": "Shadow is a binary state and is summarized separately from physical surface-cover classes.",
            }
        )

        luhk_pair = luhk.loc[luhk["pair_id"].astype(str).eq(pair_id)].copy() if not luhk.empty and "pair_id" in luhk.columns else pd.DataFrame()
        dominant_luhk = str(summary_row.get("dominant_luhk_class", ""))
        luhk_props = ""
        spatial_notes = ""
        if not luhk_pair.empty:
            luhk_props = "; ".join(
                f"{row['luhk_category_name']}={float(row['proportion']):.6f}"
                for _, row in luhk_pair.iterrows()
            )
            spatial_notes = " | ".join(sorted({str(value) for value in luhk_pair["spatial_uncertainty_note"].tolist()}))
        physical_props = "; ".join(
            f"{row['class_name']}={row['area_percent']:.6f}"
            for row in surface_summary
            if row["pair_id"] == pair_id and int(row["class_id"]) != 0
        )
        combined_summary.append(
            {
                "pair_id": pair_id,
                "image_id": image_id,
                "dominant_luhk_class": dominant_luhk,
                "luhk_class_proportions": luhk_props,
                "physical_surface_cover_class_proportions": physical_props,
                "shadow_percent": round(shadow_pixels / total_pixels * 100.0, 6),
                "spatial_uncertainty_notes": spatial_notes,
                "alignment_quality": str(summary_row.get("part_b_alignment_quality", "")),
                "manual_review_status": manual_review_status(pair_df),
                "usable_for_part_d": usable_for_part_d,
            }
        )

        manifest_row = {
            "pair_id": pair_id,
            "image_id": image_id,
            "thermal_grid_shape": thermal_shape,
            "visible_roi_shape": f"{refined_visible.width}x{refined_visible.height}",
            "class_mapping_path": relative_posix(CLASS_MAPPING_XLSX),
            "shadow_mapping_path": relative_posix(SHADOW_MAPPING_XLSX),
            "usable_for_part_d": usable_for_part_d,
        }
        manifest_row.update(paths)
        mask_manifest.append(manifest_row)

    return mask_manifest, surface_summary, shadow_summary, combined_summary


def write_markdown_table_summary(path: Path, title: str, lines: list[str]) -> None:
    path.write_text("\n".join([f"# {title}", "", *lines, ""]) + "\n", encoding="utf-8")


def write_summary_reports(
    mask_manifest: list[dict[str, Any]],
    surface_summary: list[dict[str, Any]],
    shadow_summary: list[dict[str, Any]],
    combined_summary: list[dict[str, Any]],
    validation_stats: dict[str, Any],
    backup_paths: list[str],
) -> None:
    write_rows(MASK_MANIFEST_XLSX, mask_manifest)
    write_rows(SURFACE_SUMMARY_XLSX, surface_summary)
    write_rows(SHADOW_SUMMARY_XLSX, shadow_summary)
    write_rows(COMBINED_SUMMARY_XLSX, combined_summary)

    ready_count = sum(1 for row in combined_summary if row["usable_for_part_d"] == "yes")
    pair_count = len(combined_summary)
    write_markdown_table_summary(
        SURFACE_SUMMARY_MD,
        "Part C Physical Surface-Cover Summary",
        [
            f"- Pairs summarized: {pair_count}",
            f"- Pairs marked usable_for_part_d=yes: {ready_count}",
            f"- Table: `{relative_posix(SURFACE_SUMMARY_XLSX)}`",
            "- Physical surface-cover percentages exclude shadow as a class.",
            "- `no_data_unreviewed` and `unclear_ignore` are separate IDs and are not silently merged.",
        ],
    )
    write_markdown_table_summary(
        SHADOW_SUMMARY_MD,
        "Part C Shadow Flag Summary",
        [
            f"- Pairs summarized: {pair_count}",
            f"- Table: `{relative_posix(SHADOW_SUMMARY_XLSX)}`",
            "- Shadow is a binary observation state and is not a physical surface-cover class.",
            "- A pixel can have both a physical class and `shadow_flag=1`.",
        ],
    )
    write_markdown_table_summary(
        COMBINED_SUMMARY_MD,
        "Part C LUHK, Physical Surface-Cover, and Shadow Combined Summary",
        [
            f"- Pairs summarized: {pair_count}",
            f"- Pairs marked usable_for_part_d=yes: {ready_count}",
            f"- Table: `{relative_posix(COMBINED_SUMMARY_XLSX)}`",
            "- LUHK is official broad land-use context.",
            "- Physical surface cover comes from visible-image manual review on Part C segments.",
            "- Shadow is an illumination or observation state.",
        ],
    )

    mask_lines = [
        "# Part C Final Masks",
        "",
        "This directory contains final pilot physical surface-cover masks and separate shadow_flag masks generated from reviewed Part C segment annotations.",
        "",
        "No thermal temperatures or delta T values are extracted here.",
        "",
        "Each pair directory stores thermal-grid class ID masks, visible-ROI resampled masks, color previews, overlays, NumPy arrays, and a final contact sheet.",
        "",
        f"Manifest: `{relative_posix(MASK_MANIFEST_XLSX)}`",
        f"Class mapping: `{relative_posix(CLASS_MAPPING_XLSX)}`",
        f"Shadow mapping: `{relative_posix(SHADOW_MAPPING_XLSX)}`",
        "",
    ]
    MASK_README.write_text("\n".join(mask_lines), encoding="utf-8")

    final_lines = [
        "# Part C Round 3 Final Mask Generation Summary",
        "",
        "## Files Read",
        "",
        f"- Manual annotations: `{relative_posix(MAIN_ANNOTATION_XLSX)}`",
        f"- Part C Round 1 summary: `{relative_posix(ROUND1_SUMMARY_XLSX)}`",
        f"- Accepted Part B alignment summary: `{relative_posix(PART_B_ALIGNMENT_SUMMARY_XLSX)}`",
        f"- LUHK context summary: `{relative_posix(LUHK_CONTEXT_SUMMARY_XLSX)}`",
        "",
        "## Annotation Validation",
        "",
        f"- Validation report: `{relative_posix(VALIDATION_XLSX)}`",
        f"- Validation markdown: `{relative_posix(VALIDATION_MD)}`",
        f"- Validation errors: {validation_stats['validation_error_count']}",
        f"- Validation warnings: {validation_stats['validation_warning_count']}",
        f"- Unresolved segments: {validation_stats['unresolved_segment_count']}",
        "",
        "## Outputs Generated",
        "",
        f"- Mask manifest: `{relative_posix(MASK_MANIFEST_XLSX)}`",
        f"- Physical surface-cover summary: `{relative_posix(SURFACE_SUMMARY_XLSX)}`",
        f"- Shadow flag summary: `{relative_posix(SHADOW_SUMMARY_XLSX)}`",
        f"- Combined LUHK/surface/shadow summary: `{relative_posix(COMBINED_SUMMARY_XLSX)}`",
        f"- Class mapping: `{relative_posix(CLASS_MAPPING_XLSX)}`",
        f"- Shadow mapping: `{relative_posix(SHADOW_MAPPING_XLSX)}`",
        "",
        "## Manual Work Protection",
        "",
        f"- Annotation backups created: {len(backup_paths)}",
    ]
    final_lines.extend([f"  - `{path}`" for path in backup_paths])
    final_lines.extend(
        [
            "",
            "## Part D Readiness",
            "",
            f"- Pilot pairs ready for Part D: {ready_count}/{pair_count}",
            "- Part D can join thermal temperatures to these masks later, but no temperature extraction was run in Part C.",
            "",
            "## Outputs To Inspect Manually",
            "",
            f"- `{relative_posix(MASK_MANIFEST_XLSX)}`",
            f"- `outputs/part_c/masks/<image_id>/<image_id>_final_mask_contact_sheet.png`",
            f"- `{relative_posix(COMBINED_SUMMARY_XLSX)}`",
            "",
            "## Restrictions Honored",
            "",
            "- Part A was not redone.",
            "- Part B was not redone.",
            "- Part C Round 1 segmentation was not redone.",
            "- No thermal temperature extraction was run.",
            "- No delta T was calculated.",
            "- No model was trained.",
            "- Shadow is not treated as a physical surface-cover class.",
            "",
        ]
    )
    ROUND3_FINAL_MD.write_text("\n".join(final_lines), encoding="utf-8")


def write_method_update() -> None:
    method_path = SUMMARY_DIR / "part_c_round1_1_method_update.md"
    lines = [
        "# Part C Round 1.1 Method Update",
        "",
        "Part C uses a semi-automatic, manually reviewed workflow.",
        "",
        "Primary method:",
        "",
        "1. Use the accepted refined visible ROI from Part B.",
        "2. Generate candidate regions using SLIC superpixels on the refined ROI resized to the thermal grid.",
        "3. Manually review and label each segment.",
        "4. Convert reviewed labels into thermal-grid-aligned physical surface-cover masks.",
        "5. Treat shadow as a separate binary `shadow_flag`, not as physical surface cover.",
        "6. Combine physical surface-cover labels with LUHK broad land-use context.",
        "7. Preserve uncertainty with confidence, review_status, notes, no_data_unreviewed, and unclear_ignore.",
        "",
        "No temperature extraction, delta T calculation, or supervised model training is part of this step.",
        "",
        "Baseline and automation methods are planning/comparison options only and are documented in `docs/part_c_automation_and_baseline_methods.md`.",
        "",
    ]
    method_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ensure_dirs()
    backup_paths = copy_review_backups()
    write_mapping_tables()
    annotations, round1, alignment, luhk, pilot_pairs = load_required_inputs()
    validation_rows, validation_stats = validate_annotations(annotations, round1, alignment, pilot_pairs)
    write_validation_reports(validation_rows, validation_stats)
    mask_manifest, surface_summary, shadow_summary, combined_summary = generate_masks_and_summaries(
        annotations,
        round1,
        luhk,
        validation_stats,
    )
    write_summary_reports(mask_manifest, surface_summary, shadow_summary, combined_summary, validation_stats, backup_paths)
    write_method_update()
    print(f"Annotation backups created: {len(backup_paths)}")
    print(f"Validation errors: {validation_stats['validation_error_count']}")
    print(f"Validation warnings: {validation_stats['validation_warning_count']}")
    print(f"Mask pairs generated: {len(mask_manifest)}")
    print(f"Mask manifest: {relative_posix(MASK_MANIFEST_XLSX)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
