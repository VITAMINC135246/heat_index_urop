#!/usr/bin/env python3
"""Refine Part B Round 1 V/T alignment for the existing pilot pairs.

This script preserves the Round 1 outputs and creates a Round 1.1 alignment
refinement package. Automatic image matching is treated as diagnostic because
thermal-visible alignment is cross-modal. Manual GCP templates are always
created so uncertain pairs can be corrected without rerunning Part A.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from PIL import Image, ImageOps

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from table_io import read_table, write_rows
from workflow.part_b_review import verified_pilot_decisions

try:
    from scipy import ndimage
    from skimage import feature, filters
except Exception as exc:  # pragma: no cover - dependency guard for user envs
    raise RuntimeError(
        "Part B Round 1.1 alignment refinement requires scipy and scikit-image. "
        "Install project requirements before running this script."
    ) from exc


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PILOT_XLSX = PROJECT_ROOT / "data" / "metadata" / "part_b_pilot_pairs.xlsx"
ALIGNMENT_DIR = PROJECT_ROOT / "outputs" / "part_b" / "alignment_refinement"
SUMMARY_DIR = PROJECT_ROOT / "outputs" / "part_b" / "summaries"
ALIGNMENT_SUMMARY_XLSX = SUMMARY_DIR / "part_b_round1_1_alignment_summary.xlsx"
ALIGNMENT_ATTEMPTS_XLSX = SUMMARY_DIR / "part_b_round1_1_alignment_attempts.xlsx"

SCORE_SIZE = (160, 128)
MANUAL_GCP_COLUMNS = [
    "pair_id",
    "V_x",
    "V_y",
    "T_x",
    "T_y",
    "point_description",
    "include",
    "notes",
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
    return text.strip("_") or "pair"


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


def write_rows_xlsx(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    write_rows(path, rows, columns)


def load_rgb(path: Path) -> Image.Image:
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image)
        image.load()
        if image.mode == "L":
            return ImageOps.autocontrast(image).convert("RGB")
        return image.convert("RGB")


def normalize_gray_array(image: Image.Image, size: tuple[int, int]) -> np.ndarray:
    gray = image.convert("L").resize(size, Image.Resampling.BILINEAR)
    arr = np.asarray(gray, dtype=np.float32) / 255.0
    low, high = np.percentile(arr, [2, 98])
    if high > low:
        arr = np.clip((arr - low) / (high - low), 0.0, 1.0)
    return arr.astype(np.float32)


def edge_bundle(image: Image.Image, size: tuple[int, int]) -> dict[str, np.ndarray]:
    gray = normalize_gray_array(image, size)
    sobel = filters.sobel(gray).astype(np.float32)
    if sobel.max() > 0:
        sobel = sobel / sobel.max()
    edges = feature.canny(gray, sigma=1.4, low_threshold=0.08, high_threshold=0.25)
    return {"gray": gray, "sobel": sobel, "edges": edges}


def ncc(a: np.ndarray, b: np.ndarray) -> float:
    a0 = a.astype(np.float64) - float(np.mean(a))
    b0 = b.astype(np.float64) - float(np.mean(b))
    denom = float(np.sqrt(np.sum(a0 * a0) * np.sum(b0 * b0)))
    if denom <= 1e-12:
        return 0.0
    return float(np.sum(a0 * b0) / denom)


def edge_overlap(a: np.ndarray, b: np.ndarray) -> float:
    if not a.any() or not b.any():
        return 0.0
    a_dilated = ndimage.binary_dilation(a, iterations=2)
    b_dilated = ndimage.binary_dilation(b, iterations=2)
    precision = float(np.logical_and(a, b_dilated).sum()) / float(a.sum())
    recall = float(np.logical_and(b, a_dilated).sum()) / float(b.sum())
    if precision + recall <= 1e-12:
        return 0.0
    return 2.0 * precision * recall / (precision + recall)


def candidate_score(candidate: Image.Image, thermal_features: dict[str, np.ndarray]) -> dict[str, float]:
    visible_features = edge_bundle(candidate, SCORE_SIZE)
    sobel_ncc = ncc(visible_features["sobel"], thermal_features["sobel"])
    gray_ncc = ncc(visible_features["gray"], thermal_features["gray"])
    overlap = edge_overlap(visible_features["edges"], thermal_features["edges"])
    score = (0.55 * sobel_ncc) + (0.15 * gray_ncc) + (0.30 * overlap)
    return {
        "score": float(score),
        "sobel_ncc": float(sobel_ncc),
        "gray_ncc": float(gray_ncc),
        "edge_overlap": float(overlap),
    }


def clamp_bbox(
    x_min: float,
    y_min: float,
    width: float,
    height: float,
    visible_size: tuple[int, int],
) -> tuple[int, int, int, int]:
    image_width, image_height = visible_size
    width = max(1.0, min(float(width), float(image_width)))
    height = max(1.0, min(float(height), float(image_height)))
    x_min = max(0.0, min(float(x_min), float(image_width) - width))
    y_min = max(0.0, min(float(y_min), float(image_height) - height))
    x0 = int(round(x_min))
    y0 = int(round(y_min))
    x1 = int(round(x_min + width))
    y1 = int(round(y_min + height))
    x1 = max(x0 + 1, min(x1, image_width))
    y1 = max(y0 + 1, min(y1, image_height))
    return x0, y0, x1, y1


def bbox_from_adjustment(
    old_bbox: tuple[int, int, int, int],
    dx: float,
    dy: float,
    scale: float,
    visible_size: tuple[int, int],
) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = old_bbox
    width = float(x1 - x0) * scale
    height = float(y1 - y0) * scale
    cx = (x0 + x1) / 2.0 + dx
    cy = (y0 + y1) / 2.0 + dy
    return clamp_bbox(cx - width / 2.0, cy - height / 2.0, width, height, visible_size)


def crop_for_alignment(
    visible: Image.Image,
    bbox: tuple[int, int, int, int],
    output_size: tuple[int, int],
    rotation_deg: float = 0.0,
) -> Image.Image:
    crop = visible.crop(bbox).resize(output_size, Image.Resampling.LANCZOS)
    if abs(rotation_deg) > 1e-6:
        crop = crop.rotate(
            rotation_deg,
            resample=Image.Resampling.BICUBIC,
            expand=False,
            fillcolor=(0, 0, 0),
        )
    return crop.convert("RGB")


def crop_transform_matrix(
    bbox: tuple[int, int, int, int],
    thermal_size: tuple[int, int],
    rotation_deg: float,
) -> list[list[float]]:
    x0, y0, x1, y1 = bbox
    width = float(x1 - x0)
    height = float(y1 - y0)
    tw, th = thermal_size
    sx = tw / width
    sy = th / height
    scale_crop = np.array([[sx, 0.0, -x0 * sx], [0.0, sy, -y0 * sy], [0.0, 0.0, 1.0]])
    theta = math.radians(rotation_deg)
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)
    cx = tw / 2.0
    cy = th / 2.0
    rotate = np.array(
        [
            [cos_t, -sin_t, cx - cos_t * cx + sin_t * cy],
            [sin_t, cos_t, cy - sin_t * cx - cos_t * cy],
            [0.0, 0.0, 1.0],
        ]
    )
    return (rotate @ scale_crop).round(8).tolist()


def blank_gcp_template(pair_id: str) -> list[dict[str, Any]]:
    descriptions = [
        "building corner",
        "roof edge",
        "road or pavement intersection",
        "sharp pavement boundary",
        "stable large object",
        "additional point",
    ]
    return [
        {
            "pair_id": pair_id,
            "V_x": "",
            "V_y": "",
            "T_x": "",
            "T_y": "",
            "point_description": description,
            "include": "",
            "notes": "",
        }
        for description in descriptions
    ]


def read_gcp_points(path: Path, pair_id: str) -> list[tuple[float, float, float, float]]:
    if not path.exists():
        return []
    rows = read_table(path, dtype=str).fillna("")
    if "pair_id" in rows.columns:
        rows = rows.loc[rows["pair_id"].astype(str).eq(pair_id)]
    if "include" in rows.columns:
        rows = rows.loc[rows["include"].astype(str).str.casefold().isin(["yes", "y", "true", "1"])]
    points: list[tuple[float, float, float, float]] = []
    for _, row in rows.iterrows():
        vx = as_float(row.get("V_x"))
        vy = as_float(row.get("V_y"))
        tx = as_float(row.get("T_x"))
        ty = as_float(row.get("T_y"))
        if None not in (vx, vy, tx, ty):
            points.append((float(vx), float(vy), float(tx), float(ty)))
    return points


def fit_affine(points: list[tuple[float, float, float, float]]) -> np.ndarray:
    a_rows: list[list[float]] = []
    b_rows: list[float] = []
    for vx, vy, tx, ty in points:
        a_rows.append([vx, vy, 1.0, 0.0, 0.0, 0.0])
        a_rows.append([0.0, 0.0, 0.0, vx, vy, 1.0])
        b_rows.extend([tx, ty])
    coeffs, *_ = np.linalg.lstsq(np.asarray(a_rows), np.asarray(b_rows), rcond=None)
    return np.array([[coeffs[0], coeffs[1], coeffs[2]], [coeffs[3], coeffs[4], coeffs[5]], [0.0, 0.0, 1.0]])


def fit_homography(points: list[tuple[float, float, float, float]]) -> np.ndarray:
    a_rows: list[list[float]] = []
    for vx, vy, tx, ty in points:
        a_rows.append([-vx, -vy, -1.0, 0.0, 0.0, 0.0, tx * vx, tx * vy, tx])
        a_rows.append([0.0, 0.0, 0.0, -vx, -vy, -1.0, ty * vx, ty * vy, ty])
    _, _, vh = np.linalg.svd(np.asarray(a_rows))
    h = vh[-1].reshape(3, 3)
    if abs(h[2, 2]) > 1e-12:
        h = h / h[2, 2]
    return h


def residual_summary(matrix: np.ndarray, points: list[tuple[float, float, float, float]]) -> dict[str, float]:
    residuals: list[float] = []
    for vx, vy, tx, ty in points:
        pred = matrix @ np.array([vx, vy, 1.0])
        pred = pred[:2] / pred[2]
        residuals.append(float(np.linalg.norm(pred - np.array([tx, ty]))))
    if not residuals:
        return {"mean": math.nan, "max": math.nan, "rmse": math.nan}
    arr = np.asarray(residuals, dtype=np.float64)
    return {"mean": float(arr.mean()), "max": float(arr.max()), "rmse": float(np.sqrt(np.mean(arr * arr)))}


def bbox_from_visible_to_thermal_matrix(
    matrix: np.ndarray,
    thermal_size: tuple[int, int],
    visible_size: tuple[int, int],
) -> tuple[int, int, int, int] | None:
    try:
        inverse = np.linalg.inv(matrix)
    except np.linalg.LinAlgError:
        return None
    tw, th = thermal_size
    corners = np.array([[0.0, 0.0, 1.0], [tw, 0.0, 1.0], [tw, th, 1.0], [0.0, th, 1.0]]).T
    visible_corners = inverse @ corners
    visible_corners = visible_corners[:2, :] / visible_corners[2, :]
    x0 = float(np.nanmin(visible_corners[0]))
    y0 = float(np.nanmin(visible_corners[1]))
    x1 = float(np.nanmax(visible_corners[0]))
    y1 = float(np.nanmax(visible_corners[1]))
    if not all(math.isfinite(v) for v in [x0, y0, x1, y1]):
        return None
    return clamp_bbox(x0, y0, x1 - x0, y1 - y0, visible_size)


def manual_gcp_refinement(
    points: list[tuple[float, float, float, float]],
    old_bbox: tuple[int, int, int, int],
    visible_size: tuple[int, int],
    thermal_size: tuple[int, int],
    allow_homography: bool,
) -> dict[str, Any] | None:
    if not points:
        return None
    old_matrix = np.asarray(crop_transform_matrix(old_bbox, thermal_size, 0.0))
    old_residuals = residual_summary(old_matrix, points)

    if allow_homography and len(points) >= 4:
        matrix = fit_homography(points)
        transform_type = "manual_gcp_homography"
    elif len(points) >= 3:
        matrix = fit_affine(points)
        transform_type = "manual_gcp_affine"
    else:
        diffs = []
        for vx, vy, tx, ty in points:
            pred = old_matrix @ np.array([vx, vy, 1.0])
            pred = pred[:2] / pred[2]
            diffs.append(np.array([tx, ty]) - pred)
        mean_shift = np.mean(np.asarray(diffs), axis=0)
        matrix = old_matrix.copy()
        matrix[0, 2] += float(mean_shift[0])
        matrix[1, 2] += float(mean_shift[1])
        transform_type = "manual_gcp_translation"

    refined_bbox = bbox_from_visible_to_thermal_matrix(matrix, thermal_size, visible_size)
    residuals = residual_summary(matrix, points)
    return {
        "transform_type": transform_type,
        "matrix": matrix,
        "bbox": refined_bbox,
        "old_mean_residual": old_residuals["mean"],
        "mean_residual": residuals["mean"],
        "max_residual": residuals["max"],
        "rmse": residuals["rmse"],
    }


def opencv_is_available() -> bool:
    try:
        import cv2  # type: ignore  # noqa: F401
    except Exception:
        return False
    return True


def blank_opencv_attempt(method: str, reason: str) -> dict[str, Any]:
    return {
        "stage": "opencv",
        "method": method,
        "attempted": "no",
        "status": "skipped",
        "accepted": "no",
        "score": "",
        "score_delta": "",
        "dx_px": "",
        "dy_px": "",
        "scale": "",
        "rotation_deg": "",
        "match_count": "",
        "inlier_count": "",
        "transform_matrix_json": "",
        "reason": reason,
    }


def opencv_candidate_from_shift(
    visible: Image.Image,
    old_bbox: tuple[int, int, int, int],
    thermal_size: tuple[int, int],
    thermal_features: dict[str, np.ndarray],
    old_score: float,
    method: str,
    shift_x_score_px: float,
    shift_y_score_px: float,
    response: float | None,
    visible_to_thermal_matrix: list[list[float]] | None,
    match_count: int | str = "",
    inlier_count: int | str = "",
) -> tuple[dict[str, Any], dict[str, Any]]:
    old_width = old_bbox[2] - old_bbox[0]
    old_height = old_bbox[3] - old_bbox[1]
    scale_x = old_width / float(SCORE_SIZE[0])
    scale_y = old_height / float(SCORE_SIZE[1])
    raw_dx = float(shift_x_score_px) * scale_x
    raw_dy = float(shift_y_score_px) * scale_y

    tested: list[dict[str, Any]] = []
    for sign in [-1.0, 1.0]:
        dx = sign * raw_dx
        dy = sign * raw_dy
        bbox = bbox_from_adjustment(old_bbox, dx, dy, 1.0, visible.size)
        image = crop_for_alignment(visible, bbox, SCORE_SIZE, 0.0)
        metrics = candidate_score(image, thermal_features)
        tested.append(
            {
                "stage": "opencv",
                "method": method,
                "dx_px": float(dx),
                "dy_px": float(dy),
                "scale": 1.0,
                "rotation_deg": 0.0,
                **metrics,
                "bbox": bbox,
                "match_count": match_count,
                "inlier_count": inlier_count,
                "opencv_response": response if response is not None else "",
                "source_transform_matrix_json": json.dumps(visible_to_thermal_matrix or []),
            }
        )

    candidate = max(tested, key=lambda row: row["score"])
    shift_magnitude = math.hypot(float(candidate["dx_px"]), float(candidate["dy_px"]))
    score_delta = float(candidate["score"] - old_score)
    if shift_magnitude > 160.0:
        status = "rejected"
        reason = f"Rejected because inferred shift is too large for local refinement: {shift_magnitude:.1f} px."
    elif score_delta <= 0.0:
        status = "rejected"
        reason = f"Rejected because the OpenCV candidate did not improve the score: delta={score_delta:.6f}."
    else:
        status = "candidate"
        reason = (
            "OpenCV-derived local translation candidate; still requires visual review "
            "because thermal-visible alignment is cross-modal."
        )

    attempt = {
        "stage": "opencv",
        "method": method,
        "attempted": "yes",
        "status": status,
        "accepted": "no",
        "score": format_number(float(candidate["score"])),
        "score_delta": format_number(score_delta),
        "dx_px": format_number(float(candidate["dx_px"])),
        "dy_px": format_number(float(candidate["dy_px"])),
        "scale": 1.0,
        "rotation_deg": 0.0,
        "match_count": match_count,
        "inlier_count": inlier_count,
        "transform_matrix_json": json.dumps(
            crop_transform_matrix(tuple(int(value) for value in candidate["bbox"]), thermal_size, 0.0)
        ),
        "reason": reason,
    }
    return candidate, attempt


def opencv_alignment_candidates(
    visible: Image.Image,
    thermal: Image.Image,
    old_bbox: tuple[int, int, int, int],
    thermal_features: dict[str, np.ndarray],
    old_score: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    methods = ["opencv_phase_correlation", "opencv_ecc_translation", "opencv_orb_feature_matching"]
    if not opencv_is_available():
        reason = "OpenCV cv2 is not installed in the active Python environment."
        return [], [blank_opencv_attempt(method, reason) for method in methods], False

    import cv2  # type: ignore

    candidates: list[dict[str, Any]] = []
    attempts: list[dict[str, Any]] = []
    old_roi = crop_for_alignment(visible, old_bbox, SCORE_SIZE, 0.0)
    visible_features = edge_bundle(old_roi, SCORE_SIZE)
    visible_sobel = visible_features["sobel"].astype(np.float32)
    thermal_sobel = thermal_features["sobel"].astype(np.float32)
    visible_gray = visible_features["gray"].astype(np.float32)
    thermal_gray = thermal_features["gray"].astype(np.float32)

    try:
        shift, response = cv2.phaseCorrelate(visible_sobel, thermal_sobel)
        candidate, attempt = opencv_candidate_from_shift(
            visible,
            old_bbox,
            thermal.size,
            thermal_features,
            old_score,
            "opencv_phase_correlation",
            float(shift[0]),
            float(shift[1]),
            float(response),
            [[1.0, 0.0, float(shift[0])], [0.0, 1.0, float(shift[1])], [0.0, 0.0, 1.0]],
        )
        attempts.append(attempt)
        if attempt["status"] == "candidate":
            candidates.append(candidate)
    except Exception as exc:
        attempts.append(
            {
                **blank_opencv_attempt("opencv_phase_correlation", f"OpenCV phase correlation failed: {exc}"),
                "attempted": "yes",
                "status": "failed",
            }
        )

    try:
        warp = np.eye(2, 3, dtype=np.float32)
        criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 80, 1e-5)
        ecc_score, warp = cv2.findTransformECC(
            thermal_gray,
            visible_gray,
            warp,
            cv2.MOTION_TRANSLATION,
            criteria,
            None,
            5,
        )
        candidate, attempt = opencv_candidate_from_shift(
            visible,
            old_bbox,
            thermal.size,
            thermal_features,
            old_score,
            "opencv_ecc_translation",
            float(warp[0, 2]),
            float(warp[1, 2]),
            float(ecc_score),
            [[1.0, 0.0, float(warp[0, 2])], [0.0, 1.0, float(warp[1, 2])], [0.0, 0.0, 1.0]],
        )
        attempts.append(attempt)
        if attempt["status"] == "candidate":
            candidates.append(candidate)
    except Exception as exc:
        attempts.append(
            {
                **blank_opencv_attempt("opencv_ecc_translation", f"OpenCV ECC translation failed: {exc}"),
                "attempted": "yes",
                "status": "failed",
            }
        )

    try:
        visible_u8 = np.clip(visible_gray * 255.0, 0, 255).astype(np.uint8)
        thermal_u8 = np.clip(thermal_gray * 255.0, 0, 255).astype(np.uint8)
        orb = cv2.ORB_create(nfeatures=800)
        keypoints_v, desc_v = orb.detectAndCompute(visible_u8, None)
        keypoints_t, desc_t = orb.detectAndCompute(thermal_u8, None)
        if desc_v is None or desc_t is None or len(keypoints_v) < 8 or len(keypoints_t) < 8:
            raise ValueError("Not enough ORB descriptors in visible or thermal image.")
        matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        matches = sorted(matcher.match(desc_v, desc_t), key=lambda match: match.distance)
        keep = matches[: min(80, len(matches))]
        src = np.float32([keypoints_v[match.queryIdx].pt for match in keep]).reshape(-1, 1, 2)
        dst = np.float32([keypoints_t[match.trainIdx].pt for match in keep]).reshape(-1, 1, 2)
        affine, inliers = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=5.0)
        if affine is None or inliers is None:
            raise ValueError("RANSAC did not estimate a stable affine transform.")
        inlier_count = int(inliers.ravel().sum())
        match_count = int(len(keep))
        if inlier_count < 8:
            raise ValueError(f"Too few ORB/RANSAC inliers: {inlier_count}.")
        candidate, attempt = opencv_candidate_from_shift(
            visible,
            old_bbox,
            thermal.size,
            thermal_features,
            old_score,
            "opencv_orb_feature_matching",
            float(affine[0, 2]),
            float(affine[1, 2]),
            None,
            [[float(affine[0, 0]), float(affine[0, 1]), float(affine[0, 2])], [float(affine[1, 0]), float(affine[1, 1]), float(affine[1, 2])], [0.0, 0.0, 1.0]],
            match_count=match_count,
            inlier_count=inlier_count,
        )
        attempts.append(attempt)
        if attempt["status"] == "candidate":
            candidates.append(candidate)
    except Exception as exc:
        attempts.append(
            {
                **blank_opencv_attempt("opencv_orb_feature_matching", f"OpenCV ORB feature matching failed or was rejected: {exc}"),
                "attempted": "yes",
                "status": "failed",
            }
        )

    return candidates, attempts, True


def search_alignment(
    visible: Image.Image,
    thermal: Image.Image,
    old_bbox: tuple[int, int, int, int],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], bool]:
    thermal_features = edge_bundle(ImageOps.autocontrast(thermal.convert("L")).convert("RGB"), SCORE_SIZE)
    visible_size = visible.size

    old_candidate = crop_for_alignment(visible, old_bbox, SCORE_SIZE, 0.0)
    old_metrics = candidate_score(old_candidate, thermal_features)
    old_row = {
        "stage": "baseline",
        "method": "metadata_fov_center_crop",
        "dx_px": 0.0,
        "dy_px": 0.0,
        "scale": 1.0,
        "rotation_deg": 0.0,
        **old_metrics,
        "bbox": old_bbox,
    }

    candidates: list[dict[str, Any]] = [old_row]
    opencv_candidates, opencv_attempts, opencv_available = opencv_alignment_candidates(
        visible,
        thermal,
        old_bbox,
        thermal_features,
        float(old_metrics["score"]),
    )
    candidates.extend(opencv_candidates)

    coarse_candidates: list[dict[str, Any]] = []
    coarse_dx = [-80, -40, 0, 40, 80]
    coarse_dy = [-80, -40, 0, 40, 80]
    coarse_scales = [0.98, 1.0, 1.02]
    for dx in coarse_dx:
        for dy in coarse_dy:
            for scale in coarse_scales:
                bbox = bbox_from_adjustment(old_bbox, dx, dy, scale, visible_size)
                image = crop_for_alignment(visible, bbox, SCORE_SIZE, 0.0)
                metrics = candidate_score(image, thermal_features)
                candidate = {
                    "stage": "coarse_grid",
                    "method": "skimage_edge_grid_search",
                    "dx_px": float(dx),
                    "dy_px": float(dy),
                    "scale": float(scale),
                    "rotation_deg": 0.0,
                    **metrics,
                    "bbox": bbox,
                }
                candidates.append(candidate)
                coarse_candidates.append(candidate)

    def add_fine_grid(seed: dict[str, Any], stage: str, method: str) -> None:
        base_dx = float(seed["dx_px"])
        base_dy = float(seed["dy_px"])
        base_scale = float(seed["scale"])
        fine_dx = [base_dx + value for value in [-20, -10, 0, 10, 20]]
        fine_dy = [base_dy + value for value in [-20, -10, 0, 10, 20]]
        fine_scales = [max(0.96, min(1.04, base_scale + value)) for value in [-0.01, 0.0, 0.01]]
        fine_rotations = [-1.0, 0.0, 1.0]
        for dx in fine_dx:
            for dy in fine_dy:
                for scale in fine_scales:
                    for rotation in fine_rotations:
                        bbox = bbox_from_adjustment(old_bbox, dx, dy, scale, visible_size)
                        image = crop_for_alignment(visible, bbox, SCORE_SIZE, rotation)
                        metrics = candidate_score(image, thermal_features)
                        candidates.append(
                            {
                                "stage": stage,
                                "method": method,
                                "dx_px": float(dx),
                                "dy_px": float(dy),
                                "scale": float(scale),
                                "rotation_deg": float(rotation),
                                **metrics,
                                "bbox": bbox,
                            }
                        )

    non_opencv_seed = max([old_row, *coarse_candidates], key=lambda row: row["score"])
    add_fine_grid(non_opencv_seed, "fine_grid", "skimage_edge_grid_search")

    if opencv_candidates:
        opencv_seed = max(opencv_candidates, key=lambda row: row["score"])
        add_fine_grid(
            opencv_seed,
            "fine_grid_opencv_seeded",
            f"skimage_edge_grid_search_seeded_by_{opencv_seed['method']}",
        )

    best = max(candidates, key=lambda row: row["score"])
    best["old_score"] = old_metrics["score"]
    best["score_delta"] = float(best["score"] - old_metrics["score"])
    best["sobel_ncc_delta"] = float(best["sobel_ncc"] - old_metrics["sobel_ncc"])
    best["edge_overlap_delta"] = float(best["edge_overlap"] - old_metrics["edge_overlap"])
    top_rows = sorted(candidates, key=lambda row: row["score"], reverse=True)[:25]
    return best, top_rows, opencv_attempts, opencv_available


def format_number(value: Any, digits: int = 6) -> Any:
    if isinstance(value, float):
        if math.isnan(value):
            return ""
        return round(value, digits)
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-homography",
        action="store_true",
        help="Use manual GCP homography when at least four included points are available.",
    )
    args = parser.parse_args()

    if not PILOT_XLSX.exists():
        raise FileNotFoundError(f"Missing {relative_posix(PILOT_XLSX)}; run Part B Round 1 first.")

    ALIGNMENT_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)

    pilot_rows = read_table(PILOT_XLSX, dtype=str).fillna("")
    verified_decisions = verified_pilot_decisions(PROJECT_ROOT)
    summary_rows: list[dict[str, Any]] = []
    attempt_rows: list[dict[str, Any]] = []

    for _, row in pilot_rows.iterrows():
        pair_id = str(row["pair_id"])
        image_id = str(row["image_id"]) or safe_name(pair_id.split("::")[-1])
        pair_dir = ALIGNMENT_DIR / safe_name(image_id)
        pair_dir.mkdir(parents=True, exist_ok=True)

        visible = load_rgb(resolve_project_path(row["v_path"]))
        thermal = load_rgb(resolve_project_path(row["t_path"]))
        old_bbox = (
            as_int(row["roi_x_min_px"]),
            as_int(row["roi_y_min_px"]),
            as_int(row["roi_x_max_px"]),
            as_int(row["roi_y_max_px"]),
        )

        gcp_template_path = pair_dir / "manual_gcp_template.xlsx"
        if not gcp_template_path.exists():
            write_rows_xlsx(gcp_template_path, blank_gcp_template(pair_id), MANUAL_GCP_COLUMNS)
        gcp_points = read_gcp_points(gcp_template_path, pair_id)

        best, top_candidates, opencv_attempts, opencv_available = search_alignment(visible, thermal, old_bbox)
        old_score = float(best["old_score"])
        score_delta = float(best["score_delta"])
        auto_accepted = score_delta >= 0.015 and score_delta / max(abs(old_score), 1e-6) >= 0.06
        rejection_reason = "" if auto_accepted else "Automatic cross-modal score improvement is too small for acceptance."

        gcp_result = manual_gcp_refinement(gcp_points, old_bbox, visible.size, thermal.size, args.allow_homography)
        if gcp_result is not None and gcp_result.get("bbox") is not None:
            refined_bbox = tuple(int(v) for v in gcp_result["bbox"])
            transform_type = gcp_result["transform_type"]
            transform_matrix = np.asarray(gcp_result["matrix"]).round(8).tolist()
            method_used = transform_type
            confidence = "medium" if len(gcp_points) >= 3 else "low"
            alignment_quality = "acceptable" if len(gcp_points) >= 3 else "poor"
            needs_manual_gcp = "no" if len(gcp_points) >= 3 else "yes"
            notes = "Manual GCP transform is available; inspect residuals and review figures before accepting."
            dx_px = ""
            dy_px = ""
            scale = ""
            rotation = ""
            final_score = ""
            score_delta_out = ""
        else:
            refined_bbox = tuple(int(v) for v in best["bbox"])
            transform_type = "crop_shift_scale_rotate_candidate"
            transform_matrix = crop_transform_matrix(refined_bbox, thermal.size, float(best["rotation_deg"]))
            method_used = f"{best['method']}_from_metadata_fov_center_crop"
            confidence = "low" if not auto_accepted else "medium"
            alignment_quality = "poor" if not auto_accepted else "acceptable"
            needs_manual_gcp = "yes" if not auto_accepted else "no"
            notes = (
                "Automatic result is a review candidate only; visually compare old and refined overlays. "
                + (rejection_reason if rejection_reason else "Manual visual acceptance is still required.")
            )
            dx_px = float(best["dx_px"])
            dy_px = float(best["dy_px"])
            scale = float(best["scale"])
            rotation = float(best["rotation_deg"])
            final_score = float(best["score"])
            score_delta_out = score_delta

        old_matrix = crop_transform_matrix(old_bbox, thermal.size, 0.0)
        verified = verified_decisions.get(image_id)
        manual_review_status = verified.manual_review_status.value if verified else "not_reviewed"
        final_alignment_status = verified.final_alignment_status.value if verified else "indeterminate"
        scene_correspondence = verified.scene_correspondence.value if verified else "indeterminate"
        coverage_class = verified.coverage_class.value if verified else "indeterminate"
        routing_decision = "normal_visible_thermal" if final_alignment_status == "accepted" else "requires_manual_review"
        summary = {
            "pair_id": pair_id,
            "image_id": image_id,
            "v_path": row["v_path"],
            "t_path": row["t_path"],
            "old_roi_x_min_px": old_bbox[0],
            "old_roi_y_min_px": old_bbox[1],
            "old_roi_x_max_px": old_bbox[2],
            "old_roi_y_max_px": old_bbox[3],
            "old_roi_width_px": old_bbox[2] - old_bbox[0],
            "old_roi_height_px": old_bbox[3] - old_bbox[1],
            "refined_roi_x_min_px": refined_bbox[0],
            "refined_roi_y_min_px": refined_bbox[1],
            "refined_roi_x_max_px": refined_bbox[2],
            "refined_roi_y_max_px": refined_bbox[3],
            "refined_roi_width_px": refined_bbox[2] - refined_bbox[0],
            "refined_roi_height_px": refined_bbox[3] - refined_bbox[1],
            "dx_px": dx_px,
            "dy_px": dy_px,
            "scale": scale,
            "rotation_deg": rotation,
            "final_transform_type": transform_type,
            "final_transform_matrix_json": json.dumps(transform_matrix),
            "old_transform_matrix_json": json.dumps(old_matrix),
            "method_used": method_used,
            "opencv_available": "yes" if opencv_available else "no",
            "match_count": best.get("match_count", ""),
            "inlier_count": best.get("inlier_count", ""),
            "original_alignment_score": format_number(old_score),
            "refined_alignment_score": format_number(final_score) if final_score != "" else "",
            "score_delta": format_number(score_delta_out) if score_delta_out != "" else "",
            "auto_result_accepted": "yes" if auto_accepted else "no",
            "auto_candidate_status": "available",
            "auto_rejection_reason": rejection_reason,
            "confidence": confidence,
            "scene_correspondence": scene_correspondence,
            "coverage_class": coverage_class,
            "manual_review_status": manual_review_status,
            "final_alignment_status": final_alignment_status,
            "routing_decision": routing_decision,
            "alignment_quality": alignment_quality,
            "needs_manual_gcp": needs_manual_gcp,
            "manual_gcp_template_path": relative_posix(gcp_template_path),
            "manual_gcp_point_count": len(gcp_points),
            "manual_gcp_mean_residual_px": format_number(gcp_result["mean_residual"]) if gcp_result else "",
            "manual_gcp_max_residual_px": format_number(gcp_result["max_residual"]) if gcp_result else "",
            "manual_gcp_rmse_px": format_number(gcp_result["rmse"]) if gcp_result else "",
            "alignment_review_dir": relative_posix(pair_dir),
            "old_roi_box_path": relative_posix(pair_dir / "01_old_roi_box_full_visible.png"),
            "refined_roi_box_path": relative_posix(pair_dir / "02_refined_roi_box_full_visible.png"),
            "old_blend_overlay_path": relative_posix(pair_dir / "03_old_vt_alpha_blend_overlay.png"),
            "refined_blend_overlay_path": relative_posix(pair_dir / "04_refined_vt_alpha_blend_overlay.png"),
            "old_side_by_side_path": relative_posix(pair_dir / "05_old_side_by_side_v_roi_and_t.png"),
            "refined_side_by_side_path": relative_posix(pair_dir / "06_refined_side_by_side_v_roi_and_t.png"),
            "old_edge_overlay_path": relative_posix(pair_dir / "07_edge_overlay_before_refinement.png"),
            "refined_edge_overlay_path": relative_posix(pair_dir / "08_edge_overlay_after_refinement.png"),
            "manual_gcp_side_by_side_path": relative_posix(pair_dir / "09_manual_gcp_side_by_side.png"),
            "contact_sheet_path": relative_posix(pair_dir / "10_alignment_comparison_contact_sheet.png"),
            "notes": notes + (
                " Final acceptance is supported by existing reviewed downstream pilot evidence."
                if verified else " Automatic candidate status is not final acceptance."
            ),
        }
        summary_rows.append(summary)

        for attempt in opencv_attempts:
            if (
                auto_accepted
                and attempt.get("status") == "candidate"
                and attempt.get("method") == best.get("method")
                and as_float(attempt.get("dx_px")) == format_number(float(best.get("dx_px", 0.0)))
                and as_float(attempt.get("dy_px")) == format_number(float(best.get("dy_px", 0.0)))
            ):
                attempt["accepted"] = "yes"
                attempt["status"] = "selected"
            elif (
                auto_accepted
                and attempt.get("status") == "candidate"
                and best.get("stage") == "fine_grid_opencv_seeded"
                and str(attempt.get("method")) in str(best.get("method"))
            ):
                attempt["status"] = "used_as_seed"
                attempt["reason"] = (
                    "OpenCV translation was used to seed the final fine-grid crop search; "
                    "the final accepted candidate is the refined fine-grid result."
                )
            attempt_rows.append({"pair_id": pair_id, "image_id": image_id, **attempt})
        for candidate in top_candidates:
            if candidate["stage"] == "opencv":
                continue
            bbox = tuple(int(v) for v in candidate["bbox"])
            matrix = crop_transform_matrix(bbox, thermal.size, float(candidate["rotation_deg"]))
            accepted = (
                candidate["stage"] == best["stage"]
                and candidate["dx_px"] == best["dx_px"]
                and candidate["dy_px"] == best["dy_px"]
                and candidate["scale"] == best["scale"]
                and candidate["rotation_deg"] == best["rotation_deg"]
            )
            attempt_rows.append(
                {
                    "pair_id": pair_id,
                    "image_id": image_id,
                    "stage": candidate["stage"],
                    "method": candidate["method"],
                    "attempted": "yes",
                    "status": "candidate",
                    "accepted": "yes" if accepted and auto_accepted else "no",
                    "score": format_number(candidate["score"]),
                    "score_delta": format_number(float(candidate["score"]) - old_score),
                    "dx_px": candidate["dx_px"],
                    "dy_px": candidate["dy_px"],
                    "scale": candidate["scale"],
                    "rotation_deg": candidate["rotation_deg"],
                    "match_count": candidate.get("match_count", ""),
                    "inlier_count": candidate.get("inlier_count", ""),
                    "transform_matrix_json": json.dumps(matrix),
                    "reason": "Top local edge/gradient search candidate for manual review.",
                }
            )

        write_rows_xlsx(
            pair_dir / "top_alignment_candidates.xlsx",
            [
                {
                    "rank": rank,
                    "stage": candidate["stage"],
                    "method": candidate["method"],
                    "score": format_number(candidate["score"]),
                    "score_delta": format_number(float(candidate["score"]) - old_score),
                    "dx_px": candidate["dx_px"],
                    "dy_px": candidate["dy_px"],
                    "scale": candidate["scale"],
                    "rotation_deg": candidate["rotation_deg"],
                    "match_count": candidate.get("match_count", ""),
                    "inlier_count": candidate.get("inlier_count", ""),
                    "bbox": ",".join(str(v) for v in candidate["bbox"]),
                }
                for rank, candidate in enumerate(top_candidates, start=1)
            ],
            [
                "rank",
                "stage",
                "method",
                "score",
                "score_delta",
                "dx_px",
                "dy_px",
                "scale",
                "rotation_deg",
                "match_count",
                "inlier_count",
                "bbox",
            ],
        )

        print(
            f"{image_id}: old score {old_score:.4f}, best {float(best['score']):.4f}, "
            f"delta {score_delta:.4f}, quality {alignment_quality}, manual_gcp {needs_manual_gcp}"
        )

    summary_columns = [
        "pair_id",
        "image_id",
        "v_path",
        "t_path",
        "old_roi_x_min_px",
        "old_roi_y_min_px",
        "old_roi_x_max_px",
        "old_roi_y_max_px",
        "old_roi_width_px",
        "old_roi_height_px",
        "refined_roi_x_min_px",
        "refined_roi_y_min_px",
        "refined_roi_x_max_px",
        "refined_roi_y_max_px",
        "refined_roi_width_px",
        "refined_roi_height_px",
        "dx_px",
        "dy_px",
        "scale",
        "rotation_deg",
        "final_transform_type",
        "final_transform_matrix_json",
        "old_transform_matrix_json",
        "method_used",
        "opencv_available",
        "match_count",
        "inlier_count",
        "original_alignment_score",
        "refined_alignment_score",
        "score_delta",
        "auto_result_accepted",
        "auto_candidate_status",
        "auto_rejection_reason",
        "confidence",
        "scene_correspondence",
        "coverage_class",
        "manual_review_status",
        "final_alignment_status",
        "routing_decision",
        "alignment_quality",
        "needs_manual_gcp",
        "manual_gcp_template_path",
        "manual_gcp_point_count",
        "manual_gcp_mean_residual_px",
        "manual_gcp_max_residual_px",
        "manual_gcp_rmse_px",
        "alignment_review_dir",
        "old_roi_box_path",
        "refined_roi_box_path",
        "old_blend_overlay_path",
        "refined_blend_overlay_path",
        "old_side_by_side_path",
        "refined_side_by_side_path",
        "old_edge_overlay_path",
        "refined_edge_overlay_path",
        "manual_gcp_side_by_side_path",
        "contact_sheet_path",
        "notes",
    ]
    attempt_columns = [
        "pair_id",
        "image_id",
        "stage",
        "method",
        "attempted",
        "status",
        "accepted",
        "score",
        "score_delta",
        "dx_px",
        "dy_px",
        "scale",
        "rotation_deg",
        "match_count",
        "inlier_count",
        "transform_matrix_json",
        "reason",
    ]
    write_rows_xlsx(ALIGNMENT_SUMMARY_XLSX, summary_rows, summary_columns)
    write_rows_xlsx(ALIGNMENT_ATTEMPTS_XLSX, attempt_rows, attempt_columns)
    print(f"Wrote {relative_posix(ALIGNMENT_SUMMARY_XLSX)}")
    print(f"Wrote {relative_posix(ALIGNMENT_ATTEMPTS_XLSX)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
