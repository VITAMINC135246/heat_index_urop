"""Explainable Part B0 visible/thermal content-correspondence triage."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageOps

from scripts.part_b.b05_refine_vt_alignment import candidate_score, crop_transform_matrix, edge_bundle

from .models import ContentTriageState, ManualReviewStatus, PartB0Result


DEFAULT_THRESHOLDS: dict[str, float] = {
    "match_score": 0.61,
    "mismatch_score": 0.34,
    "minimum_margin": 0.025,
    "minimum_texture": 0.012,
    "minimum_edge_overlap_for_match": 0.18,
}
ALGORITHM_VERSION = "part-b0-structural-ensemble-0.2.0"


def _normalized_mutual_information(a: np.ndarray, b: np.ndarray, bins: int = 32) -> float:
    histogram, _, _ = np.histogram2d(a.ravel(), b.ravel(), bins=bins, range=((0, 1), (0, 1)))
    if histogram.sum() <= 0:
        return 0.0
    joint = histogram / histogram.sum()
    pa = joint.sum(axis=1)
    pb = joint.sum(axis=0)
    nz = joint > 0
    denom = pa[:, None] * pb[None, :]
    mi = float(np.sum(joint[nz] * np.log(joint[nz] / denom[nz])))
    ha = float(-np.sum(pa[pa > 0] * np.log(pa[pa > 0])))
    hb = float(-np.sum(pb[pb > 0] * np.log(pb[pb > 0])))
    return float(np.clip(2.0 * mi / max(ha + hb, 1e-12), 0.0, 1.0))


def _phase_response(a: np.ndarray, b: np.ndarray) -> float:
    try:
        import cv2

        _shift, response = cv2.phaseCorrelate(a.astype(np.float32), b.astype(np.float32))
        return float(np.clip(response, 0.0, 1.0))
    except Exception:
        return 0.0


def _candidate_boxes(visible_size: tuple[int, int], aspect: float) -> list[tuple[int, int, int, int]]:
    width, height = visible_size
    boxes: set[tuple[int, int, int, int]] = set()
    for fraction in (0.35, 0.50, 0.60, 0.70, 0.90, 1.0):
        crop_width = max(2, int(round(width * fraction)))
        crop_height = max(2, int(round(crop_width / aspect)))
        if crop_height > height:
            crop_height = max(2, int(round(height * fraction)))
            crop_width = max(2, int(round(crop_height * aspect)))
        crop_width = min(width, crop_width)
        crop_height = min(height, crop_height)
        for y_fraction in (0.10, 0.30, 0.45, 0.70, 0.90):
            for x_fraction in (0.10, 0.30, 0.45, 0.70, 0.90):
                cx, cy = x_fraction * width, y_fraction * height
                x0 = int(round(np.clip(cx - crop_width / 2, 0, width - crop_width)))
                y0 = int(round(np.clip(cy - crop_height / 2, 0, height - crop_height)))
                boxes.add((x0, y0, x0 + crop_width, y0 + crop_height))
    return sorted(boxes)


def _review_image(
    visible: Image.Image,
    thermal: Image.Image,
    crop: tuple[int, int, int, int],
    output_path: Path,
    state: ContentTriageState,
    score: float,
) -> None:
    preview = visible.copy().convert("RGB")
    draw = ImageDraw.Draw(preview)
    line = max(2, round(max(preview.size) / 400))
    draw.rectangle(crop, outline="#ff2d2d", width=line)
    crop_image = visible.crop(crop).resize(thermal.size, Image.Resampling.LANCZOS).convert("RGB")
    thermal_rgb = ImageOps.autocontrast(thermal.convert("L")).convert("RGB")
    tile_width = max(crop_image.width, thermal_rgb.width)
    tile_height = max(crop_image.height, thermal_rgb.height)
    top = preview.copy()
    top.thumbnail((tile_width * 2, tile_height * 2), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (tile_width * 2, top.height + tile_height + 54), "white")
    canvas.paste(top, ((canvas.width - top.width) // 2, 0))
    canvas.paste(crop_image, (0, top.height))
    canvas.paste(thermal_rgb, (tile_width, top.height))
    ImageDraw.Draw(canvas).text((8, canvas.height - 44), f"Part B0 {state.value}; score={score:.3f}; candidate crop (left) / thermal (right)", fill="black")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path)


def triage_content_correspondence(
    *,
    group_id: str,
    image_id: str,
    visible_path: Path,
    thermal_path: Path,
    output_directory: Path,
    thresholds: dict[str, float] | None = None,
) -> PartB0Result:
    configured = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    with Image.open(visible_path) as source:
        visible = ImageOps.exif_transpose(source).convert("RGB")
    with Image.open(thermal_path) as source:
        thermal = ImageOps.exif_transpose(source).convert("RGB")
    aspect = thermal.width / max(thermal.height, 1)
    thermal_features = edge_bundle(ImageOps.autocontrast(thermal.convert("L")).convert("RGB"), (160, 128))
    texture = float(np.std(thermal_features["sobel"]))
    rows: list[dict[str, Any]] = []
    for bbox in _candidate_boxes(visible.size, aspect):
        candidate = visible.crop(bbox).resize((160, 128), Image.Resampling.LANCZOS).convert("RGB")
        features = edge_bundle(candidate, (160, 128))
        base = candidate_score(candidate, thermal_features)
        nmi = _normalized_mutual_information(features["gray"], thermal_features["gray"])
        phase = _phase_response(features["sobel"], thermal_features["sobel"])
        sobel_similarity = max(0.0, float(base["sobel_ncc"]))
        gray_similarity = abs(float(base["gray_ncc"]))
        overall = (
            0.36 * sobel_similarity
            + 0.25 * float(base["edge_overlap"])
            + 0.17 * gray_similarity
            + 0.14 * nmi
            + 0.08 * phase
        )
        rows.append({**base, "nmi": nmi, "phase_response": phase, "overall": float(overall), "bbox": bbox})
    ranked = sorted(rows, key=lambda row: row["overall"], reverse=True)
    best = ranked[0]
    margin = float(best["overall"] - ranked[1]["overall"]) if len(ranked) > 1 else float(best["overall"])
    evidence_count = sum(
        (
            float(best["sobel_ncc"]) >= 0.35,
            float(best["edge_overlap"]) >= configured["minimum_edge_overlap_for_match"],
            float(best["nmi"]) >= 0.22,
            float(best["phase_response"]) >= 0.20,
        )
    )
    warnings: list[str] = []
    reasons: list[str] = []
    if texture < configured["minimum_texture"]:
        state = ContentTriageState.NEEDS_MANUAL_REVIEW
        reasons.append("thermal_structure_too_low_for_automatic_triage")
    elif best["overall"] >= configured["match_score"] and evidence_count >= 2 and margin >= configured["minimum_margin"]:
        state = ContentTriageState.CONTENT_MATCH_CANDIDATE
        reasons.append("multiple_structural_features_support_content_correspondence")
    elif best["overall"] <= configured["mismatch_score"] and evidence_count <= 1:
        state = ContentTriageState.CONTENT_MISMATCH_CANDIDATE
        reasons.append("no_plausible_crop_has_sufficient_structural_support")
    else:
        state = ContentTriageState.NEEDS_MANUAL_REVIEW
        reasons.append("borderline_or_conflicting_cross_modal_evidence")
    if margin < configured["minimum_margin"]:
        warnings.append("multiple_spatial_candidates_have_similar_scores")
        if state == ContentTriageState.CONTENT_MATCH_CANDIDATE:
            state = ContentTriageState.NEEDS_MANUAL_REVIEW
    confidence = "high" if state != ContentTriageState.NEEDS_MANUAL_REVIEW and abs(best["overall"] - configured["match_score"]) > 0.12 else "medium"
    if state == ContentTriageState.NEEDS_MANUAL_REVIEW:
        confidence = "low"
    crop = tuple(int(value) for value in best["bbox"])
    review_path = output_directory / "part_b0_review.png"
    _review_image(visible, thermal, crop, review_path, state, float(best["overall"]))
    result = PartB0Result(
        group_id=group_id,
        image_id=image_id,
        triage_state=state,
        algorithm_version=ALGORITHM_VERSION,
        candidate_crop=list(crop),
        candidate_transform=crop_transform_matrix(crop, thermal.size, 0.0),
        feature_scores={
            "sobel_ncc": float(best["sobel_ncc"]),
            "gray_ncc_absolute": abs(float(best["gray_ncc"])),
            "edge_overlap": float(best["edge_overlap"]),
            "normalized_mutual_information": float(best["nmi"]),
            "phase_response": float(best["phase_response"]),
            "candidate_margin": margin,
            "thermal_texture": texture,
        },
        overall_score=float(best["overall"]),
        thresholds=configured,
        confidence=confidence,
        diagnostic_paths=[review_path.resolve().as_posix()],
        reasons=reasons,
        warnings=warnings,
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    record_path = output_directory / "part_b0.json"
    temporary = record_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(record_path)
    return result


def load_part_b0_reviews(path: Path | None) -> dict[str, ManualReviewStatus]:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("decisions", payload)
    if not isinstance(rows, dict):
        raise ValueError("Part B0 review JSON must be keyed by group_id or image_id.")
    decisions: dict[str, ManualReviewStatus] = {}
    for key, value in rows.items():
        status = value.get("review_status") if isinstance(value, dict) else value
        decisions[str(key)] = ManualReviewStatus(str(status))
    return decisions


def apply_part_b0_review(result: PartB0Result, status: ManualReviewStatus | None) -> PartB0Result:
    return replace(result, manual_review_status=status or ManualReviewStatus.NOT_REVIEWED)
