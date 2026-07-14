#!/usr/bin/env python3
"""Extract Part D pilot thermal temperature matrices with the DJI Thermal SDK.

This script expects the DJI Thermal SDK to live outside the repository. It
uses an ignored local config file, environment variables, or command line
arguments to find the SDK command-line utility. It never copies SDK binaries
into this project.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from table_io import write_rows

PILOT_PAIRS_XLSX = PROJECT_ROOT / "data" / "metadata" / "part_b_pilot_pairs.xlsx"
DJI_METADATA_XLSX = PROJECT_ROOT / "data" / "metadata" / "dji_image_metadata.xlsx"
CLASS_MAPPING_XLSX = PROJECT_ROOT / "data" / "annotations" / "part_c" / "surface_cover_class_mapping.xlsx"
PART_C_COMBINED_SUMMARY_XLSX = (
    PROJECT_ROOT / "outputs" / "part_c" / "summaries" / "part_c_luhk_surface_cover_combined_summary.xlsx"
)

LOCAL_CONFIG = PROJECT_ROOT / "config" / "part_d_sdk.local.json"
TEMPLATE_CONFIG = PROJECT_ROOT / "config" / "part_d_sdk.template.json"

TEMPERATURE_DIR = PROJECT_ROOT / "data" / "processed" / "part_d" / "temperature_matrices"
PREVIEW_DIR = PROJECT_ROOT / "outputs" / "part_d" / "previews"
QA_DIR = PROJECT_ROOT / "outputs" / "part_d" / "qa"
SUMMARY_DIR = PROJECT_ROOT / "outputs" / "part_d" / "summaries"
DOC_PATH = PROJECT_ROOT / "docs" / "part_d_temperature_extraction.md"

SUMMARY_CSV = SUMMARY_DIR / "part_d_round1_temperature_extraction_summary.csv"
SUMMARY_MD = SUMMARY_DIR / "part_d_round1_temperature_extraction_summary.md"
MANIFEST_CSV = SUMMARY_DIR / "part_d_round1_pilot_input_manifest.csv"
MANIFEST_XLSX = SUMMARY_DIR / "part_d_round1_pilot_input_manifest.xlsx"
CLASS_QA_CSV = QA_DIR / "part_d_round1_class_temperature_qa.csv"
CLASS_QA_XLSX = QA_DIR / "part_d_round1_class_temperature_qa.xlsx"
SHADOW_QA_CSV = QA_DIR / "part_d_round1_shadow_temperature_qa.csv"
SHADOW_QA_XLSX = QA_DIR / "part_d_round1_shadow_temperature_qa.xlsx"

DEFAULT_CONFIG: dict[str, Any] = {
    "sdk_root": "",
    "dji_irp_exe": "",
    "measure_format": "float32",
    "distance_m": 5.0,
    "relative_humidity_percent": 70.0,
    "emissivity": 1.0,
    "ambient_temperature_c": 25.0,
    "reflected_temperature_c": 23.0,
    "write_matrix_csv": True,
    "keep_sdk_raw": False,
}

COMMON_SDK_ROOTS = [
    Path(r"D:\DJI_Thermal_SDK"),
]


@dataclass
class SdkTool:
    irp_exe: Path | None
    sdk_root: Path | None
    status: str
    message: str
    version_text: str = ""


def relative_posix(path: Path | str) -> str:
    work = Path(path)
    try:
        return work.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return work.as_posix()


def external_sdk_label() -> str:
    return "external DJI Thermal SDK path from ignored local config"


def resolve_project_path(path_text: Any) -> Path:
    path = Path(str(path_text))
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def clean_number(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def clean_int(value: Any, default: int | None = None) -> int | None:
    number = clean_number(value)
    if number is None:
        return default
    return int(round(number))


def load_config(path: Path) -> dict[str, Any]:
    config = dict(DEFAULT_CONFIG)
    if path.is_file():
        with path.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        if not isinstance(loaded, dict):
            raise ValueError(f"Expected object in config file: {relative_posix(path)}")
        config.update(loaded)
    return config


def sdk_root_from_irp(irp_exe: Path) -> Path | None:
    parts = irp_exe.parts
    if "utility" in parts:
        index = parts.index("utility")
        return Path(*parts[:index])
    return None


def candidate_irp_paths(config: dict[str, Any], args: argparse.Namespace) -> list[Path]:
    candidates: list[Path] = []

    for value in [args.irp_exe, config.get("dji_irp_exe"), os.environ.get("DJI_IRP_EXE")]:
        if value:
            candidates.append(Path(str(value)))

    root_values = [
        args.sdk_root,
        config.get("sdk_root"),
        os.environ.get("DJI_THERMAL_SDK_ROOT"),
        *COMMON_SDK_ROOTS,
    ]
    for root_value in root_values:
        if not root_value:
            continue
        root = Path(str(root_value))
        candidates.extend(
            [
                root / "utility" / "bin" / "windows" / "release_x64" / "dji_irp.exe",
                root / "utility" / "bin" / "windows" / "release_x86" / "dji_irp.exe",
            ]
        )

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).casefold()
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def detect_sdk(config: dict[str, Any], args: argparse.Namespace) -> SdkTool:
    checked: list[str] = []
    for candidate in candidate_irp_paths(config, args):
        checked.append(str(candidate))
        if not candidate.is_file():
            continue
        try:
            result = subprocess.run(
                [str(candidate), "--version"],
                cwd=candidate.parent,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return SdkTool(candidate, sdk_root_from_irp(candidate), "not_callable", str(exc))
        version_text = (result.stdout or result.stderr).strip()
        if result.returncode == 0:
            return SdkTool(candidate, sdk_root_from_irp(candidate), "available", "dji_irp.exe is callable.", version_text)
        return SdkTool(
            candidate,
            sdk_root_from_irp(candidate),
            "not_callable",
            f"dji_irp.exe returned exit code {result.returncode}: {version_text}",
            version_text,
        )

    message = "No callable dji_irp.exe found. Checked: " + "; ".join(checked)
    return SdkTool(None, None, "missing", message)


def find_exiftool() -> str:
    candidates = [
        "exiftool",
        "exiftool.exe",
        str(PROJECT_ROOT / "exiftool.exe"),
        str(PROJECT_ROOT / "exiftool-13.59_64" / "exiftool.exe"),
    ]
    for candidate in candidates:
        try:
            result = subprocess.run(
                [candidate, "-ver"],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                check=False,
            )
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0 and result.stdout.strip():
            return f"{candidate} {result.stdout.strip()}"
    return ""


def read_required_table(path: Path, name: str) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Missing {name}: {relative_posix(path)}")
    return pd.read_excel(path, dtype=str).fillna("")


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    pairs = read_required_table(PILOT_PAIRS_XLSX, "Part B pilot pairs")
    metadata = read_required_table(DJI_METADATA_XLSX, "DJI metadata")
    classes = read_required_table(CLASS_MAPPING_XLSX, "Part C class mapping")
    combined = read_required_table(PART_C_COMBINED_SUMMARY_XLSX, "Part C combined summary")
    return pairs, metadata, classes, combined


def metadata_for_t_image(metadata: pd.DataFrame, t_path: str, image_id: str) -> dict[str, Any]:
    if metadata.empty:
        return {}
    path_key = t_path.replace("\\", "/").casefold()
    image_name = f"{image_id}_T.JPG".casefold()
    work = metadata.copy()
    if "image_path" in work.columns:
        hit = work.loc[work["image_path"].astype(str).str.replace("\\", "/", regex=False).str.casefold().eq(path_key)]
        if not hit.empty:
            return hit.iloc[0].to_dict()
    if "image_name" in work.columns:
        hit = work.loc[work["image_name"].astype(str).str.casefold().eq(image_name)]
        if not hit.empty:
            return hit.iloc[0].to_dict()
    return {}


def class_lookup(classes: pd.DataFrame) -> dict[int, str]:
    lookup: dict[int, str] = {}
    for _, row in classes.iterrows():
        class_id = clean_int(row.get("class_id"))
        if class_id is None:
            continue
        lookup[class_id] = str(row.get("class_name", "")).strip()
    return lookup


def safe_stat(array: np.ndarray, name: str) -> float | int:
    finite = array[np.isfinite(array)]
    if name == "nan_count":
        return int(np.isnan(array).sum())
    if name == "invalid_count":
        return int((~np.isfinite(array)).sum())
    if finite.size == 0:
        return float("nan")
    if name == "min":
        return float(np.min(finite))
    if name == "max":
        return float(np.max(finite))
    if name == "mean":
        return float(np.mean(finite))
    if name == "median":
        return float(np.median(finite))
    if name == "std":
        return float(np.std(finite))
    raise ValueError(name)


def looks_like_preview_values(array: np.ndarray) -> bool:
    finite = array[np.isfinite(array)]
    if finite.size == 0:
        return False
    if float(np.min(finite)) < 0 or float(np.max(finite)) > 255:
        return False
    unique_count = len(np.unique(finite[: min(finite.size, 100000)]))
    integer_like = np.allclose(finite[: min(finite.size, 100000)], np.round(finite[: min(finite.size, 100000)]), atol=1e-6)
    return bool(integer_like and unique_count <= 256)


def validation_flags(array: np.ndarray) -> tuple[str, list[str]]:
    finite = array[np.isfinite(array)]
    flags: list[str] = []
    if finite.size == 0:
        flags.append("no_finite_values")
    else:
        minimum = float(np.min(finite))
        maximum = float(np.max(finite))
        std = float(np.std(finite))
        if np.allclose(finite, 0.0):
            flags.append("all_zero")
        if std < 1e-6:
            flags.append("all_constant")
        if looks_like_preview_values(array):
            flags.append("preview_intensity_like_integer_values")
        if minimum < 0 or maximum > 80:
            flags.append("outside_typical_surface_temperature_review_range")
        if minimum < -80 or maximum > 200:
            flags.append("outside_broad_celsius_plausibility_range")
    blocking = {"no_finite_values", "all_zero", "all_constant", "outside_broad_celsius_plausibility_range"}
    status = "fail" if any(flag in blocking for flag in flags) else "pass"
    if status == "pass" and flags:
        status = "warn"
    return status, flags


def make_preview(array: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    finite = array[np.isfinite(array)]
    if finite.size == 0:
        rgb = np.zeros((*array.shape, 3), dtype=np.uint8)
    else:
        low, high = np.percentile(finite, [2, 98])
        if np.isclose(low, high):
            low, high = float(np.min(finite)), float(np.max(finite))
        if np.isclose(low, high):
            norm = np.zeros(array.shape, dtype=np.float32)
        else:
            norm = np.clip((array - low) / (high - low), 0.0, 1.0)
        anchors = np.array(
            [
                [32, 50, 112],
                [31, 145, 146],
                [238, 201, 87],
                [198, 67, 58],
            ],
            dtype=np.float32,
        )
        scaled = norm * (len(anchors) - 1)
        idx = np.floor(scaled).astype(int)
        idx = np.clip(idx, 0, len(anchors) - 2)
        frac = scaled - idx
        rgb_float = anchors[idx] * (1.0 - frac[..., None]) + anchors[idx + 1] * frac[..., None]
        rgb = np.clip(rgb_float, 0, 255).astype(np.uint8)
    Image.fromarray(rgb, mode="RGB").save(path)


def run_sdk_measure(
    tool: SdkTool,
    source: Path,
    raw_output: Path,
    config: dict[str, Any],
) -> tuple[bool, str]:
    if tool.irp_exe is None:
        return False, tool.message
    raw_output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(tool.irp_exe),
        "-s",
        str(source),
        "-a",
        "measure",
        "-o",
        str(raw_output),
        "--measurefmt",
        str(config["measure_format"]),
        "--distance",
        str(config["distance_m"]),
        "--humidity",
        str(config["relative_humidity_percent"]),
        "--emissivity",
        str(config["emissivity"]),
        "--ambient",
        str(config["ambient_temperature_c"]),
        "--reflection",
        str(config["reflected_temperature_c"]),
    ]
    result = subprocess.run(
        command,
        cwd=tool.irp_exe.parent,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    output = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
    if result.returncode != 0:
        return False, f"SDK exit code {result.returncode}: {output}"
    if not raw_output.is_file():
        return False, "SDK returned success but did not create the raw output file."
    return True, output


def read_temperature_raw(raw_path: Path, width: int, height: int) -> np.ndarray:
    array = np.fromfile(raw_path, dtype=np.float32)
    expected = width * height
    if array.size != expected:
        raise ValueError(
            f"Expected {expected} float32 values for {width}x{height}, got {array.size} from {relative_posix(raw_path)}"
        )
    return array.reshape((height, width))


def metadata_summary(meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "camera_model": meta.get("camera_model", ""),
        "thermal_image_width": meta.get("image_width", ""),
        "thermal_image_height": meta.get("image_height", ""),
        "thermal_image_type": meta.get("thermal_image_type", ""),
        "emissivity_metadata": meta.get("emissivity", ""),
        "object_distance_metadata": meta.get("object_distance", ""),
        "reflected_temperature_metadata": meta.get("reflected_apparent_temperature", ""),
        "ambient_temperature_metadata": meta.get("atmospheric_temperature", ""),
        "relative_humidity_metadata": meta.get("relative_humidity", ""),
        "temperature_unit_metadata": "",
    }


def build_manifest_rows(
    pairs: pd.DataFrame,
    metadata: pd.DataFrame,
    combined: pd.DataFrame,
    exiftool_status: str,
) -> list[dict[str, Any]]:
    combined_by_pair = {
        str(row["pair_id"]): row.to_dict()
        for _, row in combined.iterrows()
        if "pair_id" in combined.columns
    }
    rows: list[dict[str, Any]] = []
    for _, pair in pairs.iterrows():
        image_id = str(pair["image_id"])
        pair_id = str(pair["pair_id"])
        t_path = str(pair["t_path"])
        meta = metadata_for_t_image(metadata, t_path, image_id)
        combo = combined_by_pair.get(pair_id, {})
        class_mask = PROJECT_ROOT / "outputs" / "part_c" / "masks" / image_id / f"{image_id}_physical_surface_cover_class_id_thermal_grid.npy"
        shadow_mask = PROJECT_ROOT / "outputs" / "part_c" / "masks" / image_id / f"{image_id}_shadow_flag_thermal_grid.npy"
        row = {
            "pair_id": pair_id,
            "image_id": image_id,
            "t_path": t_path,
            "t_exists": resolve_project_path(t_path).is_file(),
            "part_b_t_image_width": pair.get("t_image_width", ""),
            "part_b_t_image_height": pair.get("t_image_height", ""),
            "part_c_class_mask_path": relative_posix(class_mask),
            "part_c_class_mask_exists": class_mask.is_file(),
            "part_c_shadow_mask_path": relative_posix(shadow_mask),
            "part_c_shadow_mask_exists": shadow_mask.is_file(),
            "dominant_luhk_class": combo.get("dominant_luhk_class", ""),
            "luhk_class_proportions": combo.get("luhk_class_proportions", ""),
            "part_c_surface_cover_proportions": combo.get("physical_surface_cover_class_proportions", ""),
            "part_c_shadow_percent": combo.get("shadow_percent", ""),
            "metadata_source": relative_posix(DJI_METADATA_XLSX),
            "exiftool_status": exiftool_status or "not_available_this_run",
        }
        row.update(metadata_summary(meta))
        rows.append(row)
    return rows


def write_dataframe_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def write_matrix_csv(path: Path, array: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savetxt(path, array, delimiter=",", fmt="%.3f")


def qa_by_class(
    image_id: str,
    pair_id: str,
    temps: np.ndarray,
    class_mask: np.ndarray,
    class_names: dict[int, str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    all_class_ids = sorted(set(class_names) | {int(value) for value in np.unique(class_mask)})
    finite = np.isfinite(temps)
    for class_id in all_class_ids:
        pixels = (class_mask == class_id) & finite
        values = temps[pixels]
        rows.append(
            {
                "pair_id": pair_id,
                "image_id": image_id,
                "class_id": class_id,
                "class_name": class_names.get(class_id, ""),
                "pixel_count": int((class_mask == class_id).sum()),
                "valid_temperature_pixel_count": int(values.size),
                "mean_temperature_c": float(np.mean(values)) if values.size else "",
                "median_temperature_c": float(np.median(values)) if values.size else "",
                "std_temperature_c": float(np.std(values)) if values.size else "",
                "qa_label": "QA statistics only, not final delta T analysis",
            }
        )
    return rows


def qa_by_shadow(image_id: str, pair_id: str, temps: np.ndarray, shadow_mask: np.ndarray) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    finite = np.isfinite(temps)
    for shadow_flag in [0, 1]:
        pixels = (shadow_mask == shadow_flag) & finite
        values = temps[pixels]
        rows.append(
            {
                "pair_id": pair_id,
                "image_id": image_id,
                "shadow_flag": shadow_flag,
                "pixel_count": int((shadow_mask == shadow_flag).sum()),
                "valid_temperature_pixel_count": int(values.size),
                "mean_temperature_c": float(np.mean(values)) if values.size else "",
                "median_temperature_c": float(np.median(values)) if values.size else "",
                "std_temperature_c": float(np.std(values)) if values.size else "",
                "qa_label": "QA statistics only, not final delta T analysis",
            }
        )
    return rows


def write_extraction_metadata(
    path: Path,
    pair: pd.Series,
    tool: SdkTool,
    config: dict[str, Any],
    stats: dict[str, Any],
    sdk_output: str,
) -> None:
    payload = {
        "pair_id": str(pair["pair_id"]),
        "image_id": str(pair["image_id"]),
        "t_path": str(pair["t_path"]),
        "temperature_unit": "degrees Celsius, interpreted from DJI Thermal SDK measure float32 output",
        "extraction_method": "DJI Thermal SDK dji_irp.exe measure --measurefmt float32",
        "sdk_root": external_sdk_label() if tool.sdk_root else "",
        "dji_irp_exe": "dji_irp.exe from external DJI Thermal SDK" if tool.irp_exe else "",
        "local_config_path": relative_posix(LOCAL_CONFIG),
        "sdk_version_text": tool.version_text,
        "measurement_parameters": {
            "distance_m": config["distance_m"],
            "relative_humidity_percent": config["relative_humidity_percent"],
            "emissivity": config["emissivity"],
            "ambient_temperature_c": config["ambient_temperature_c"],
            "reflected_temperature_c": config["reflected_temperature_c"],
        },
        "stats": stats,
        "sdk_output": sdk_output,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def build_summary_md(
    rows: list[dict[str, Any]],
    manifest_rows: list[dict[str, Any]],
    tool: SdkTool,
    exiftool_status: str,
) -> str:
    success_count = sum(row.get("extraction_status") == "success" for row in rows)
    align_count = sum(row.get("aligns_with_part_c_masks") == "yes" for row in rows)
    lines = [
        "# Part D Round 1 Temperature Extraction Summary",
        "",
        "## Scope",
        "",
        "- Tested the five accepted pilot `_T.JPG` images.",
        "- Used thermal temperature extraction only; no delta T modeling and no prediction modeling were run.",
        "- Treated RGB thermal previews as visualization only, never as temperature data.",
        "",
        "## Tool Status",
        "",
        f"- DJI Thermal SDK status: {tool.status}",
        f"- DJI Thermal SDK executable: `{external_sdk_label()}`" if tool.irp_exe else "- DJI Thermal SDK executable: not found",
        f"- DJI Thermal SDK root: `{external_sdk_label()}`" if tool.sdk_root else "- DJI Thermal SDK root: not found",
        f"- ExifTool status: {exiftool_status or 'not available in this run'}",
        f"- Local SDK config: `{relative_posix(LOCAL_CONFIG)}` (ignored by Git)",
        "",
        "## Results",
        "",
        f"- Pilot images tested: {len(rows)}",
        f"- Successful temperature matrices: {success_count}",
        f"- Matrices aligned with Part C masks: {align_count}",
        f"- Pilot input manifest: `{relative_posix(MANIFEST_CSV)}`",
        f"- Extraction summary CSV: `{relative_posix(SUMMARY_CSV)}`",
        f"- Class QA CSV: `{relative_posix(CLASS_QA_CSV)}`",
        f"- Shadow QA CSV: `{relative_posix(SHADOW_QA_CSV)}`",
        "",
        "## Per Image",
        "",
        "| image_id | status | shape | min C | max C | mean C | aligns with Part C masks | notes |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| {image_id} | {extraction_status} | {temperature_shape} | {temperature_min_c} | {temperature_max_c} | {temperature_mean_c} | {aligns_with_part_c_masks} | {notes} |".format(
                image_id=row.get("image_id", ""),
                extraction_status=row.get("extraction_status", ""),
                temperature_shape=row.get("temperature_shape", ""),
                temperature_min_c=row.get("temperature_min_c", ""),
                temperature_max_c=row.get("temperature_max_c", ""),
                temperature_mean_c=row.get("temperature_mean_c", ""),
                aligns_with_part_c_masks=row.get("aligns_with_part_c_masks", ""),
                notes=str(row.get("notes", "")).replace("|", "/"),
            )
        )
    lines.extend(
        [
            "",
            "## QA Boundary",
            "",
            "The class and shadow summaries are QA statistics only. They are intended to confirm extraction, shape alignment, and plausible values before any later delta T analysis.",
            "",
            "## Unresolved Setup Issues",
            "",
        ]
    )
    issues = sorted({str(row.get("notes", "")) for row in rows if row.get("extraction_status") != "success" and row.get("notes")})
    if not issues and tool.status == "available":
        lines.append("- None for SDK extraction in this run.")
    else:
        if tool.status != "available":
            lines.append(f"- {tool.message}")
        lines.extend(f"- {issue}" for issue in issues)
    lines.extend(
        [
            "",
            "## Recommended Next Steps",
            "",
            "- Review the preview PNGs and QA tables for physically implausible values.",
            "- Confirm measurement parameters such as emissivity, distance, humidity, ambient temperature, and reflected temperature before final analysis.",
            "- Keep the DJI SDK outside the repository and update only the ignored local config path if the SDK is moved.",
            "- Proceed to delta T analysis only after accepting these extraction outputs.",
            "",
        ]
    )
    return "\n".join(lines)


def update_doc(tool: SdkTool, exiftool_status: str, ran_rows: list[dict[str, Any]]) -> None:
    success_count = sum(row.get("extraction_status") == "success" for row in ran_rows)
    lines = [
        "# Part D Temperature Extraction",
        "",
        "Part D extracts pixel-level temperature matrices from the accepted pilot DJI thermal `_T.JPG` images and checks alignment with the Part C thermal-grid masks.",
        "",
        "## Dependency Rule",
        "",
        "Do not copy DJI Thermal SDK binaries into this repository. Install or unzip the SDK outside the repo, for example under `D:\\DJI_Thermal_SDK`, and point the project to it with an ignored local config file.",
        "",
        "Tracked template:",
        "",
        "```powershell",
        "config\\part_d_sdk.template.json",
        "```",
        "",
        "Ignored local config used on this machine:",
        "",
        "```powershell",
        "config\\part_d_sdk.local.json",
        "```",
        "",
        "The script also accepts `--sdk-root`, `--irp-exe`, `DJI_THERMAL_SDK_ROOT`, or `DJI_IRP_EXE`.",
        "",
        "## Current Tool Check",
        "",
        f"- DJI Thermal SDK status: `{tool.status}`",
        f"- DJI Thermal SDK root: `{external_sdk_label()}`" if tool.sdk_root else "- DJI Thermal SDK root: not found",
        f"- `dji_irp.exe`: `{external_sdk_label()}`" if tool.irp_exe else "- `dji_irp.exe`: not found",
        f"- ExifTool: `{exiftool_status}`" if exiftool_status else "- ExifTool: not found on PATH or known local paths during this run",
        "",
        "## Extraction Command",
        "",
        "```powershell",
        ".\\.venv\\Scripts\\python.exe scripts\\part_d\\01_extract_temperature_matrices.py",
        "```",
        "",
        "The script calls DJI `dji_irp.exe` with `-a measure --measurefmt float32`, reads the raw float32 output, reshapes it to the thermal grid from `data/metadata/part_b_pilot_pairs.xlsx`, and saves Celsius matrices.",
        "",
        "Default measurement parameters are explicit in the config template:",
        "",
        "- distance: 5.0 m",
        "- relative humidity: 70 percent",
        "- emissivity: 1.0",
        "- ambient temperature: 25 C",
        "- reflected temperature: 23 C",
        "",
        "These defaults should be reviewed before final analysis. Existing metadata inspection did not provide reliable per-image emissivity, object distance, reflected temperature, humidity, or temperature unit values for the pilot images.",
        "",
        "## Outputs",
        "",
        "- Temperature matrices: `data/processed/part_d/temperature_matrices/`",
        "- Preview PNGs: `outputs/part_d/previews/`",
        "- QA tables: `outputs/part_d/qa/`",
        "- Round 1 summaries: `outputs/part_d/summaries/`",
        "",
        "For each successful pilot image, the workflow writes `.npy`, optional matrix `.csv`, preview `.png`, and extraction metadata `.json` files.",
        "",
        "## QA Checks",
        "",
        "- Matrix shape matches the expected thermal grid.",
        "- Part C physical surface-cover mask shape matches the temperature matrix.",
        "- Part C `shadow_flag` mask shape matches the temperature matrix.",
        "- Temperature values are finite, non-constant, non-zero, and within a broad Celsius plausibility range.",
        "- Values outside a typical surface-temperature review range, such as below 0 C or above 80 C, are flagged for manual QA.",
        "- Integer-like 0 to 255 preview values are flagged as suspicious.",
        "",
        "The class and shadow summaries are QA statistics only. They are not final delta T analysis.",
        "",
        "## Current Run",
        "",
        f"- Successful matrices: {success_count}/{len(ran_rows)}",
        f"- Summary: `{relative_posix(SUMMARY_MD)}`",
        f"- Summary CSV: `{relative_posix(SUMMARY_CSV)}`",
        "",
        "## Limitations",
        "",
        "- Thermal extraction depends on DJI R-JPEG radiometric support in the external SDK.",
        "- The SDK readme for this installed version lists several supported cameras but also includes M4T sample data; pilot M4T extraction is accepted only if `dji_irp.exe` succeeds and QA values are plausible.",
        "- Measurement parameters may materially affect temperature values and should be confirmed for final work.",
        "- No delta T, statistical modeling, or prediction modeling is performed in Part D Round 1.",
        "",
    ]
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text("\n".join(lines), encoding="utf-8")


def process_pairs(config: dict[str, Any], tool: SdkTool, args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], str]:
    pairs, metadata, classes, combined = load_inputs()
    exiftool_status = find_exiftool()
    manifest_rows = build_manifest_rows(pairs, metadata, combined, exiftool_status)
    class_names = class_lookup(classes)
    summary_rows: list[dict[str, Any]] = []
    class_qa_rows: list[dict[str, Any]] = []
    shadow_qa_rows: list[dict[str, Any]] = []

    for _, pair in pairs.iterrows():
        image_id = str(pair["image_id"])
        pair_id = str(pair["pair_id"])
        t_path = resolve_project_path(pair["t_path"])
        width = clean_int(pair.get("t_image_width"))
        height = clean_int(pair.get("t_image_height"))
        class_mask_path = PROJECT_ROOT / "outputs" / "part_c" / "masks" / image_id / f"{image_id}_physical_surface_cover_class_id_thermal_grid.npy"
        shadow_mask_path = PROJECT_ROOT / "outputs" / "part_c" / "masks" / image_id / f"{image_id}_shadow_flag_thermal_grid.npy"
        npy_path = TEMPERATURE_DIR / f"{image_id}_temperature_celsius.npy"
        csv_path = TEMPERATURE_DIR / f"{image_id}_temperature_celsius.csv"
        raw_path = TEMPERATURE_DIR / "sdk_raw" / f"{image_id}_temperature_float32.raw"
        preview_path = PREVIEW_DIR / f"{image_id}_temperature_preview.png"
        metadata_path = TEMPERATURE_DIR / f"{image_id}_temperature_metadata.json"

        row: dict[str, Any] = {
            "pair_id": pair_id,
            "image_id": image_id,
            "t_path": relative_posix(t_path),
            "extraction_method": "DJI Thermal SDK dji_irp.exe measure float32",
            "temperature_unit": "Celsius interpreted from SDK measure output",
            "extraction_status": "not_run",
            "temperature_shape": "",
            "expected_thermal_shape": f"{height}x{width}" if width and height else "",
            "part_c_class_mask_shape": "",
            "part_c_shadow_mask_shape": "",
            "aligns_with_part_c_masks": "no",
            "temperature_min_c": "",
            "temperature_max_c": "",
            "temperature_mean_c": "",
            "temperature_median_c": "",
            "temperature_std_c": "",
            "nan_count": "",
            "invalid_count": "",
            "validation_status": "",
            "validation_flags": "",
            "npy_path": "",
            "csv_path": "",
            "preview_png_path": "",
            "metadata_json_path": "",
            "notes": "",
        }

        try:
            if tool.status != "available":
                raise RuntimeError(tool.message)
            if not t_path.is_file():
                raise FileNotFoundError(f"Missing pilot thermal image: {relative_posix(t_path)}")
            if width is None or height is None:
                with Image.open(t_path) as image:
                    width, height = image.size
                row["expected_thermal_shape"] = f"{height}x{width}"
            ok, sdk_output = run_sdk_measure(tool, t_path, raw_path, config)
            if not ok:
                raise RuntimeError(sdk_output)

            temps = read_temperature_raw(raw_path, width, height)
            status, flags = validation_flags(temps)
            stats = {
                "shape": list(temps.shape),
                "min_c": safe_stat(temps, "min"),
                "max_c": safe_stat(temps, "max"),
                "mean_c": safe_stat(temps, "mean"),
                "median_c": safe_stat(temps, "median"),
                "std_c": safe_stat(temps, "std"),
                "nan_count": safe_stat(temps, "nan_count"),
                "invalid_count": safe_stat(temps, "invalid_count"),
                "validation_status": status,
                "validation_flags": flags,
            }

            class_mask = np.load(class_mask_path)
            shadow_mask = np.load(shadow_mask_path)
            aligned = class_mask.shape == temps.shape and shadow_mask.shape == temps.shape
            if aligned:
                class_qa_rows.extend(qa_by_class(image_id, pair_id, temps, class_mask, class_names))
                shadow_qa_rows.extend(qa_by_shadow(image_id, pair_id, temps, shadow_mask))

            npy_path.parent.mkdir(parents=True, exist_ok=True)
            np.save(npy_path, temps.astype(np.float32))
            if bool(config.get("write_matrix_csv", True)):
                write_matrix_csv(csv_path, temps)
            make_preview(temps, preview_path)
            write_extraction_metadata(metadata_path, pair, tool, config, stats, sdk_output)

            row.update(
                {
                    "extraction_status": "success",
                    "temperature_shape": f"{temps.shape[0]}x{temps.shape[1]}",
                    "part_c_class_mask_shape": f"{class_mask.shape[0]}x{class_mask.shape[1]}",
                    "part_c_shadow_mask_shape": f"{shadow_mask.shape[0]}x{shadow_mask.shape[1]}",
                    "aligns_with_part_c_masks": "yes" if aligned else "no",
                    "temperature_min_c": round(float(stats["min_c"]), 6),
                    "temperature_max_c": round(float(stats["max_c"]), 6),
                    "temperature_mean_c": round(float(stats["mean_c"]), 6),
                    "temperature_median_c": round(float(stats["median_c"]), 6),
                    "temperature_std_c": round(float(stats["std_c"]), 6),
                    "nan_count": stats["nan_count"],
                    "invalid_count": stats["invalid_count"],
                    "validation_status": status,
                    "validation_flags": ";".join(flags),
                    "npy_path": relative_posix(npy_path),
                    "csv_path": relative_posix(csv_path) if csv_path.is_file() else "",
                    "preview_png_path": relative_posix(preview_path),
                    "metadata_json_path": relative_posix(metadata_path),
                    "notes": (
                        ("extracted and aligned" if aligned else "extracted but Part C mask shapes do not match")
                        + (f"; QA flags: {';'.join(flags)}" if flags else "")
                    ),
                }
            )

            if not bool(config.get("keep_sdk_raw", False)) and raw_path.is_file():
                raw_path.unlink()
        except Exception as exc:
            row["extraction_status"] = "failed"
            row["notes"] = str(exc)
        summary_rows.append(row)

    return summary_rows, manifest_rows, class_qa_rows, shadow_qa_rows, exiftool_status


def write_outputs(
    summary_rows: list[dict[str, Any]],
    manifest_rows: list[dict[str, Any]],
    class_qa_rows: list[dict[str, Any]],
    shadow_qa_rows: list[dict[str, Any]],
    tool: SdkTool,
    exiftool_status: str,
) -> None:
    for path in [TEMPERATURE_DIR, PREVIEW_DIR, QA_DIR, SUMMARY_DIR]:
        path.mkdir(parents=True, exist_ok=True)

    write_dataframe_csv(SUMMARY_CSV, summary_rows)
    write_dataframe_csv(MANIFEST_CSV, manifest_rows)
    write_rows(MANIFEST_XLSX, manifest_rows)
    write_dataframe_csv(CLASS_QA_CSV, class_qa_rows)
    write_rows(CLASS_QA_XLSX, class_qa_rows)
    write_dataframe_csv(SHADOW_QA_CSV, shadow_qa_rows)
    write_rows(SHADOW_QA_XLSX, shadow_qa_rows)
    SUMMARY_MD.write_text(build_summary_md(summary_rows, manifest_rows, tool, exiftool_status), encoding="utf-8")
    update_doc(tool, exiftool_status, summary_rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(LOCAL_CONFIG), help="Ignored local config JSON path.")
    parser.add_argument("--sdk-root", default="", help="External DJI Thermal SDK root.")
    parser.add_argument("--irp-exe", default="", help="Full path to external dji_irp.exe.")
    parser.add_argument("--no-matrix-csv", action="store_true", help="Skip full matrix CSV output.")
    parser.add_argument("--keep-sdk-raw", action="store_true", help="Keep intermediate SDK float32 raw files.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(Path(args.config))
    if args.no_matrix_csv:
        config["write_matrix_csv"] = False
    if args.keep_sdk_raw:
        config["keep_sdk_raw"] = True
    if str(config.get("measure_format", "")).casefold() != "float32":
        raise ValueError("Part D Round 1 expects measure_format=float32.")

    tool = detect_sdk(config, args)
    summary_rows, manifest_rows, class_qa_rows, shadow_qa_rows, exiftool_status = process_pairs(config, tool, args)
    write_outputs(summary_rows, manifest_rows, class_qa_rows, shadow_qa_rows, tool, exiftool_status)

    success_count = sum(row.get("extraction_status") == "success" for row in summary_rows)
    print(f"DJI Thermal SDK status: {tool.status}")
    print(f"Pilot images processed: {len(summary_rows)}")
    print(f"Successful temperature matrices: {success_count}")
    print(f"Summary: {relative_posix(SUMMARY_MD)}")
    print(f"Summary CSV: {relative_posix(SUMMARY_CSV)}")
    return 0 if success_count == len(summary_rows) else 1


if __name__ == "__main__":
    sys.exit(main())
