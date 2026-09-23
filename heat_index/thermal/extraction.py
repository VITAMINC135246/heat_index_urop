"""Generalized per-image DJI SDK temperature extraction for version 0.1."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
from PIL import Image, ImageOps

from heat_index.provenance.result_index import sha256_file
from heat_index.thermal.artifact import (
    THERMAL_ARTIFACT_SCHEMA_VERSION,
    load_thermal_artifact,
    parameter_fingerprint,
    sidecar_path,
)


REQUIRED_PARAMETER_COLUMNS = {
    "image_id",
    "ambient_temperature_c",
    "reflected_temperature_c",
    "distance_m",
    "emissivity",
    "humidity_percent",
}


@dataclass(slots=True)
class TemperatureResult:
    matrix: np.ndarray
    metadata: dict[str, Any]
    qa_status: str
    qa_flags: list[str]


def load_parameter_row(path: Path, image_id: str) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"TAT3 parameter table does not exist: {path}")
    table = pd.read_csv(path, dtype=str).fillna("")
    missing = REQUIRED_PARAMETER_COLUMNS.difference(table.columns)
    if missing:
        raise ValueError(f"TAT3 parameter table is missing columns: {sorted(missing)}")
    rows = table.loc[table["image_id"].astype(str).eq(image_id)]
    if len(rows) != 1:
        raise ValueError(f"Expected exactly one TAT3 parameter row for {image_id}; found {len(rows)}.")
    row = rows.iloc[0]
    if "ambient_parse_status" in row and str(row["ambient_parse_status"]).casefold() != "ok":
        raise ValueError(f"TAT3 ambient_parse_status is not ok for {image_id}.")
    result: dict[str, Any] = {}
    for source, target in (
        ("distance_m", "distance_m"),
        ("humidity_percent", "relative_humidity_percent"),
        ("emissivity", "emissivity"),
        ("ambient_temperature_c", "ambient_temperature_c"),
        ("reflected_temperature_c", "reflected_temperature_c"),
    ):
        try:
            result[target] = float(row[source])
        except ValueError as exc:
            raise ValueError(f"TAT3 parameter {source} is not numeric for {image_id}.") from exc
    result["source_report"] = str(row.get("source_report", ""))
    result["parameter_source"] = "TAT3 exported report"
    result["parameter_source_record"] = result["source_report"]
    result["parameter_table"] = path.resolve().as_posix()
    result["report_capture_datetime"] = str(row.get("report_capture_datetime", ""))
    result["humidity_use_status"] = str(row.get("humidity_use_status", ""))
    return result


def load_report_parameter_row(path: Path, image_id: str) -> dict[str, Any]:
    """Read one image's SDK parameters directly from a user-supplied TAT3 report."""
    if not path.is_file():
        raise FileNotFoundError(f"TAT3 report does not exist: {path}")
    from heat_index.thermal.measurements import _ambient_entries

    entries = _ambient_entries(path)
    rows = [entry for entry in entries if str(entry.get("image_id", "")).casefold() == image_id.casefold()]
    if len(rows) != 1:
        raise ValueError(f"Expected exactly one TAT3 report entry for {image_id}; found {len(rows)}.")
    row = rows[0]
    if str(row.get("ambient_parse_status", "")).casefold() != "ok":
        raise ValueError(f"TAT3 ambient_parse_status is not ok for {image_id}.")
    result: dict[str, Any] = {}
    for source, target in (
        ("distance_m", "distance_m"),
        ("humidity_percent", "relative_humidity_percent"),
        ("emissivity", "emissivity"),
        ("ambient_temperature_c", "ambient_temperature_c"),
        ("reflected_temperature_c", "reflected_temperature_c"),
    ):
        try:
            result[target] = float(row[source])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"TAT3 report parameter {source} is not numeric for {image_id}.") from exc
    result["source_report"] = path.resolve().as_posix()
    result["parameter_source"] = "TAT3 exported report"
    result["parameter_source_record"] = result["source_report"]
    result["report_capture_datetime"] = str(row.get("report_capture_datetime", ""))
    result["humidity_use_status"] = str(row.get("humidity_use_status", ""))
    return result


