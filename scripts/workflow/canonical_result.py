"""Build, load, and validate canonical per-thermal-image results."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .models import (
    ArtifactReference,
    CanonicalManifest,
    CoverageClass,
    ManualReviewStatus,
    ProcessingRoute,
    ProcessingStatus,
    QAStatus,
    SceneCorrespondence,
    SourceMethod,
)
from .result_index import sha256_file


UNKNOWN_LABEL_ID = -1


def _artifact(path: Path, array: np.ndarray | None = None) -> ArtifactReference:
    return ArtifactReference(
        path=path.name,
        sha256=sha256_file(path),
        dtype=str(array.dtype) if array is not None else "",
        shape=list(array.shape) if array is not None else [],
    )


def validate_label_layers(
    temperature: np.ndarray,
    labels: np.ndarray,
    known_mask: np.ndarray,
    shadow_mask: np.ndarray | None = None,
) -> None:
    if temperature.ndim != 2:
        raise ValueError("Temperature matrix must be two-dimensional.")
    if labels.shape != temperature.shape or known_mask.shape != temperature.shape:
        raise ValueError("Temperature, label, and known-mask shapes must match.")
    if known_mask.dtype != np.bool_:
        raise ValueError("known_mask must have boolean dtype.")
    if shadow_mask is not None and shadow_mask.shape != temperature.shape:
        raise ValueError("Optional shadow-mask shape must match the temperature grid.")
    if np.any(labels[~known_mask] != UNKNOWN_LABEL_ID):
        raise ValueError("Unknown pixels must use the non-physical storage sentinel -1.")
    if np.any(labels[known_mask] == UNKNOWN_LABEL_ID):
        raise ValueError("Known pixels must have a surface-cover class ID.")


def pixel_frame(
    *,
    image_id: str,
    group_id: str,
    pair_id: str,
    dataset_id: str,
    temperature: np.ndarray,
    labels: np.ndarray,
    known_mask: np.ndarray,
    source_method: SourceMethod,
    review_status: ManualReviewStatus,
    surface_cover_names: dict[int, str] | None = None,
    target_name: str = "",
    shadow_mask: np.ndarray | None = None,
) -> pd.DataFrame:
    validate_label_layers(temperature, labels, known_mask, shadow_mask)
    height, width = temperature.shape
    rows = np.repeat(np.arange(height, dtype=np.int32), width)
    cols = np.tile(np.arange(width, dtype=np.int32), height)
    values = temperature.astype(np.float32, copy=False).ravel(order="C")
    finite = np.isfinite(values)
    known = known_mask.ravel(order="C")
    label_ids = labels.astype(np.int16, copy=False).ravel(order="C")
    eligible = finite & known & (review_status == ManualReviewStatus.ACCEPTED)
    exclusion = np.full(values.size, "", dtype=object)
    exclusion[~finite] = "non_finite_temperature"
    exclusion[finite & ~known] = "label_unknown"
    if review_status != ManualReviewStatus.ACCEPTED:
        exclusion[finite & known] = "annotation_not_accepted"
    names = surface_cover_names or {}
    label_names = np.array([names.get(int(value), "") if is_known else "" for value, is_known in zip(label_ids, known)], dtype=object)
    frame = pd.DataFrame(
        {
            "image_id": image_id,
            "group_id": group_id,
            "pair_id": pair_id,
            "dataset_id": dataset_id,
            "thermal_row": rows,
            "thermal_col": cols,
            "pixel_x": cols,
            "pixel_y": rows,
            "pixel_uid": [f"{image_id}__r{row:04d}_c{col:04d}" for row, col in zip(rows, cols)],
            "temperature_c": values,
            "temperature_is_finite": finite,
            "source_method": source_method.value,
            "label_provenance": source_method.value,
            "label_known": known,
            "surface_cover_class_id": label_ids,
            "surface_cover_class": label_names,
            "analysis_eligible": eligible,
            "exclusion_reason": exclusion,
            "target_name": target_name,
            "annotation_review_status": review_status.value,
        }
    )
    if shadow_mask is None:
        frame["shadow_flag"] = pd.array([pd.NA] * len(frame), dtype="Int8")
        frame["shadow_valid"] = False
    else:
        frame["shadow_flag"] = pd.array(shadow_mask.astype(np.int8).ravel(order="C"), dtype="Int8")
        frame["shadow_valid"] = True
    return frame


def write_canonical_result(
    *,
    output_root: Path,
    image_id: str,
    group_id: str,
    pair_id: str,
    dataset_id: str,
    visible_path: str,
    thermal_path: str,
    temperature: np.ndarray,
    labels: np.ndarray,
    known_mask: np.ndarray,
    processing_route: ProcessingRoute,
    source_method: SourceMethod,
    review_status: ManualReviewStatus,
    qa_status: QAStatus,
    configuration_hash: str,
    source_file_hashes: dict[str, str],
    surface_cover_names: dict[int, str] | None = None,
    surface_cover_class_id: int | None = None,
    surface_cover_category: str | None = None,
    target_name: str = "",
    polygon_coordinates: list[list[float]] | None = None,
    reviewer_confidence: str = "",
    shadow_mask: np.ndarray | None = None,
    temperature_metadata: dict[str, Any] | None = None,
    validation_status: str = "",
    scene_correspondence: str = SceneCorrespondence.INDETERMINATE.value,
    coverage_class: str = CoverageClass.INDETERMINATE.value,
    exclusions: list[str] | None = None,
    notes: str = "",
    write_pixels_parquet: bool = True,
) -> tuple[CanonicalManifest, Path]:
    temperature = np.asarray(temperature, dtype=np.float32)
    labels = np.asarray(labels, dtype=np.int16)
    known_mask = np.asarray(known_mask, dtype=bool)
    shadow = np.asarray(shadow_mask) if shadow_mask is not None else None
    validate_label_layers(temperature, labels, known_mask, shadow)
    if processing_route == ProcessingRoute.THERMAL_POLYGON:
        if surface_cover_class_id is None or not surface_cover_category:
            raise ValueError("Polygon results require a selected surface-cover class ID and category.")
        if np.any(labels[known_mask] != int(surface_cover_class_id)):
            raise ValueError("Every known polygon pixel must receive the selected surface-cover class.")
    directory = output_root / image_id
    directory.mkdir(parents=True, exist_ok=True)
    temperature_path = directory / "temperature.npy"
    labels_path = directory / "surface_cover_labels.npy"
    known_path = directory / "known_mask.npy"
    np.save(temperature_path, temperature)
    np.save(labels_path, labels)
    np.save(known_path, known_mask)
    artifacts: dict[str, ArtifactReference] = {
        "temperature": _artifact(temperature_path, temperature),
        "surface_cover_labels": _artifact(labels_path, labels),
        "known_mask": _artifact(known_path, known_mask),
    }
    if shadow is not None:
        shadow_path = directory / "shadow_mask.npy"
        np.save(shadow_path, shadow.astype(np.int8))
        artifacts["shadow_mask"] = _artifact(shadow_path, shadow.astype(np.int8))
    frame = pixel_frame(
        image_id=image_id,
        group_id=group_id,
        pair_id=pair_id,
        dataset_id=dataset_id,
        temperature=temperature,
        labels=labels,
        known_mask=known_mask,
        source_method=source_method,
        review_status=review_status,
        surface_cover_names=surface_cover_names,
        target_name=target_name,
        shadow_mask=shadow,
    )
    if write_pixels_parquet:
        pixels_path = directory / "pixels.parquet"
        frame.to_parquet(pixels_path, index=False, compression="zstd")
        artifacts["pixels"] = _artifact(pixels_path)
    finite_count = int(np.isfinite(temperature).sum())
    actual_qa = qa_status if finite_count else QAStatus.FAIL
    manifest = CanonicalManifest(
        image_id=image_id,
        group_id=group_id,
        pair_id=pair_id,
        dataset_id=dataset_id,
        visible_path=visible_path,
        thermal_path=thermal_path,
        processing_route=processing_route,
        source_method=source_method,
        image_height=int(temperature.shape[0]),
        image_width=int(temperature.shape[1]),
        processing_status=ProcessingStatus.SUCCESS if actual_qa != QAStatus.FAIL else ProcessingStatus.FAILED,
        qa_status=actual_qa,
        review_status=review_status,
        configuration_hash=configuration_hash,
        source_file_hashes=source_file_hashes,
        validation_status=validation_status,
        scene_correspondence=scene_correspondence,
        coverage_class=coverage_class,
        label_provenance=source_method.value,
        surface_cover_class_id=surface_cover_class_id,
        surface_cover_category=surface_cover_category,
        target_name=target_name or None,
        polygon_coordinates=polygon_coordinates or [],
        known_pixel_count=int(known_mask.sum()),
        unknown_pixel_count=int(known_mask.size - known_mask.sum()),
        annotation_source=source_method.value,
        reviewer_confidence=reviewer_confidence,
        temperature_metadata={**(temperature_metadata or {}), "finite_pixel_count": finite_count},
        artifacts=artifacts,
        exclusions=exclusions or [],
        notes=notes,
        created_at_utc=datetime.now(timezone.utc).isoformat(),
    )
    manifest.validate()
    manifest_path = directory / "manifest.json"
    manifest_path.write_text(json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest, manifest_path


def load_manifest(path: Path, *, validate_artifacts: bool = True) -> CanonicalManifest:
    manifest = CanonicalManifest.from_dict(json.loads(path.read_text(encoding="utf-8")))
    manifest.validate(require_artifacts=validate_artifacts)
    return manifest


def eligible_target_pixels(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"temperature_is_finite", "label_known", "analysis_eligible", "annotation_review_status"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Canonical pixel table is missing eligibility fields: {sorted(missing)}")
    eligible = (
        frame["temperature_is_finite"].astype(bool)
        & frame["label_known"].astype(bool)
        & frame["analysis_eligible"].astype(bool)
        & frame["annotation_review_status"].astype(str).eq(ManualReviewStatus.ACCEPTED.value)
    )
    return frame.loc[eligible].copy()
