"""Reusable normal Part C adapter around the preserved reviewed SLIC workflow."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from PIL import Image, ImageOps

from scripts.part_b.b05_refine_vt_alignment import crop_for_alignment

from .legacy_loader import load_numbered_script
from .part_c_review_gui import SuperpixelReviewController, run_review_gui_subprocess
from .result_index import sha256_file


@dataclass(slots=True)
class PartCResult:
    labels: np.ndarray
    known_mask: np.ndarray
    shadow_mask: np.ndarray
    review_artifact_path: Path
    segment_labels_path: Path
    visible_roi_path: Path
    review_metadata: dict[str, Any]


def prepare_part_c_review(
    *,
    image_id: str,
    pair_id: str,
    visible_path: Path,
    thermal_path: Path,
    accepted_crop: list[int],
    output_directory: Path,
    class_mapping: dict[int, str],
) -> SuperpixelReviewController:
    if len(accepted_crop) != 4:
        raise ValueError("Normal Part C requires the final accepted Part B crop.")
    output_directory.mkdir(parents=True, exist_ok=True)
    with Image.open(visible_path) as source:
        visible = ImageOps.exif_transpose(source).convert("RGB")
    with Image.open(thermal_path) as source:
        thermal = ImageOps.exif_transpose(source).convert("RGB")
    roi = crop_for_alignment(visible, tuple(map(int, accepted_crop)), thermal.size, 0.0)
    roi_path = output_directory / "reviewed_visible_roi.png"
    roi.save(roi_path)
    legacy = load_numbered_script(
        "scripts/part_c/01_prepare_round1_review.py",
        "heat_index_part_c_prepare_v02",
    )
    segments, boundaries, superpixels, color_labels, _ = legacy.run_slic(roi)
    segment_path = output_directory / "superpixel_labels.npy"
    with segment_path.open("wb") as handle:
        np.save(handle, segments.astype(np.int32), allow_pickle=False)
    boundaries.save(output_directory / "superpixel_boundaries.png")
    superpixels.save(output_directory / "superpixel_prefill_regions.png")
    color_labels.save(output_directory / "superpixel_id_colors.png")
    rows = legacy.summarize_segments(
        segments,
        legacy.image_to_array01(roi),
        pair_id,
        image_id,
    )
    pd.DataFrame(rows).to_csv(output_directory / "superpixel_suggestions.csv", index=False, encoding="utf-8-sig")
    suggestions = {int(row["segment_id"]): str(row["suggested_class"]) for row in rows}
    return SuperpixelReviewController(
        image_id=image_id,
        segment_labels=segments,
        class_mapping=class_mapping,
        suggestions=suggestions,
        visible_roi_path=roi_path.resolve().as_posix(),
        thermal_path=thermal_path.resolve().as_posix(),
    )


def run_reviewed_part_c(
    *,
    image_id: str,
    pair_id: str,
    visible_path: Path,
    thermal_path: Path,
    accepted_crop: list[int],
    output_directory: Path,
    class_mapping: dict[int, str],
    review_artifact_path: Path | None = None,
    launch_gui: bool = False,
) -> PartCResult | None:
    controller = prepare_part_c_review(
        image_id=image_id,
        pair_id=pair_id,
        visible_path=visible_path,
        thermal_path=thermal_path,
        accepted_crop=accepted_crop,
        output_directory=output_directory,
        class_mapping=class_mapping,
    )
    artifact = review_artifact_path or output_directory / "superpixel_review.json"
    if review_artifact_path and review_artifact_path.is_file():
        controller = SuperpixelReviewController.resume(
            review_artifact_path,
            segment_labels=controller.segment_labels,
            expected_image_id=image_id,
        )
    if launch_gui:
        run_review_gui_subprocess(controller, artifact, output_directory / "superpixel_labels.npy")
    if not artifact.is_file():
        controller.save_draft(artifact)
        return None
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    if str(payload.get("review_status")) == "cancelled":
        return None
    if str(payload.get("review_status")) != "accepted":
        return None
    controller = SuperpixelReviewController.resume(
        artifact,
        segment_labels=controller.segment_labels,
        expected_image_id=image_id,
    )
    labels, known, shadow = controller.generate_masks()
    payload["artifact_sha256"] = sha256_file(artifact)
    return PartCResult(
        labels=labels,
        known_mask=known,
        shadow_mask=shadow,
        review_artifact_path=artifact,
        segment_labels_path=output_directory / "superpixel_labels.npy",
        visible_roi_path=Path(controller.visible_roi_path),
        review_metadata=payload,
    )


def load_reviewed_label_override(
    *,
    labels_path: Path,
    manifest_path: Path,
    image_id: str,
    expected_shape: tuple[int, int],
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Compatibility override that rejects an unaudited bare label NPY."""
    if not manifest_path.is_file():
        raise ValueError("Normal Part C label overrides require a companion review manifest.")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    required = {"image_id", "dimensions", "class_mapping", "review_status", "reviewer", "artifact_sha256"}
    missing = required.difference(payload)
    if missing:
        raise ValueError(f"Part C review manifest is missing fields: {sorted(missing)}")
    if str(payload["image_id"]) != image_id or list(payload["dimensions"]) != list(expected_shape):
        raise ValueError("Part C label override identity or dimensions do not match.")
    if str(payload["review_status"]) != "accepted":
        raise ValueError("Part C label override has not been accepted.")
    if sha256_file(labels_path) != str(payload["artifact_sha256"]):
        raise ValueError("Part C label override hash does not match its review manifest.")
    labels = np.load(labels_path, allow_pickle=False).astype(np.int16)
    if labels.shape != expected_shape:
        raise ValueError("Part C label override does not match the native thermal grid.")
    known = ~np.isin(labels, [0, 9, -1])
    canonical = labels.copy()
    canonical[~known] = -1
    return canonical, known, payload