def resolve_irp_exe(
    *,
    irp_exe: str = "",
    sdk_root: str = "",
    sdk_config_path: Path | None = None,
) -> Path:
    if sys.platform != "win32":
        raise RuntimeError("DJI thermal extraction requires Windows and the DJI thermal runtime. Use a precomputed thermal artifact on this host.")
    candidates: list[Path] = []
    if irp_exe:
        candidates.append(Path(irp_exe))
    if sdk_root:
        candidates.append(Path(sdk_root) / "utility" / "bin" / "windows" / "release_x64" / "dji_irp.exe")
        candidates.append(Path(sdk_root) / "dji_irp.exe")
    if sdk_config_path and sdk_config_path.is_file():
        config = json.loads(sdk_config_path.read_text(encoding="utf-8"))
        if config.get("dji_irp_exe"):
            candidates.append(Path(str(config["dji_irp_exe"])))
        if config.get("sdk_root"):
            root = Path(str(config["sdk_root"]))
            candidates.extend(
                [root / "utility" / "bin" / "windows" / "release_x64" / "dji_irp.exe", root / "dji_irp.exe"]
            )
    if os.environ.get("DJI_IRP_EXE"):
        candidates.append(Path(os.environ["DJI_IRP_EXE"]))
    if os.environ.get("DJI_THERMAL_SDK_ROOT"):
        root = Path(os.environ["DJI_THERMAL_SDK_ROOT"])
        candidates.extend([root / "utility" / "bin" / "windows" / "release_x64" / "dji_irp.exe", root / "dji_irp.exe"])
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError("No callable dji_irp.exe was found in CLI options, local config, or environment variables.")


def temperature_qa(matrix: np.ndarray) -> tuple[str, list[str]]:
    flags: list[str] = []
    finite = matrix[np.isfinite(matrix)]
    if finite.size == 0:
        return "fail", ["no_finite_values"]
    minimum = float(np.min(finite))
    maximum = float(np.max(finite))
    if np.allclose(finite, 0.0):
        flags.append("all_zero")
    if float(np.std(finite)) < 1e-6:
        flags.append("all_constant")
    sample = finite[: min(finite.size, 100000)]
    if minimum >= 0 and maximum <= 255 and np.allclose(sample, np.round(sample), atol=1e-6) and len(np.unique(sample)) <= 256:
        flags.append("preview_intensity_like_integer_values")
    if minimum < 0 or maximum > 80:
        flags.append("outside_typical_surface_temperature_review_range")
    if minimum < -80 or maximum > 200:
        flags.append("outside_broad_celsius_plausibility_range")
    failed = {"all_constant", "all_zero", "outside_broad_celsius_plausibility_range"}
    if failed.intersection(flags):
        return "fail", flags
    return ("warn" if flags else "pass"), flags


def build_sdk_command(
    *,
    irp_exe: Path,
    thermal_path: Path,
    raw_path: Path,
    parameters: dict[str, Any],
) -> list[str]:
    """Build the preserved Part D DJI SDK measure/float32 command."""
    return [
        str(irp_exe), "-s", str(thermal_path), "-a", "measure", "-o", str(raw_path),
        "--measurefmt", "float32",
        "--distance", str(parameters["distance_m"]),
        "--humidity", str(parameters["relative_humidity_percent"]),
        "--emissivity", str(parameters["emissivity"]),
        "--ambient", str(parameters["ambient_temperature_c"]),
        "--reflection", str(parameters["reflected_temperature_c"]),
    ]


