"""Build, load, and validate canonical per-thermal-image schema-0.2 results."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .models import (
    ArtifactReference,
    CanonicalManifest,
    CoverageClass,
    LEGACY_CANONICAL_SCHEMA_VERSION,
    LUHKProvenance,
    ManualReviewStatus,
    MeasurementType,
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


def _atomic_npy(path: Path, array: np.ndarray) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as handle:
        np.save(handle, array, allow_pickle=False)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def _atomic_parquet(path: Path, frame: pd.DataFrame) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(temporary, index=False, compression="zstd")
    temporary.replace(path)


def validate_label_layers(
    temperature: np.ndarray,
    labels: np.ndarray,
    known_mask: np.ndarray,
    shadow_mask: np.ndarray | None = None,
    *,
    luhk_labels: np.ndarray | None = None,
    luhk_known_mask: np.ndarray | None = None,
    target_mask: np.ndarray | None = None,
) -> None:
    if temperature.ndim != 2:
        raise ValueError("Temperature matrix must be two-dimensional.")
    if labels.shape != temperature.shape or known_mask.shape != temperature.shape:
        raise ValueError("Temperature, label, and surface-cover-known shapes must match.")
    if known_mask.dtype != np.bool_:
        raise ValueError("known_mask must have boolean dtype.")
    for name, array in (("shadow-mask", shadow_mask), ("LUHK labels", luhk_labels), ("LUHK known mask", luhk_known_mask), ("target mask", target_mask)):
        if array is not None and array.shape != temperature.shape:
            raise ValueError(f"{name} shape must match the native temperature grid.")
    if luhk_known_mask is not None and luhk_known_mask.dtype != np.bool_:
        raise ValueError("luhk_known_mask must have boolean dtype.")
    if target_mask is not None and target_mask.dtype != np.bool_:
        raise ValueError("target_mask must have boolean dtype.")
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
    measurement_type: MeasurementType,
    review_status: ManualReviewStatus,
    qa_status: QAStatus = QAStatus.PASS,
    surface_cover_names: dict[int, str] | None = None,
    target_name: str = "",
    target_mask: np.ndarray | None = None,
    shadow_mask: np.ndarray | None = None,
    luhk_labels: np.ndarray | None = None,
    luhk_known_mask: np.ndarray | None = None,
    surface_cover_provenance: str = "unknown",
    luhk_provenance: str = "unknown",
    temperature_source: str = "",
) -> pd.DataFrame:
    shape = temperature.shape
    target = np.ones(shape, dtype=bool) if target_mask is None else np.asarray(target_mask, dtype=bool)
    luhk_known = np.zeros(shape, dtype=bool) if luhk_known_mask is None else np.asarray(luhk_known_mask, dtype=bool)
    luhk = np.full(shape, "", dtype="<U96") if luhk_labels is None else np.asarray(luhk_labels).astype("<U96")
    validate_label_layers(
        temperature, labels, known_mask, shadow_mask,
        luhk_labels=luhk, luhk_known_mask=luhk_known, target_mask=target,
    )
    height, width = shape
    rows = np.repeat(np.arange(height, dtype=np.int32), width)
    cols = np.tile(np.arange(width, dtype=np.int32), height)
    values = temperature.astype(np.float32, copy=False).ravel(order="C")
    finite = np.isfinite(values)
    known = known_mask.ravel(order="C")
    selected = target.ravel(order="C")
    label_ids = labels.astype(np.int16, copy=False).ravel(order="C")
    accepted = review_status == ManualReviewStatus.ACCEPTED
    qa_eligible = qa_status != QAStatus.FAIL
    eligible = finite & known & selected & accepted & qa_eligible
    exclusion = np.full(values.size, "", dtype=object)
    exclusion[~finite] = "non_finite_temperature"
    exclusion[finite & ~selected] = "outside_target_selection"
    exclusion[finite & selected & ~known] = "label_unknown"
    if not accepted:
        exclusion[finite & selected & known] = "annotation_not_accepted"
    if not qa_eligible:
        exclusion[finite & selected & known] = "temperature_qa_failed"
    names = surface_cover_names or {}
    label_names = np.array(
        [names.get(int(value), "") if is_known else "" for value, is_known in zip(label_ids, known)], dtype=object
    )
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
            "measurement_type": measurement_type.value,
            "temperature_source": temperature_source,
            "source_method": source_method.value,
            "label_provenance": surface_cover_provenance,
            "surface_cover_provenance": surface_cover_provenance,
            "label_known": known,
            "surface_cover_known": known,
            "surface_cover_class_id": label_ids,
            "surface_cover_class": label_names,
            "luhk_label": luhk.ravel(order="C"),
            "luhk_known": luhk_known.ravel(order="C"),
            "luhk_provenance": luhk_provenance,
            "target_mask": selected,
            "analysis_eligible": eligible,
            "exclusion_reason": exclusion,
            "target_name": target_name,
            "qa_status": qa_status.value,
            "annotation_review_status": review_status.value,
        }
    )
    if shadow_mask is None:
        frame["shadow_flag"] = pd.array([pd.NA] * len(frame), dtype="Int8")
        frame["shadow_valid"] = False
    else:
        frame["shadow_flag"] = pd.array(np.asarray(shadow_mask, dtype=np.int8).ravel(order="C"), dtype="Int8")
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
    target_mask: np.ndarray | None = None,
    luhk_labels: np.ndarray | None = None,
    luhk_known_mask: np.ndarray | None = None,
    luhk_category: str | None = None,
    luhk_code: str | None = None,
    luhk_provenance: str = LUHKProvenance.UNKNOWN.value,
    temperature_metadata: dict[str, Any] | None = None,
    ambient_metadata: dict[str, Any] | None = None,
    temperature_source: str = "",
    validation_status: str = "",
    part_a: dict[str, Any] | None = None,
    part_b0: dict[str, Any] | None = None,
    part_b: dict[str, Any] | None = None,
    scene_correspondence: str = SceneCorrespondence.INDETERMINATE.value,
    coverage_class: str = CoverageClass.INDETERMINATE.value,
    dependency_fingerprints: dict[str, str] | None = None,
    derived_input_hashes: dict[str, str] | None = None,
    tool_identity: dict[str, str] | None = None,
    annotation_review: dict[str, Any] | None = None,
    exclusions: list[str] | None = None,
    notes: str = "",
    write_pixels_parquet: bool = True,
) -> tuple[CanonicalManifest, Path]:
    temperature = np.asarray(temperature, dtype=np.float32)
    labels = np.asarray(labels, dtype=np.int16)
    known = np.asarray(known_mask, dtype=bool)
    if temperature.ndim != 2 or labels.shape != temperature.shape or known.shape != temperature.shape:
        raise ValueError("Temperature, label, and known-mask shapes must match the native two-dimensional thermal grid.")
    shadow = np.asarray(shadow_mask, dtype=bool) if shadow_mask is not None else None
    if processing_route == ProcessingRoute.THERMAL_POLYGON:
        measurement_type = MeasurementType.POLYGON_SELECTED_THERMAL_PIXEL
        selection_scope = "user_accepted_thermal_polygon"
        surface_provenance = SourceMethod.THERMAL_POLYGON_USER_ANNOTATION.value
        target = known.copy() if target_mask is None else np.asarray(target_mask, dtype=bool)
        if review_status != ManualReviewStatus.ACCEPTED:
            raise ValueError("A successful polygon canonical result requires an accepted annotation.")
        if surface_cover_class_id is None or not surface_cover_category:
            raise ValueError("Polygon results require a selected surface-cover class ID and category.")
        if not luhk_category:
            raise ValueError("Polygon results require a selected LUHK category.")
        if luhk_provenance not in {item.value for item in LUHKProvenance}:
            raise ValueError("Polygon results require explicit official/user/unknown LUHK provenance.")
        if luhk_provenance == LUHKProvenance.UNKNOWN.value:
            raise ValueError("Accepted polygon results require known LUHK context.")
        if np.any(labels[known] != int(surface_cover_class_id)):
            raise ValueError("Every known polygon pixel must receive the selected surface-cover class.")
        if not np.array_equal(target, known):
            raise ValueError("Polygon target_mask and target-specific known surface-cover mask must match.")
        luhk_known = target.copy() if luhk_known_mask is None else np.asarray(luhk_known_mask, dtype=bool)
        if not np.array_equal(luhk_known, target):
            raise ValueError("User-supplied polygon LUHK context must be known only inside target_mask.")
        luhk = np.full(temperature.shape, "", dtype="<U96")
        luhk[target] = str(luhk_code or luhk_category)
    elif processing_route == ProcessingRoute.NORMAL_VT:
        measurement_type = MeasurementType.FULL_THERMAL_PIXEL
        selection_scope = "full_native_thermal_grid"
        surface_provenance = SourceMethod.VISIBLE_REVIEW.value
        target = np.ones(temperature.shape, dtype=bool) if target_mask is None else np.asarray(target_mask, dtype=bool)
        luhk_known = np.zeros(temperature.shape, dtype=bool) if luhk_known_mask is None else np.asarray(luhk_known_mask, dtype=bool)
        luhk = np.full(temperature.shape, "", dtype="<U96") if luhk_labels is None else np.asarray(luhk_labels).astype("<U96")
    else:
        raise ValueError("Canonical results may only be written for successful normal or thermal-polygon routes.")
    validate_label_layers(
        temperature, labels, known, shadow,
        luhk_labels=luhk, luhk_known_mask=luhk_known, target_mask=target,
    )
    directory = output_root / image_id
    directory.mkdir(parents=True, exist_ok=True)
    temperature_path = directory / "temperature.npy"
    labels_path = directory / "surface_cover_labels.npy"
    known_path = directory / "surface_cover_known_mask.npy"
    luhk_path = directory / "luhk_labels.npy"
    luhk_known_path = directory / "luhk_known_mask.npy"
    target_path = directory / "target_mask.npy"
    _atomic_npy(temperature_path, temperature)
    _atomic_npy(labels_path, labels)
    _atomic_npy(known_path, known)
    _atomic_npy(luhk_path, luhk)
    _atomic_npy(luhk_known_path, luhk_known)
    _atomic_npy(target_path, target)
    known_ref = _artifact(known_path, known)
    artifacts: dict[str, ArtifactReference] = {
        "temperature": _artifact(temperature_path, temperature),
        "surface_cover_labels": _artifact(labels_path, labels),
        "surface_cover_known_mask": known_ref,
        "known_mask": known_ref,
        "luhk_labels": _artifact(luhk_path, luhk),
        "luhk_known_mask": _artifact(luhk_known_path, luhk_known),
        "target_mask": _artifact(target_path, target),
    }
    if shadow is not None:
        shadow_path = directory / "shadow_mask.npy"
        _atomic_npy(shadow_path, shadow)
        artifacts["shadow_mask"] = _artifact(shadow_path, shadow)
    resolved_temperature_source = temperature_source or str((temperature_metadata or {}).get("extraction_method", ""))
    frame = pixel_frame(
        image_id=image_id,
        group_id=group_id,
        pair_id=pair_id,
        dataset_id=dataset_id,
        temperature=temperature,
        labels=labels,
        known_mask=known,
        source_method=source_method,
        measurement_type=measurement_type,
        review_status=review_status,
        qa_status=qa_status,
        surface_cover_names=surface_cover_names,
        target_name=target_name,
        target_mask=target,
        shadow_mask=shadow,
        luhk_labels=luhk,
        luhk_known_mask=luhk_known,
        surface_cover_provenance=surface_provenance,
        luhk_provenance=luhk_provenance,
        temperature_source=resolved_temperature_source,
    )
    ambient_value = (temperature_metadata or {}).get(
        "ambient_temperature_c", (ambient_metadata or {}).get("ambient_temperature_c")
    )
    try:
        ambient_float = float(ambient_value)
    except (TypeError, ValueError):
        ambient_float = np.nan
    frame["ambient_temperature_c"] = np.float32(ambient_float)
    frame["delta_t_c"] = (
        pd.to_numeric(frame["temperature_c"], errors="coerce") - ambient_float
    ).astype("float32")
    if not np.isfinite(ambient_float):
        frame["delta_t_c"] = np.float32(np.nan)
    frame["delta_temperature_available"] = bool(np.isfinite(ambient_float))
    if write_pixels_parquet:
        pixels_path = directory / "pixels.parquet"
        _atomic_parquet(pixels_path, frame)
        artifacts["pixels"] = _artifact(pixels_path)
    finite_count = int(np.isfinite(temperature).sum())
    actual_qa = qa_status if finite_count else QAStatus.FAIL
    processing_status = ProcessingStatus.SUCCESS if actual_qa != QAStatus.FAIL else ProcessingStatus.FAILED
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
        processing_status=processing_status,
        qa_status=actual_qa,
        review_status=review_status,
        measurement_type=measurement_type,
        selection_scope=selection_scope,
        configuration_hash=configuration_hash,
        dependency_fingerprints=dependency_fingerprints or {},
        source_file_hashes=source_file_hashes,
        derived_input_hashes=derived_input_hashes or {},
        tool_identity=tool_identity or {},
        part_a=part_a or {},
        part_b0=part_b0 or {},
        part_b=part_b or {},
        validation_status=validation_status,
        scene_correspondence=scene_correspondence,
        coverage_class=coverage_class,
        label_provenance=surface_provenance,
        surface_cover_provenance=surface_provenance,
        luhk_provenance=luhk_provenance,
        luhk_category=luhk_category,
        luhk_code=luhk_code,
        surface_cover_class_id=surface_cover_class_id,
        surface_cover_category=surface_cover_category,
        target_name=target_name or None,
        polygon_coordinates=polygon_coordinates or [],
        known_pixel_count=int(known.sum()),
        unknown_pixel_count=int(known.size - known.sum()),
        target_pixel_count=int(target.sum()),
        annotation_source=surface_provenance,
        annotation_review=annotation_review or {},
        reviewer_confidence=reviewer_confidence,
        temperature_source=resolved_temperature_source,
        temperature_metadata={**(temperature_metadata or {}), "finite_pixel_count": finite_count},
        ambient_metadata=ambient_metadata or {},
        artifacts=artifacts,
        exclusions=exclusions or [],
        notes=notes,
        created_at_utc=datetime.now(timezone.utc).isoformat(),
    )
    manifest.validate()
    manifest_path = directory / "manifest.json"
    temporary_manifest = manifest_path.with_suffix(".json.tmp")
    temporary_manifest.write_text(json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    temporary_manifest.replace(manifest_path)
    return manifest, manifest_path


def load_manifest(path: Path, *, validate_artifacts: bool = True, allow_legacy: bool = True) -> CanonicalManifest:
    manifest = CanonicalManifest.from_dict(json.loads(path.read_text(encoding="utf-8")))
    manifest.validate(require_artifacts=validate_artifacts, allow_legacy=allow_legacy)
    return manifest


def read_schema_01_manifest(path: Path) -> CanonicalManifest:
    manifest = load_manifest(path, allow_legacy=True)
    if manifest.schema_version != LEGACY_CANONICAL_SCHEMA_VERSION:
        raise ValueError("The requested compatibility reader only accepts schema 0.1 manifests.")
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
