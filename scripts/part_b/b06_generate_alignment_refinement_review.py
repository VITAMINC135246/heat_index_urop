#!/usr/bin/env python3
"""Generate Part B Round 1.1 V/T alignment refinement review figures."""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageOps

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from table_io import read_table, write_rows

from b05_refine_vt_alignment import (
    ALIGNMENT_SUMMARY_XLSX,
    PROJECT_ROOT,
    as_float,
    as_int,
    crop_for_alignment,
    edge_bundle,
    relative_posix,
    resolve_project_path,
)


SUMMARY_MD = PROJECT_ROOT / "outputs" / "part_b" / "summaries" / "part_b_round1_1_alignment_summary.md"
ROUND1_PILOT_XLSX = PROJECT_ROOT / "data" / "metadata" / "part_b_pilot_pairs.xlsx"
ROUND1_LOCAL_OUTPUTS_MANIFEST_XLSX = (
    PROJECT_ROOT / "outputs" / "part_b" / "summaries" / "part_b_round1_local_outputs_manifest.xlsx"
)


def write_rows_xlsx(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    write_rows(path, rows, columns)


def load_rgb(path: Path) -> Image.Image:
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image)
        image.load()
        if image.mode == "L":
            return ImageOps.autocontrast(image).convert("RGB")
        return image.convert("RGB")


def thermal_preview(thermal: Image.Image, size: tuple[int, int] | None = None) -> Image.Image:
    preview = ImageOps.autocontrast(thermal.convert("L")).convert("RGB")
    if size and preview.size != size:
        preview = preview.resize(size, Image.Resampling.BILINEAR)
    return preview


def parse_bbox(row: pd.Series, prefix: str) -> tuple[int, int, int, int]:
    return (
        as_int(row[f"{prefix}_roi_x_min_px"]),
        as_int(row[f"{prefix}_roi_y_min_px"]),
        as_int(row[f"{prefix}_roi_x_max_px"]),
        as_int(row[f"{prefix}_roi_y_max_px"]),
    )


def thumbnail_copy(image: Image.Image, max_size: tuple[int, int]) -> Image.Image:
    copy = image.copy()
    copy.thumbnail(max_size, Image.Resampling.LANCZOS)
    return copy


def draw_roi_box(
    visible: Image.Image,
    bbox: tuple[int, int, int, int],
    label: str,
    color: tuple[int, int, int],
) -> Image.Image:
    preview = thumbnail_copy(visible, (1400, 1050))
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
            outline=color,
        )
    text_bbox = draw.textbbox((0, 0), label)
    draw.rectangle((0, 0, text_bbox[2] + 18, text_bbox[3] + 16), fill=(255, 255, 255))
    draw.text((8, 6), label, fill=(0, 0, 0))
    return preview


def alpha_blend(visible_roi: Image.Image, thermal: Image.Image) -> Image.Image:
    thermal_rgb = thermal_preview(thermal, visible_roi.size)
    return Image.blend(visible_roi.convert("RGB"), thermal_rgb.convert("RGB"), 0.45)


def side_by_side(left: Image.Image, right: Image.Image, left_label: str, right_label: str) -> Image.Image:
    width = left.width + right.width
    height = max(left.height, right.height) + 34
    canvas = Image.new("RGB", (width, height), "white")
    canvas.paste(left, (0, 34))
    canvas.paste(right, (left.width, 34))
    draw = ImageDraw.Draw(canvas)
    draw.text((8, 8), left_label, fill=(0, 0, 0))
    draw.text((left.width + 8, 8), right_label, fill=(0, 0, 0))
    return canvas


def edge_overlay(visible_roi: Image.Image, thermal: Image.Image) -> Image.Image:
    size = thermal.size
    visible_features = edge_bundle(visible_roi, size)
    thermal_features = edge_bundle(thermal_preview(thermal, size), size)
    visible_edges = visible_features["edges"]
    thermal_edges = thermal_features["edges"]
    overlay = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    overlay[thermal_edges] = [255, 40, 40]
    overlay[visible_edges] = [40, 210, 255]
    overlay[np.logical_and(visible_edges, thermal_edges)] = [255, 230, 30]
    return Image.fromarray(overlay, mode="RGB")


def labelled_tile(image: Image.Image, label: str, tile_size: tuple[int, int]) -> Image.Image:
    tile_width, tile_height = tile_size
    label_height = 28
    canvas = Image.new("RGB", tile_size, "white")
    body = thumbnail_copy(image, (tile_width, tile_height - label_height))
    x = (tile_width - body.width) // 2
    y = label_height + (tile_height - label_height - body.height) // 2
    canvas.paste(body, (x, y))
    draw = ImageDraw.Draw(canvas)
    draw.text((8, 7), label, fill=(0, 0, 0))
    return canvas


