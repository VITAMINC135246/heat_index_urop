"""Generalized per-image DJI SDK temperature extraction for version 0.1."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
from PIL import Image, ImageOps

from .result_index import sha256_file


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
    result["report_capture_datetime"] = str(row.get("report_capture_datetime", ""))
    result["humidity_use_status"] = str(row.get("humidity_use_status", ""))
    return result


def load_report_parameter_row(path: Path, image_id: str) -> dict[str, Any]:
    """Read one image's SDK parameters directly from a user-supplied TAT3 report."""
    if not path.is_file():
        raise FileNotFoundError(f"TAT3 report does not exist: {path}")
    from .tat3_manual_measurement import _ambient_entries

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
    result["report_capture_datetime"] = str(row.get("report_capture_datetime", ""))
    result["humidity_use_status"] = str(row.get("humidity_use_status", ""))
    return result


def resolve_irp_exe(
    *,
    irp_exe: str = "",
    sdk_root: str = "",
    sdk_config_path: Path | None = None,
) -> Path:
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
        "extraction_method": "DJI Thermal SDK dji_irp.exe measure float32",
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
) -> TemperatureResult:
    matrix = np.load(path, allow_pickle=False)
    if matrix.ndim != 2:
        raise ValueError(f"Temperature override must be a two-dimensional NPY matrix: {path}")
    if native_shape is not None and tuple(matrix.shape) != tuple(native_shape):
        raise ValueError(f"Temperature override shape {matrix.shape} does not match native thermal grid {native_shape}.")
    status, flags = temperature_qa(matrix)
    return TemperatureResult(
        matrix.astype(np.float32, copy=False),
        {
            "extraction_method": "provided_npy",
            "source_npy": path.resolve().as_posix(),
            "source_npy_sha256": sha256_file(path),
            "ambient_temperature_c": (ambient_metadata or {}).get("ambient_temperature_c"),
            "delta_temperature_available": bool(
                ambient_metadata
                and ambient_metadata.get("ambient_temperature_c") not in (None, "")
            ),
            "qa_flags": flags,
        },
        status,
        flags,
    )
