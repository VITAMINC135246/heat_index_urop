"""Generalized per-image DJI SDK temperature extraction for version 0.1."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from PIL import Image, ImageOps


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
        return "fail", ["no_finite_temperature_pixels"]
    if np.allclose(finite, finite[0]):
        flags.append("constant_temperature_matrix")
    if np.allclose(finite, 0.0):
        flags.append("all_zero_temperature_matrix")
    if float(np.min(finite)) < -100 or float(np.max(finite)) > 300:
        flags.append("outside_broad_celsius_plausibility_range")
    if float(np.min(finite)) < 0:
        flags.append("subzero_pixels_require_review")
    if float(np.max(finite)) > 80:
        flags.append("high_temperature_pixels_require_review")
    failed = {"constant_temperature_matrix", "all_zero_temperature_matrix", "outside_broad_celsius_plausibility_range"}
    if failed.intersection(flags):
        return "fail", flags
    return ("warn" if flags else "pass"), flags


def extract_temperature(
    *,
    thermal_path: Path,
    image_id: str,
    parameters: dict[str, Any],
    work_directory: Path,
    irp_exe: Path,
    keep_raw: bool = False,
) -> TemperatureResult:
    with Image.open(thermal_path) as source:
        oriented = ImageOps.exif_transpose(source)
        width, height = oriented.size
    raw_path = work_directory / f"{image_id}_temperature_float32.raw"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(irp_exe), "-s", str(thermal_path), "-a", "measure", "-o", str(raw_path),
        "--measurefmt", "float32",
        "--distance", str(parameters["distance_m"]),
        "--humidity", str(parameters["relative_humidity_percent"]),
        "--emissivity", str(parameters["emissivity"]),
        "--ambient", str(parameters["ambient_temperature_c"]),
        "--reflection", str(parameters["reflected_temperature_c"]),
    ]
    completed = subprocess.run(
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
        "qa_flags": flags,
    }
    return TemperatureResult(matrix, metadata, qa_status, flags)


def load_temperature_override(path: Path) -> TemperatureResult:
    matrix = np.load(path)
    if matrix.ndim != 2:
        raise ValueError(f"Temperature override must be a two-dimensional NPY matrix: {path}")
    status, flags = temperature_qa(matrix)
    return TemperatureResult(
        matrix.astype(np.float32, copy=False),
        {"extraction_method": "provided_npy", "source_npy": path.resolve().as_posix(), "qa_flags": flags},
        status,
        flags,
    )