def make_contact_sheet(items: list[tuple[str, Image.Image]], path: Path) -> None:
    tile_size = (520, 390)
    columns = 2
    rows = int(math.ceil(len(items) / columns))
    sheet = Image.new("RGB", (tile_size[0] * columns, tile_size[1] * rows), "white")
    for index, (label, image) in enumerate(items):
        tile = labelled_tile(image, label, tile_size)
        x = (index % columns) * tile_size[0]
        y = (index // columns) * tile_size[1]
        sheet.paste(tile, (x, y))
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)


def save_image(path_text: Any, image: Image.Image) -> None:
    path = resolve_project_path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def generate_pair_review(row: pd.Series) -> dict[str, Any]:
    image_id = str(row["image_id"])
    visible = load_rgb(resolve_project_path(row["v_path"]))
    thermal = load_rgb(resolve_project_path(row["t_path"]))
    thermal_rgb = thermal_preview(thermal, thermal.size)
    old_bbox = parse_bbox(row, "old")
    refined_bbox = parse_bbox(row, "refined")
    rotation = as_float(row.get("rotation_deg")) or 0.0

    old_roi = crop_for_alignment(visible, old_bbox, thermal.size, 0.0)
    refined_roi = crop_for_alignment(visible, refined_bbox, thermal.size, rotation)

    old_box = draw_roi_box(visible, old_bbox, f"{image_id} old ROI", (255, 45, 45))
    refined_box = draw_roi_box(visible, refined_bbox, f"{image_id} refined ROI", (20, 160, 255))
    old_blend = alpha_blend(old_roi, thermal)
    refined_blend = alpha_blend(refined_roi, thermal)
    old_side = side_by_side(old_roi, thermal_rgb, "Old visible ROI", "Thermal preview")
    refined_side = side_by_side(refined_roi, thermal_rgb, "Refined visible ROI", "Thermal preview")
    old_edges = edge_overlay(old_roi, thermal)
    refined_edges = edge_overlay(refined_roi, thermal)
    gcp_side = side_by_side(
        draw_roi_box(visible, refined_bbox, "Full visible image with refined ROI", (20, 160, 255)),
        thumbnail_copy(thermal_rgb, (700, 560)),
        "Visible reference for GCP selection",
        "Thermal reference for GCP selection",
    )

    save_image(row["old_roi_box_path"], old_box)
    save_image(row["refined_roi_box_path"], refined_box)
    save_image(row["old_blend_overlay_path"], old_blend)
    save_image(row["refined_blend_overlay_path"], refined_blend)
    save_image(row["old_side_by_side_path"], old_side)
    save_image(row["refined_side_by_side_path"], refined_side)
    save_image(row["old_edge_overlay_path"], old_edges)
    save_image(row["refined_edge_overlay_path"], refined_edges)
    save_image(row["manual_gcp_side_by_side_path"], gcp_side)

    contact_items = [
        ("Old ROI box", old_box),
        ("Refined ROI box", refined_box),
        ("Old alpha blend", old_blend),
        ("Refined alpha blend", refined_blend),
        ("Old side by side", old_side),
        ("Refined side by side", refined_side),
        ("Old edge overlay", old_edges),
        ("Refined edge overlay", refined_edges),
        ("Manual GCP reference", gcp_side),
    ]
    make_contact_sheet(contact_items, resolve_project_path(row["contact_sheet_path"]))

    return {
        "image_id": image_id,
        "contact_sheet_path": row["contact_sheet_path"],
        "alignment_quality": row["alignment_quality"],
        "needs_manual_gcp": row["needs_manual_gcp"],
        "score_delta": row.get("score_delta", ""),
    }


