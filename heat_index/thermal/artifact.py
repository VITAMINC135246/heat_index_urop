"""Portable, versioned temperature matrix and provenance sidecar.

The NPY and JSON files are one logical artifact. A reader verifies both before
returning a TemperatureResult; moving the two files together needs no path edits.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from heat_index.provenance.result_index import sha256_file
from heat_index.provenance.models import PROCESSING_VERSION


THERMAL_ARTIFACT_SCHEMA_VERSION = "thermal-artifact-v1"
THERMAL_CACHE_VERSION = 1
RADIOMETRIC_PARAMETER_KEYS = (
    "distance_m",
    "relative_humidity_percent",
    "emissivity",
    "ambient_temperature_c",
    "reflected_temperature_c",
)


def sidecar_path(matrix_path: Path) -> Path:
    """Keep the historical Part D sidecar filename for pilot matrix paths."""
    stem = matrix_path.stem
    if stem.endswith("_temperature_celsius"):
        return matrix_path.with_name(stem.removesuffix("_temperature_celsius") + "_temperature_metadata.json")
    return matrix_path.with_suffix(".metadata.json")


def parameter_fingerprint(parameters: Mapping[str, Any]) -> str | None:
    """Hash only a complete SDK parameter set; missing values remain unknown."""
    values: dict[str, float] = {}
    for key in RADIOMETRIC_PARAMETER_KEYS:
        value = parameters.get(key)
        if value in (None, ""):
            return None
        try:
            values[key] = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid radiometric parameter {key}: {value!r}") from exc
        if not np.isfinite(values[key]):
            raise ValueError(f"Non-finite radiometric parameter {key}: {value!r}")
    encoded = json.dumps(values, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def write_thermal_artifact(matrix_path: Path, result: Any, *, image_id: str) -> Path:
    """Write an NPY and binding sidecar; incomplete writes fail closed on read."""
    matrix = np.asarray(result.matrix)
    if matrix.ndim != 2 or matrix.dtype != np.dtype("float32"):
        raise ValueError("Standard thermal artifacts require a two-dimensional float32 matrix.")
    metadata = dict(result.metadata)
    if metadata.get("temperature_unit") in (None, ""):
        raise ValueError("A standard thermal artifact requires an explicit temperature unit.")
    matrix_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_matrix = matrix_path.with_suffix(matrix_path.suffix + ".tmp")
    with temporary_matrix.open("wb") as handle:
        np.save(handle, matrix, allow_pickle=False)
        handle.flush()
        os.fsync(handle.fileno())
    payload = {
        "schema_version": THERMAL_ARTIFACT_SCHEMA_VERSION,
        "cache_version": THERMAL_CACHE_VERSION,
        "producer": "heat_index.thermal.artifact.write_thermal_artifact",
        "producer_version": PROCESSING_VERSION,
        "image_id": image_id,
        "source_image_identifier": metadata.get("source_image") or None,
        "matrix_file": matrix_path.name,
        "matrix_sha256": sha256_file(temporary_matrix),
        "matrix_shape": list(matrix.shape),
        "matrix_dtype": str(matrix.dtype),
        "parameter_fingerprint": parameter_fingerprint(metadata),
        "source_image_sha256": metadata.get("source_image_sha256") or None,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "metadata": metadata,
        "qa_status": result.qa_status,
        "qa_flags": list(result.qa_flags),
    }
    sidecar = sidecar_path(matrix_path)
    temporary_sidecar = sidecar.with_suffix(sidecar.suffix + ".tmp")
    try:
        temporary_sidecar.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
        temporary_matrix.replace(matrix_path)
        temporary_sidecar.replace(sidecar)
    finally:
        temporary_matrix.unlink(missing_ok=True)
        temporary_sidecar.unlink(missing_ok=True)
    return sidecar


def load_thermal_artifact(
    matrix_path: Path,
    *,
    image_id: str | None = None,
    native_shape: tuple[int, int] | None = None,
    expected_parameters: Mapping[str, Any] | None = None,
    source_image_path: Path | None = None,
) -> Any:
    """Verify the matrix, provenance, and optional current extraction inputs."""
    from heat_index.thermal.extraction import TemperatureResult

    sidecar = sidecar_path(matrix_path)
    if not sidecar.is_file():
        raise FileNotFoundError(f"Thermal provenance sidecar is missing: {sidecar}")
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    if payload.get("schema_version") != THERMAL_ARTIFACT_SCHEMA_VERSION:
        raise ValueError(f"Unsupported thermal artifact schema: {payload.get('schema_version')!r}")
    if payload.get("cache_version") != THERMAL_CACHE_VERSION or not payload.get("producer_version"):
        raise ValueError("Unsupported or incomplete thermal cache version.")
    if payload.get("matrix_file") != matrix_path.name:
        raise ValueError("Thermal sidecar matrix filename does not match.")
    if image_id is not None and payload.get("image_id") != image_id:
        raise ValueError("Thermal sidecar image ID does not match requested image.")
    if payload.get("matrix_sha256") != sha256_file(matrix_path):
        raise ValueError("Thermal matrix checksum does not match its provenance sidecar.")
    matrix = np.load(matrix_path, allow_pickle=False)
    if matrix.ndim != 2 or matrix.dtype != np.dtype("float32"):
        raise ValueError("Thermal artifact matrix must be two-dimensional float32.")
    if list(matrix.shape) != payload.get("matrix_shape") or payload.get("matrix_dtype") != "float32":
        raise ValueError("Thermal sidecar matrix shape or dtype does not match.")
    if native_shape is not None and tuple(matrix.shape) != tuple(native_shape):
        raise ValueError(f"Thermal artifact shape {matrix.shape} does not match native thermal grid {native_shape}.")
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict) or not metadata.get("temperature_unit"):
        raise ValueError("Thermal artifact metadata has no temperature unit.")
    if metadata.get("image_id") not in (None, "", payload.get("image_id")):
        raise ValueError("Thermal sidecar image ID disagrees with embedded metadata.")
    if payload.get("source_image_identifier") != (metadata.get("source_image") or None):
        raise ValueError("Thermal sidecar source image identifier disagrees with metadata.")
    actual_fingerprint = parameter_fingerprint(metadata)
    if payload.get("parameter_fingerprint") != actual_fingerprint:
        raise ValueError("Thermal sidecar radiometric parameter fingerprint does not match metadata.")
    if expected_parameters is not None:
        expected_fingerprint = parameter_fingerprint(expected_parameters)
        if expected_fingerprint is None or actual_fingerprint != expected_fingerprint:
            raise ValueError("Cached thermal artifact has incompatible radiometric parameters.")
    source_hash = payload.get("source_image_sha256")
    if source_hash != (metadata.get("source_image_sha256") or None):
        raise ValueError("Thermal sidecar source image checksum does not match metadata.")
    if source_image_path is not None and source_image_path.is_file() and source_hash:
        if sha256_file(source_image_path) != source_hash:
            raise ValueError("Cached thermal artifact has a different source image checksum.")
    if source_image_path is not None and source_image_path.is_file() and not source_hash:
        raise ValueError("Cached thermal artifact has no source image checksum to verify.")
    qa_flags = payload.get("qa_flags", [])
    if not isinstance(qa_flags, list):
        raise ValueError("Thermal artifact QA flags must be a list.")
    return TemperatureResult(
        matrix=matrix,
        metadata={**metadata, "artifact_schema_version": THERMAL_ARTIFACT_SCHEMA_VERSION, "provenance_binding": "verified"},
        qa_status=str(payload.get("qa_status", "")),
        qa_flags=[str(flag) for flag in qa_flags],
    )