def extract_temperature(
    *,
    thermal_path: Path,
    image_id: str,
    parameters: dict[str, Any],
    work_directory: Path,
    irp_exe: Path,
    keep_raw: bool = False,
    runner: Callable[..., Any] = subprocess.run,
) -> TemperatureResult:
    if sys.platform != "win32" and runner is subprocess.run:
        raise RuntimeError("DJI thermal extraction requires Windows and the DJI thermal runtime. Use a precomputed thermal artifact on this host.")
    with Image.open(thermal_path) as source:
        oriented = ImageOps.exif_transpose(source)
        width, height = oriented.size
    raw_path = work_directory / f"{image_id}_temperature_float32.raw"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    command = build_sdk_command(irp_exe=irp_exe, thermal_path=thermal_path, raw_path=raw_path, parameters=parameters)
    completed = runner(
        command,
        cwd=irp_exe.parent,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    output = "\n".join(part for part in (completed.stdout.strip(), completed.stderr.strip()) if part)
    if completed.returncode:
        raise RuntimeError(f"DJI SDK returned {completed.returncode}: {output}")
    if not raw_path.is_file():
        raise RuntimeError("DJI SDK returned success but did not create the float32 output.")
    values = np.fromfile(raw_path, dtype=np.float32)
    if values.size != width * height:
        raise ValueError(f"SDK matrix has {values.size} values; expected {width * height} for {width}x{height}.")
    matrix = values.reshape((height, width))
    qa_status, flags = temperature_qa(matrix)
    if not keep_raw:
        raw_path.unlink(missing_ok=True)
    metadata = {
        **parameters,
        "image_id": image_id,
        "source_image": thermal_path.name,
        "source_image_sha256": sha256_file(thermal_path),
        "extraction_method": "DJI Thermal SDK dji_irp.exe measure float32",
        "temperature_definition": "per-pixel radiometric surface temperature",
        "temperature_unit": "degC",
        "ambient_source": "TAT3 exported ambient parameter" if parameters.get("source_report") else "SDK measurement parameter",
        "ambient_definition": "TAT3 exported ambient parameter; not independently validated meteorological air temperature" if parameters.get("source_report") else "SDK measurement ambient parameter; meteorological status unknown",
        "ambient_source_record": parameters.get("source_report", ""),
        "ambient_validation_status": "provisional_report_parameter" if parameters.get("source_report") else "unknown",
        "thermal_width": width,
        "thermal_height": height,
        "sdk_output": output,
        "sdk_tool_path": irp_exe.resolve().as_posix(),
        "sdk_tool_sha256": sha256_file(irp_exe),
        "sdk_command_parameter_names": ["distance", "humidity", "emissivity", "ambient", "reflection"],
        "qa_flags": flags,
    }
    return TemperatureResult(matrix, metadata, qa_status, flags)


def load_temperature_override(
    path: Path,
    *,
    ambient_metadata: dict[str, Any] | None = None,
    native_shape: tuple[int, int] | None = None,
    image_id: str | None = None,
    expected_parameters: dict[str, Any] | None = None,
    source_image_path: Path | None = None,
) -> TemperatureResult:
    sidecar = sidecar_path(path)
    if sidecar.is_file():
        sidecar_payload = json.loads(sidecar.read_text(encoding="utf-8"))
        if sidecar_payload.get("schema_version") == THERMAL_ARTIFACT_SCHEMA_VERSION:
            result = load_thermal_artifact(
                path,
                image_id=image_id,
                native_shape=native_shape,
                expected_parameters=expected_parameters,
                source_image_path=source_image_path,
            )
            if ambient_metadata and ambient_metadata.get("ambient_temperature_c") not in (None, ""):
                result.metadata["radiometric_ambient_temperature_c"] = result.metadata.get("ambient_temperature_c")
                result.metadata["ambient_temperature_c"] = ambient_metadata["ambient_temperature_c"]
                result.metadata["ambient_source"] = ambient_metadata.get("source", "unknown")
                result.metadata["ambient_definition"] = ambient_metadata.get("definition", "unknown")
                result.metadata["ambient_source_record"] = ambient_metadata.get("source_record", "")
                result.metadata["ambient_validation_status"] = ambient_metadata.get("validation_status", "unknown")
            return result
        if sidecar_payload.get("schema_version"):
            raise ValueError(f"Unsupported thermal artifact schema: {sidecar_payload['schema_version']!r}")
        historical_parameters = sidecar_payload.get("measurement_parameters", {})
        if expected_parameters is not None and parameter_fingerprint(historical_parameters) != parameter_fingerprint(expected_parameters):
            raise ValueError("Historical Part D metadata has incompatible radiometric parameters.")
    else:
        sidecar_payload = {}
    matrix = np.load(path, allow_pickle=False)
    if matrix.ndim != 2:
        raise ValueError(f"Temperature override must be a two-dimensional NPY matrix: {path}")
    if native_shape is not None and tuple(matrix.shape) != tuple(native_shape):
        raise ValueError(f"Temperature override shape {matrix.shape} does not match native thermal grid {native_shape}.")
    status, flags = temperature_qa(matrix)
    metadata = {
        **dict(ambient_metadata or {}),
        **dict(sidecar_payload.get("measurement_parameters", {})),
        "extraction_method": str((ambient_metadata or {}).get("extraction_method") or sidecar_payload.get("extraction_method") or "provided_npy"),
        "temperature_definition": str((ambient_metadata or {}).get("temperature_definition") or ""),
        "temperature_unit": str((ambient_metadata or {}).get("temperature_unit") or sidecar_payload.get("temperature_unit") or "degC"),
        "source_npy": path.resolve().as_posix(),
        "source_npy_sha256": sha256_file(path),
        "ambient_temperature_c": (ambient_metadata or {}).get("ambient_temperature_c", sidecar_payload.get("measurement_parameters", {}).get("ambient_temperature_c")),
        "provenance_binding": "legacy_unverified" if sidecar_payload else "unverified_npy",
        "delta_temperature_available": bool((ambient_metadata or {}).get("ambient_temperature_c") not in (None, "")),
        "qa_flags": flags,
    }
    return TemperatureResult(
        matrix.astype(np.float32, copy=False),
        metadata,
        status,
        flags,
    )


def legacy_summary_metadata(row: Any) -> dict[str, Any]:
    """Recover the accepted Part D CSV's actual parameters and definitions."""
    fields = {
        "distance_m": row.get("distance_m", ""),
        "relative_humidity_percent": row.get("relative_humidity_percent", ""),
        "emissivity": row.get("emissivity", ""),
        "ambient_temperature_c": row.get("ambient_temperature_c", ""),
        "reflected_temperature_c": row.get("reflected_temperature_c", ""),
    }
    return {
        **fields,
        "extraction_method": str(row.get("extraction_method", "legacy_part_d")),
        "temperature_definition": "per-pixel radiometric surface temperature",
        "temperature_unit": str(row.get("temperature_unit", "Celsius interpreted from SDK measure output")),
        "measurement_parameter_source": str(row.get("measurement_parameter_source", "")),
        "parameter_source": str(row.get("measurement_parameter_source", "")),
        "parameter_table": str(row.get("tat3_parameter_table", "")),
        "source_report": str(row.get("tat3_parameter_source_report", "")),
        "report_capture_datetime": str(row.get("tat3_report_capture_datetime", "")),
        "humidity_use_status": str(row.get("humidity_use_status", "")),
        "legacy_validation_status": str(row.get("validation_status", "")),
        "ambient_source": "TAT3 exported ambient parameter",
        "ambient_definition": "TAT3 exported ambient parameter; not independently validated meteorological air temperature",
        "ambient_source_record": str(row.get("tat3_parameter_source_report", "")),
        "ambient_validation_status": "provisional_report_parameter",
    }


def load_legacy_temperature(
    path: Path,
    row: Any,
    *,
    image_id: str,
    native_shape: tuple[int, int] | None = None,
    source_image_path: Path | None = None,
) -> TemperatureResult:
    metadata = legacy_summary_metadata(row)
    result = load_temperature_override(
        path,
        native_shape=native_shape,
        image_id=image_id,
        expected_parameters=metadata if sidecar_path(path).is_file() else None,
        ambient_metadata=metadata if not sidecar_path(path).is_file() else None,
        source_image_path=source_image_path,
    )
    if result.metadata.get("provenance_binding") == "verified":
        if result.metadata.get("temperature_unit") != metadata["temperature_unit"]:
            raise ValueError("Cached pilot temperature unit disagrees with the accepted Part D summary.")
    else:
        result.metadata.update(metadata)
        result.metadata["provenance_binding"] = "legacy_unverified"
    return result