def write_summary_md(rows: pd.DataFrame, generated: list[dict[str, Any]]) -> None:
    lines: list[str] = []
    lines.append("# Part B Round 1.1 Alignment Summary")
    lines.append("")
    lines.append(
        "This package preserves the existing Part B Round 1 review outputs and adds "
        "before/after V/T alignment refinement figures for the same five HKUST pilot pairs."
    )
    lines.append("")
    lines.append("No surface-cover annotation was ingested, no superpixels were converted to masks, and no thermal temperature data was extracted.")
    lines.append("")
    lines.append("## Stage Boundary")
    lines.append("")
    lines.append("- Part B is currently V/T alignment and thermal ROI acceptance only.")
    lines.append("- Existing Round 1 superpixel and annotation XLSX outputs are parked for future Part C preparation.")
    lines.append("- Automatic cross-modal scores are diagnostics; visual/manual acceptance is still required.")
    lines.append("")
    lines.append("## Pilot Pair Results")
    lines.append("")
    for _, row in rows.iterrows():
        score_delta = row.get("score_delta", "")
        score_text = f", score_delta={score_delta}" if str(score_delta) else ""
        adjustment = (
            f"dx={row.get('dx_px', '')}, dy={row.get('dy_px', '')}, "
            f"scale={row.get('scale', '')}, rotation={row.get('rotation_deg', '')}"
        )
        lines.append(
            f"- {row['image_id']}: quality={row['alignment_quality']}, "
            f"confidence={row['confidence']}, needs_manual_gcp={row['needs_manual_gcp']}, "
            f"method={row.get('method_used', '')}, {adjustment}{score_text}."
        )
    lines.append("")
    lines.append("## Review First")
    lines.append("")
    for item in generated:
        lines.append(f"- `{item['contact_sheet_path']}`")
    lines.append("")
    lines.append("For each pair, compare the old and refined alpha blends, edge overlays, and full-visible ROI boxes.")
    lines.append("")
    lines.append("## Alignment Data")
    lines.append("")
    lines.append("- `outputs/part_b/summaries/part_b_round1_1_alignment_summary.xlsx`")
    lines.append("- `outputs/part_b/summaries/part_b_round1_1_alignment_attempts.xlsx`")
    lines.append("- `outputs/part_b/summaries/part_b_round1_local_outputs_manifest.xlsx`")
    lines.append("- `outputs/part_b/alignment_refinement/<image_id>/top_alignment_candidates.xlsx`")
    lines.append("- `outputs/part_b/alignment_refinement/<image_id>/manual_gcp_template.xlsx`")
    lines.append("")
    lines.append("## Known Limitations")
    lines.append("")
    if rows.get("opencv_available", pd.Series(dtype=str)).astype(str).str.casefold().eq("yes").any():
        lines.append("- OpenCV was available for this run; phase correlation, ECC, and ORB attempts are recorded in the attempts XLSX.")
    else:
        lines.append("- OpenCV was unavailable for this run; OpenCV methods are recorded as skipped in the attempts XLSX.")
    lines.append("- Edge and gradient scores can improve for the wrong reason across thermal-visible imagery.")
    lines.append("- Refined crop/rotation candidates still require visual acceptance before Part B is closed.")
    lines.append("- Manual GCP residuals are blank until included control points are filled.")
    SUMMARY_MD.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_round1_local_outputs_manifest(alignment_rows: pd.DataFrame) -> None:
    if not ROUND1_PILOT_XLSX.exists():
        return
    pilot_rows = read_table(ROUND1_PILOT_XLSX, dtype=str).fillna("")
    alignment_by_image = {
        str(row["image_id"]): row
        for _, row in alignment_rows.iterrows()
    }
    manifest_rows: list[dict[str, Any]] = []
    for _, pilot in pilot_rows.iterrows():
        image_id = str(pilot["image_id"])
        alignment = alignment_by_image.get(image_id, {})
        manifest_rows.append(
            {
                "image_id": image_id,
                "pair_id": pilot["pair_id"],
                "round1_review_package_dir": pilot.get("review_package_dir", ""),
                "round1_contact_sheet_path": pilot.get("contact_sheet_path", ""),
                "round1_superpixel_overlay_path": pilot.get("superpixel_overlay_path", ""),
                "round1_segment_boundary_overlay_path": pilot.get("segment_boundary_overlay_path", ""),
                "round1_segment_id_map_path": pilot.get("segment_id_map_path", ""),
                "round1_segment_summary_path": pilot.get("segment_summary_path", ""),
                "round1_annotation_template_path": pilot.get("annotation_template_path", ""),
                "round1_1_alignment_review_dir": alignment.get("alignment_review_dir", ""),
                "round1_1_alignment_contact_sheet_path": alignment.get("contact_sheet_path", ""),
                "git_tracking_note": (
                    "PNG review artifacts are local ignored outputs; XLSX/MD manifests are small "
                    "project records that can be tracked."
                ),
            }
        )
    write_rows_xlsx(
        ROUND1_LOCAL_OUTPUTS_MANIFEST_XLSX,
        manifest_rows,
        [
            "image_id",
            "pair_id",
            "round1_review_package_dir",
            "round1_contact_sheet_path",
            "round1_superpixel_overlay_path",
            "round1_segment_boundary_overlay_path",
            "round1_segment_id_map_path",
            "round1_segment_summary_path",
            "round1_annotation_template_path",
            "round1_1_alignment_review_dir",
            "round1_1_alignment_contact_sheet_path",
            "git_tracking_note",
        ],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    if not ALIGNMENT_SUMMARY_XLSX.exists():
        raise FileNotFoundError(
            f"Missing {relative_posix(ALIGNMENT_SUMMARY_XLSX)}; run scripts/part_b/b05_refine_vt_alignment.py first."
        )

    rows = read_table(ALIGNMENT_SUMMARY_XLSX, dtype=str).fillna("")
    generated: list[dict[str, Any]] = []
    for _, row in rows.iterrows():
        result = generate_pair_review(row)
        generated.append(result)
        print(f"Wrote review figures for {result['image_id']}: {result['contact_sheet_path']}")

    write_round1_local_outputs_manifest(rows)
    write_summary_md(rows, generated)
    print(f"Wrote {relative_posix(ROUND1_LOCAL_OUTPUTS_MANIFEST_XLSX)}")
    print(f"Wrote {relative_posix(SUMMARY_MD)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
