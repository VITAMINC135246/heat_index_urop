"""Reusable adapter around the reviewed Part B alignment and review functions."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd
from PIL import Image, ImageOps

PART_B_DIR = Path(__file__).resolve().parents[1] / "part_b"
if str(PART_B_DIR) not in sys.path:
    sys.path.insert(0, str(PART_B_DIR))

from scripts.part_b.b05_refine_vt_alignment import (
    crop_transform_matrix,
    manual_gcp_refinement,
    search_alignment,
)
from scripts.part_b.b06_generate_alignment_refinement_review import generate_pair_review

from .models import (
    AutoCandidateStatus,
    CoverageClass,
    ManualReviewStatus,
    PartB0Result,
    PartBDecision,
    SceneCorrespondence,
)
from .routing import finalize_part_b


def _atomic_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)
    return path


def run_full_part_b(
    *,
    group_id: str,
    image_id: str,
    visible_path: Path,
    thermal_path: Path,
    part_b0: PartB0Result,
    output_directory: Path,
    review_decision: PartBDecision | None = None,
    gcp_points: Sequence[Sequence[float]] | None = None,
    allow_homography: bool = False,
) -> PartBDecision:
    """Generate candidates/evidence; only ``review_decision`` may accept alignment."""
    if part_b0.manual_review_status not in {ManualReviewStatus.ACCEPTED, ManualReviewStatus.NOT_REVIEWED}:
        raise ValueError("Full Part B cannot run after a rejected or cancelled Part B0 review.")
    with Image.open(visible_path) as source:
        visible = ImageOps.exif_transpose(source).convert("RGB")
    with Image.open(thermal_path) as source:
        thermal = ImageOps.exif_transpose(source).convert("RGB")
    if len(part_b0.candidate_crop) != 4:
        raise ValueError("Full Part B requires the Part B0 candidate crop.")
    old_bbox = tuple(int(value) for value in part_b0.candidate_crop)
    best, top_candidates, opencv_attempts, opencv_available = search_alignment(visible, thermal, old_bbox)
    points = [tuple(map(float, point)) for point in (gcp_points or [])]
    if any(len(point) != 4 for point in points):
        raise ValueError("Every GCP must contain V_x, V_y, T_x, and T_y.")
    gcp = manual_gcp_refinement(points, old_bbox, visible.size, thermal.size, allow_homography)
    if gcp is not None and gcp.get("bbox") is not None:
        refined_bbox = tuple(int(value) for value in gcp["bbox"])
        transform = np.asarray(gcp["matrix"], dtype=float).round(8).tolist()
        transform_type = str(gcp["transform_type"])
        gcp_status = "available"
    else:
        refined_bbox = tuple(int(value) for value in best["bbox"])
        transform = crop_transform_matrix(refined_bbox, thermal.size, float(best["rotation_deg"]))
        transform_type = "crop_shift_scale_rotate_candidate"
        gcp_status = "not_supplied" if not points else "insufficient_or_failed"
    output_directory.mkdir(parents=True, exist_ok=True)
    transform_path = _atomic_json(
        output_directory / "candidate_transform.json",
        {
            "transform_type": transform_type,
            "visible_to_thermal_matrix": transform,
            "old_bbox": list(old_bbox),
            "refined_bbox": list(refined_bbox),
            "thermal_size": list(thermal.size),
            "visible_size": list(visible.size),
        },
    )
    review_path = output_directory / "alignment_review_contact_sheet.png"
    row = pd.Series(
        {
            "image_id": image_id,
            "v_path": visible_path.resolve().as_posix(),
            "t_path": thermal_path.resolve().as_posix(),
            "old_roi_x_min_px": old_bbox[0],
            "old_roi_y_min_px": old_bbox[1],
            "old_roi_x_max_px": old_bbox[2],
            "old_roi_y_max_px": old_bbox[3],
            "refined_roi_x_min_px": refined_bbox[0],
            "refined_roi_y_min_px": refined_bbox[1],
            "refined_roi_x_max_px": refined_bbox[2],
            "refined_roi_y_max_px": refined_bbox[3],
            "rotation_deg": float(best.get("rotation_deg", 0.0)),
            "alignment_quality": "candidate_only",
            "needs_manual_gcp": "no" if gcp is not None else "yes",
            "score_delta": float(best.get("score_delta", 0.0)),
            "old_roi_box_path": (output_directory / "old_roi_box.png").as_posix(),
            "refined_roi_box_path": (output_directory / "refined_roi_box.png").as_posix(),
            "old_blend_overlay_path": (output_directory / "old_blend.png").as_posix(),
            "refined_blend_overlay_path": (output_directory / "refined_blend.png").as_posix(),
            "old_side_by_side_path": (output_directory / "old_side_by_side.png").as_posix(),
            "refined_side_by_side_path": (output_directory / "refined_side_by_side.png").as_posix(),
            "old_edge_overlay_path": (output_directory / "old_edges.png").as_posix(),
            "refined_edge_overlay_path": (output_directory / "refined_edges.png").as_posix(),
            "manual_gcp_side_by_side_path": (output_directory / "gcp_reference.png").as_posix(),
            "contact_sheet_path": review_path.as_posix(),
        }
    )
    generate_pair_review(row)
    supplied = review_decision or PartBDecision(group_id=group_id)
    decision = PartBDecision(
        group_id=group_id,
        filename_time_pairing=supplied.filename_time_pairing,
        part_b0_state=part_b0.triage_state,
        scene_correspondence=supplied.scene_correspondence,
        coverage_class=supplied.coverage_class,
        auto_candidate_status=AutoCandidateStatus.AVAILABLE,
        gcp_status=gcp_status,
        manual_review_status=supplied.manual_review_status,
        candidate_transform_path=transform_path.resolve().as_posix(),
        review_evidence_path=review_path.resolve().as_posix(),
        candidate_transform=transform,
        candidate_crop=list(refined_bbox),
        candidate_scores={
            "selected": {
                key: best.get(key)
                for key in ("method", "stage", "score", "old_score", "score_delta", "sobel_ncc", "gray_ncc", "edge_overlap")
            },
            "top_candidates": [
                {key: value for key, value in candidate.items() if key != "bbox"} | {"bbox": list(candidate["bbox"])}
                for candidate in top_candidates
            ],
            "opencv_attempts": opencv_attempts,
            "opencv_available": opencv_available,
        },
        gcp_evidence={
            "status": gcp_status,
            "point_count": len(points),
            "transform_type": transform_type,
            "mean_residual_px": None if gcp is None else gcp.get("mean_residual"),
            "max_residual_px": None if gcp is None else gcp.get("max_residual"),
            "rmse_px": None if gcp is None else gcp.get("rmse"),
        },
        notes=supplied.notes or "Automatic alignment is candidate evidence only; final manual review controls routing.",
    )
    decision = finalize_part_b(decision)
    _atomic_json(output_directory / "part_b.json", decision.to_dict())
    return decision


def decision_from_review_payload(group_id: str, payload: dict[str, Any]) -> PartBDecision:
    return PartBDecision(
        group_id=group_id,
        filename_time_pairing=str(payload.get("filename_time_pairing", "indeterminate")),
        scene_correspondence=SceneCorrespondence(str(payload.get("scene_correspondence", "indeterminate"))),
        coverage_class=CoverageClass(str(payload.get("coverage_class", "indeterminate"))),
        manual_review_status=ManualReviewStatus(str(payload.get("manual_review_status", "not_reviewed"))),
        notes=str(payload.get("notes", "")),
    )
