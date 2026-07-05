#!/usr/bin/env python3
"""Extract DJI image metadata for visible/thermal image pairs."""

from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


BATCH_SIZE = 100

INPUT_CSV_NAME = Path("data") / "metadata" / "vt_pairs.csv"
OUTPUT_CSV_NAME = Path("data") / "metadata" / "dji_image_metadata.csv"
SUMMARY_TXT_NAME = (
    Path("outputs") / "reports" / "02_extract_dji_metadata_summary.txt"
)

NOTES = (
    "Metadata extraction table for the first-pass geospatial workflow; "
    "footprint and grid estimation will be handled in a later script. "
    "Terrain elevation is unknown and not resolved in this script."
)

OUTPUT_COLUMNS = [
    "source_file",
    "image_path",
    "image_name",
    "image_type",
    "pair_id",
    "pair_status",
    "parent_folder",
    "capture_datetime",
    "gps_latitude",
    "gps_longitude",
    "gps_altitude",
    "absolute_altitude",
    "relative_altitude",
    "gimbal_pitch_degree",
    "gimbal_yaw_degree",
    "gimbal_roll_degree",
    "flight_pitch_degree",
    "flight_yaw_degree",
    "flight_roll_degree",
    "image_width",
    "image_height",
    "focal_length",
    "focal_length_35mm",
    "aperture",
    "f_number",
    "camera_model",
    "make",
    "model",
    "serial_number",
    "thermal_image_type",
    "emissivity",
    "object_distance",
    "reflected_apparent_temperature",
    "atmospheric_temperature",
    "relative_humidity",
    "ir_window_temperature",
    "ir_window_transmission",
    "assumed_focal_length_mm",
    "assumed_aperture",
    "assumed_image_top_is_north",
    "assumed_nadir_view",
    "assumed_gps_as_image_center",
    "terrain_elevation_known",
    "notes",
]

TAG_ALIASES = {
    "capture_datetime": [
        "DateTimeOriginal",
        "SubSecDateTimeOriginal",
        "CreateDate",
        "MediaCreateDate",
        "TrackCreateDate",
        "GPSDateTime",
        "ModifyDate",
        "FileModifyDate",
        "EXIF:DateTimeOriginal",
        "EXIF:CreateDate",
        "Composite:SubSecDateTimeOriginal",
    ],
    "gps_latitude": [
        "GPSLatitude",
        "GPS Latitude",
        "EXIF:GPSLatitude",
        "Composite:GPSLatitude",
        "XMP:GPSLatitude",
    ],
    "gps_latitude_ref": [
        "GPSLatitudeRef",
        "GPS Latitude Ref",
        "EXIF:GPSLatitudeRef",
    ],
    "gps_longitude": [
        "GPSLongitude",
        "GPS Longitude",
        "EXIF:GPSLongitude",
        "Composite:GPSLongitude",
        "XMP:GPSLongitude",
    ],
    "gps_longitude_ref": [
        "GPSLongitudeRef",
        "GPS Longitude Ref",
        "EXIF:GPSLongitudeRef",
    ],
    "gps_altitude": [
        "GPSAltitude",
        "GPS Altitude",
        "EXIF:GPSAltitude",
        "Composite:GPSAltitude",
    ],
    "absolute_altitude": [
        "AbsoluteAltitude",
        "Absolute Altitude",
        "XMP:AbsoluteAltitude",
        "XMP-drone-dji:AbsoluteAltitude",
        "Drone-dji:AbsoluteAltitude",
    ],
    "relative_altitude": [
        "RelativeAltitude",
        "Relative Altitude",
        "XMP:RelativeAltitude",
        "XMP-drone-dji:RelativeAltitude",
        "Drone-dji:RelativeAltitude",
    ],
    "gimbal_pitch_degree": [
        "GimbalPitchDegree",
        "Gimbal Pitch Degree",
        "GimbalPitch",
        "XMP:GimbalPitchDegree",
        "XMP-drone-dji:GimbalPitchDegree",
        "Drone-dji:GimbalPitchDegree",
    ],
    "gimbal_yaw_degree": [
        "GimbalYawDegree",
        "Gimbal Yaw Degree",
        "GimbalYaw",
        "XMP:GimbalYawDegree",
        "XMP-drone-dji:GimbalYawDegree",
        "Drone-dji:GimbalYawDegree",
    ],
    "gimbal_roll_degree": [
        "GimbalRollDegree",
        "Gimbal Roll Degree",
        "GimbalRoll",
        "XMP:GimbalRollDegree",
        "XMP-drone-dji:GimbalRollDegree",
        "Drone-dji:GimbalRollDegree",
    ],
    "flight_pitch_degree": [
        "FlightPitchDegree",
        "Flight Pitch Degree",
        "FlightPitch",
        "XMP:FlightPitchDegree",
        "XMP-drone-dji:FlightPitchDegree",
        "Drone-dji:FlightPitchDegree",
    ],
    "flight_yaw_degree": [
        "FlightYawDegree",
        "Flight Yaw Degree",
        "FlightYaw",
        "XMP:FlightYawDegree",
        "XMP-drone-dji:FlightYawDegree",
        "Drone-dji:FlightYawDegree",
    ],
    "flight_roll_degree": [
        "FlightRollDegree",
        "Flight Roll Degree",
        "FlightRoll",
        "XMP:FlightRollDegree",
        "XMP-drone-dji:FlightRollDegree",
        "Drone-dji:FlightRollDegree",
    ],
    "image_width": [
        "ImageWidth",
        "Image Width",
        "ExifImageWidth",
        "SourceImageWidth",
        "File:ImageWidth",
        "EXIF:ExifImageWidth",
    ],
    "image_height": [
        "ImageHeight",
        "Image Height",
        "ExifImageHeight",
        "SourceImageHeight",
        "File:ImageHeight",
        "EXIF:ExifImageHeight",
    ],
    "focal_length": [
        "FocalLength",
        "Focal Length",
        "EXIF:FocalLength",
    ],
    "focal_length_35mm": [
        "FocalLengthIn35mmFormat",
        "Focal Length In 35mm Format",
        "FocalLength35mm",
        "Focal Length 35mm",
        "EXIF:FocalLengthIn35mmFormat",
    ],
    "aperture": [
        "Aperture",
        "ApertureValue",
        "Aperture Value",
        "Composite:Aperture",
        "EXIF:ApertureValue",
    ],
    "f_number": [
        "FNumber",
        "F Number",
        "F-Number",
        "EXIF:FNumber",
    ],
    "camera_model": [
        "CameraModelName",
        "Camera Model Name",
        "Model",
        "EXIF:Model",
    ],
    "make": [
        "Make",
        "EXIF:Make",
    ],
    "model": [
        "Model",
        "EXIF:Model",
    ],
    "serial_number": [
        "SerialNumber",
        "Serial Number",
        "CameraSerialNumber",
        "Camera Serial Number",
        "InternalSerialNumber",
        "BodySerialNumber",
        "DroneSerialNumber",
        "FlightControllerSerialNumber",
        "EXIF:SerialNumber",
    ],
    "thermal_image_type": [
        "ThermalImageType",
        "Thermal Image Type",
        "RawThermalImageType",
        "Raw Thermal Image Type",
    ],
    "emissivity": [
        "Emissivity",
        "ThermalEmissivity",
        "Thermal Emissivity",
    ],
    "object_distance": [
        "ObjectDistance",
        "Object Distance",
        "SubjectDistance",
        "Subject Distance",
    ],
    "reflected_apparent_temperature": [
        "ReflectedApparentTemperature",
        "Reflected Apparent Temperature",
        "ReflectedTemperature",
        "Reflected Temperature",
    ],
    "atmospheric_temperature": [
        "AtmosphericTemperature",
        "Atmospheric Temperature",
        "AmbientTemperature",
        "Ambient Temperature",
    ],
    "relative_humidity": [
        "RelativeHumidity",
        "Relative Humidity",
        "Humidity",
    ],
    "ir_window_temperature": [
        "IRWindowTemperature",
        "IR Window Temperature",
    ],
    "ir_window_transmission": [
        "IRWindowTransmission",
        "IR Window Transmission",
    ],
}

FLOAT_RE = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")
DATE_PREFIX_RE = re.compile(r"^(\d{4}):(\d{2}):(\d{2})(.*)$")


def project_root() -> Path:
    """Return the repository root based on this script location."""
    return Path(__file__).resolve().parents[1]


def exiftool_candidates() -> list[str]:
    """Return ExifTool candidates in the preferred search order."""
    root = project_root()
    return [
        "exiftool",
        "exiftool.exe",
        str(root / "exiftool.exe"),
        str(root / "exiftool-13.59_64" / "exiftool.exe"),
        r"D:\exiftool-13.59_64\exiftool.exe",
    ]


def check_exiftool_available() -> str | None:
    """Return the first working ExifTool candidate."""
    for candidate in exiftool_candidates():
        try:
            result = subprocess.run(
                [candidate, "-ver"],
                cwd=project_root(),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                check=False,
            )
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            continue

        if result.returncode == 0 and result.stdout.strip():
            print(f"Using ExifTool: {candidate}")
            return candidate

    print(
        "Error: ExifTool was not found. The script checked these candidates:\n"
        + "\n".join(f"- {candidate}" for candidate in exiftool_candidates())
        + "\nInstall ExifTool or place it in one of the listed locations.",
        file=sys.stderr,
    )
    return None


def relative_posix(path: Path) -> str:
    """Return a project-relative POSIX path when possible."""
    root = project_root()
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def load_vt_pairs(input_csv: Path) -> list[dict[str, str]]:
    """Load the visible/thermal pair table."""
    if not input_csv.is_file():
        raise FileNotFoundError(f"Input pair table does not exist: {input_csv}")

    with input_csv.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        rows = list(reader)

    required_columns = {"pair_id", "v_path", "t_path", "status"}
    missing_columns = required_columns.difference(reader.fieldnames or [])
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Input pair table is missing required columns: {missing}")

    return rows


def resolve_listed_path(path_text: str) -> Path:
    """Resolve a path from vt_pairs.csv relative to the project root."""
    path = Path(path_text.strip())
    if path.is_absolute():
        return path
    return project_root() / path


def collect_image_records_from_pairs(
    rows: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[str]]:
    """Collect unique existing image files from visible and thermal columns."""
    records_by_path: dict[str, dict[str, str]] = {}
    missing_paths: dict[str, str] = {}

    for row in rows:
        for column, image_type in (("v_path", "visible"), ("t_path", "thermal")):
            raw_path = (row.get(column) or "").strip()
            if not raw_path:
                continue

            image_file = resolve_listed_path(raw_path)
            image_path = relative_posix(image_file)
            if not image_file.is_file():
                missing_paths[image_path] = image_path
                continue

            if image_path in records_by_path:
                continue

            records_by_path[image_path] = {
                "image_path": image_path,
                "image_name": image_file.name,
                "image_type": image_type,
                "pair_id": row.get("pair_id", ""),
                "pair_status": row.get("status", ""),
                "parent_folder": Path(image_path).parent.as_posix(),
            }

    return list(records_by_path.values()), sorted(missing_paths)


def normalize_source_key(source_file: Any) -> str:
    """Normalize an ExifTool SourceFile value for matching and output."""
    if is_missing(source_file):
        return ""

    source_text = str(scalar_value(source_file)).strip().replace("\\", "/")
    while source_text.startswith("./"):
        source_text = source_text[2:]

    source_path = Path(source_text)
    if source_path.is_absolute():
        return relative_posix(source_path)
    return source_text


def canonical_path_key(path_text: str) -> str:
    """Return a case-insensitive path key for matching ExifTool output."""
    return normalize_source_key(path_text).casefold()


def run_exiftool_batch(
    exiftool: str,
    image_records: list[dict[str, str]],
    batch_size: int = BATCH_SIZE,
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Run ExifTool in batches and return metadata plus per-file failures."""
    metadata_by_path: dict[str, dict[str, Any]] = {}
    failed_files: dict[str, str] = {}
    total = len(image_records)

    for start in range(0, total, batch_size):
        batch = image_records[start : start + batch_size]
        end = start + len(batch)
        print(f"Running ExifTool for images {start + 1}-{end} of {total}...")
        batch_metadata, batch_failures = run_exiftool_one_batch(exiftool, batch)
        metadata_by_path.update(batch_metadata)
        failed_files.update(batch_failures)

    return metadata_by_path, failed_files


def run_exiftool_one_batch(
    exiftool: str,
    batch: list[dict[str, str]],
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Run one ExifTool JSON command, falling back to single-file batches."""
    command = [exiftool, "-json", *[record["image_path"] for record in batch]]
    result = subprocess.run(
        command,
        cwd=project_root(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    if not stdout:
        if len(batch) > 1:
            return run_exiftool_individually(exiftool, batch)
        return {}, {
            batch[0]["image_path"]: clean_message(
                stderr or "ExifTool returned no JSON output."
            )
        }

    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError as exc:
        if len(batch) > 1:
            return run_exiftool_individually(exiftool, batch)
        return {}, {
            batch[0]["image_path"]: clean_message(
                f"Unable to parse ExifTool JSON: {exc}; stderr: {stderr}"
            )
        }

    if not isinstance(parsed, list):
        return {}, {
            record["image_path"]: "ExifTool JSON output was not a list."
            for record in batch
        }

    return match_exiftool_output_to_records(parsed, batch)


def run_exiftool_individually(
    exiftool: str,
    batch: list[dict[str, str]],
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Retry a failed batch one image at a time."""
    metadata_by_path: dict[str, dict[str, Any]] = {}
    failed_files: dict[str, str] = {}

    for record in batch:
        single_metadata, single_failures = run_exiftool_one_batch(exiftool, [record])
        metadata_by_path.update(single_metadata)
        failed_files.update(single_failures)

    return metadata_by_path, failed_files


def match_exiftool_output_to_records(
    parsed: list[Any],
    batch: list[dict[str, str]],
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Match ExifTool JSON objects back to input image records."""
    metadata_by_path: dict[str, dict[str, Any]] = {}
    failed_files: dict[str, str] = {}
    expected_by_key = {
        canonical_path_key(record["image_path"]): record["image_path"]
        for record in batch
    }
    seen_paths: set[str] = set()

    for index, item in enumerate(parsed):
        if not isinstance(item, dict):
            if index < len(batch):
                failed_files[batch[index]["image_path"]] = (
                    "ExifTool returned a non-object JSON item."
                )
            continue

        source_key = canonical_path_key(item.get("SourceFile", ""))
        image_path = expected_by_key.get(source_key)
        if not image_path and index < len(batch):
            image_path = batch[index]["image_path"]
        if not image_path:
            continue

        seen_paths.add(image_path)
        error = first_available(item, ["Error"])
        if not is_missing(error):
            failed_files[image_path] = clean_message(str(scalar_value(error)))
            continue

        metadata_by_path[image_path] = item

    for record in batch:
        image_path = record["image_path"]
        if image_path not in seen_paths:
            failed_files[image_path] = "ExifTool returned no metadata for this file."

    return metadata_by_path, failed_files


def normalize_tag_name(tag_name: str) -> str:
    """Normalize tag names so grouped/spaced variants can be compared."""
    ungrouped = tag_name.split(":")[-1]
    return re.sub(r"[^a-z0-9]", "", ungrouped.casefold())


def first_available(meta: dict[str, Any], keys: list[str]) -> Any:
    """Return the first non-empty value for a list of possible tag names."""
    for key in keys:
        if key in meta and not is_missing(meta[key]):
            return meta[key]

    lower_to_actual = {actual.casefold(): actual for actual in meta}
    for key in keys:
        actual = lower_to_actual.get(key.casefold())
        if actual is not None and not is_missing(meta[actual]):
            return meta[actual]

    normalized_to_actual: dict[str, str] = {}
    for actual in meta:
        normalized_to_actual.setdefault(normalize_tag_name(actual), actual)

    for key in keys:
        actual = normalized_to_actual.get(normalize_tag_name(key))
        if actual is not None and not is_missing(meta[actual]):
            return meta[actual]

    return None


def is_missing(value: Any) -> bool:
    """Return True when a metadata value should be treated as missing."""
    if value is None:
        return True
    if isinstance(value, list):
        return all(is_missing(item) for item in value)
    if isinstance(value, str):
        return value.strip() == ""
    return False


def scalar_value(value: Any) -> Any:
    """Return the first non-empty scalar value from ExifTool JSON output."""
    if isinstance(value, list):
        for item in value:
            if not is_missing(item):
                return item
        return None
    return value


def text_value(value: Any) -> str:
    """Return a stripped string value, or blank for missing values."""
    value = scalar_value(value)
    if is_missing(value):
        return ""
    return str(value).strip()


def parse_float(value: Any) -> float | None:
    """Parse numbers from ExifTool numeric values or strings with units."""
    value = scalar_value(value)
    if is_missing(value) or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip().replace("\u2212", "-")
    text = re.sub(r"(?<=\d),(?=\d)", "", text)
    match = FLOAT_RE.search(text)
    if not match:
        return None

    number = float(match.group(0))
    if "below sea" in text.casefold():
        return -abs(number)
    return number


def parse_gps_coordinate(value: Any, ref: Any = None) -> float | None:
    """Parse decimal or DMS GPS coordinates into decimal degrees."""
    value = scalar_value(value)
    if is_missing(value) or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        coordinate = float(value)
    else:
        text = str(value).strip().replace("\u2212", "-")
        hemisphere_match = re.search(r"([NSEW])\s*$", text, re.IGNORECASE)
        hemisphere = hemisphere_match.group(1).upper() if hemisphere_match else ""
        text_without_hemisphere = re.sub(
            r"([NSEW])\s*$", "", text, flags=re.IGNORECASE
        )
        numbers = [
            float(match.group(0))
            for match in FLOAT_RE.finditer(text_without_hemisphere)
        ]
        if not numbers:
            return None

        looks_like_dms = (
            any(
                marker in text_without_hemisphere.casefold()
                for marker in ("deg", "'", '"')
            )
            or len(numbers) >= 3
        )
        if looks_like_dms:
            sign = -1 if numbers[0] < 0 else 1
            degrees = abs(numbers[0])
            minutes = abs(numbers[1]) if len(numbers) > 1 else 0.0
            seconds = abs(numbers[2]) if len(numbers) > 2 else 0.0
            coordinate = sign * (degrees + minutes / 60.0 + seconds / 3600.0)
        else:
            coordinate = numbers[0]

        if hemisphere:
            coordinate = apply_hemisphere(coordinate, hemisphere)

    ref_text = text_value(ref).upper()
    if ref_text:
        ref_hemisphere = ref_text[0]
        if ref_hemisphere in {"N", "S", "E", "W"}:
            coordinate = apply_hemisphere(coordinate, ref_hemisphere)

    return coordinate


def apply_hemisphere(coordinate: float, hemisphere: str) -> float:
    """Apply N/S/E/W hemisphere sign to a coordinate."""
    if hemisphere in {"S", "W"}:
        return -abs(coordinate)
    if hemisphere in {"N", "E"}:
        return abs(coordinate)
    return coordinate


def parse_datetime(value: Any) -> str:
    """Normalize common ExifTool date strings while preserving time zones."""
    text = text_value(value)
    if not text:
        return ""

    match = DATE_PREFIX_RE.match(text)
    if match:
        year, month, day, rest = match.groups()
        return f"{year}-{month}-{day}{rest}"
    return text


def normalize_metadata_record(
    image_record: dict[str, str],
    meta: dict[str, Any],
) -> dict[str, Any]:
    """Normalize one ExifTool metadata object into the output schema."""
    source_file = normalize_source_key(
        first_available(meta, ["SourceFile"]) or image_record["image_path"]
    )
    gps_latitude = parse_gps_coordinate(
        first_available(meta, TAG_ALIASES["gps_latitude"]),
        first_available(meta, TAG_ALIASES["gps_latitude_ref"]),
    )
    gps_longitude = parse_gps_coordinate(
        first_available(meta, TAG_ALIASES["gps_longitude"]),
        first_available(meta, TAG_ALIASES["gps_longitude_ref"]),
    )

    return {
        "source_file": source_file or image_record["image_path"],
        "image_path": image_record["image_path"],
        "image_name": image_record["image_name"],
        "image_type": image_record["image_type"],
        "pair_id": image_record["pair_id"],
        "pair_status": image_record["pair_status"],
        "parent_folder": image_record["parent_folder"],
        "capture_datetime": parse_datetime(
            first_available(meta, TAG_ALIASES["capture_datetime"])
        ),
        "gps_latitude": gps_latitude,
        "gps_longitude": gps_longitude,
        "gps_altitude": parse_float(first_available(meta, TAG_ALIASES["gps_altitude"])),
        "absolute_altitude": parse_float(
            first_available(meta, TAG_ALIASES["absolute_altitude"])
        ),
        "relative_altitude": parse_float(
            first_available(meta, TAG_ALIASES["relative_altitude"])
        ),
        "gimbal_pitch_degree": parse_float(
            first_available(meta, TAG_ALIASES["gimbal_pitch_degree"])
        ),
        "gimbal_yaw_degree": parse_float(
            first_available(meta, TAG_ALIASES["gimbal_yaw_degree"])
        ),
        "gimbal_roll_degree": parse_float(
            first_available(meta, TAG_ALIASES["gimbal_roll_degree"])
        ),
        "flight_pitch_degree": parse_float(
            first_available(meta, TAG_ALIASES["flight_pitch_degree"])
        ),
        "flight_yaw_degree": parse_float(
            first_available(meta, TAG_ALIASES["flight_yaw_degree"])
        ),
        "flight_roll_degree": parse_float(
            first_available(meta, TAG_ALIASES["flight_roll_degree"])
        ),
        "image_width": parse_float(first_available(meta, TAG_ALIASES["image_width"])),
        "image_height": parse_float(first_available(meta, TAG_ALIASES["image_height"])),
        "focal_length": parse_float(first_available(meta, TAG_ALIASES["focal_length"])),
        "focal_length_35mm": parse_float(
            first_available(meta, TAG_ALIASES["focal_length_35mm"])
        ),
        "aperture": parse_float(first_available(meta, TAG_ALIASES["aperture"])),
        "f_number": parse_float(first_available(meta, TAG_ALIASES["f_number"])),
        "camera_model": text_value(first_available(meta, TAG_ALIASES["camera_model"])),
        "make": text_value(first_available(meta, TAG_ALIASES["make"])),
        "model": text_value(first_available(meta, TAG_ALIASES["model"])),
        "serial_number": text_value(
            first_available(meta, TAG_ALIASES["serial_number"])
        ),
        "thermal_image_type": text_value(
            first_available(meta, TAG_ALIASES["thermal_image_type"])
        ),
        "emissivity": parse_float(first_available(meta, TAG_ALIASES["emissivity"])),
        "object_distance": parse_float(
            first_available(meta, TAG_ALIASES["object_distance"])
        ),
        "reflected_apparent_temperature": parse_float(
            first_available(meta, TAG_ALIASES["reflected_apparent_temperature"])
        ),
        "atmospheric_temperature": parse_float(
            first_available(meta, TAG_ALIASES["atmospheric_temperature"])
        ),
        "relative_humidity": parse_float(
            first_available(meta, TAG_ALIASES["relative_humidity"])
        ),
        "ir_window_temperature": parse_float(
            first_available(meta, TAG_ALIASES["ir_window_temperature"])
        ),
        "ir_window_transmission": parse_float(
            first_available(meta, TAG_ALIASES["ir_window_transmission"])
        ),
        "assumed_focal_length_mm": (
            12 if image_record["image_type"] == "thermal" else None
        ),
        "assumed_aperture": (
            1.0 if image_record["image_type"] == "thermal" else None
        ),
        "assumed_image_top_is_north": True,
        "assumed_nadir_view": True,
        "assumed_gps_as_image_center": True,
        "terrain_elevation_known": False,
        "notes": NOTES,
    }


def count_present(rows: list[dict[str, Any]], column: str) -> int:
    """Count rows with a non-empty value in a column."""
    return sum(not is_missing(row.get(column)) for row in rows)


def build_summary_lines(
    total_pair_rows: int,
    image_records: list[dict[str, str]],
    metadata_rows: list[dict[str, Any]],
    failed_files: dict[str, str],
    missing_paths: list[str],
    output_csv: Path,
) -> list[str]:
    """Build a plain-text extraction summary."""
    gps_count = sum(
        not is_missing(row.get("gps_latitude"))
        and not is_missing(row.get("gps_longitude"))
        for row in metadata_rows
    )
    gimbal_pitch_yaw_count = sum(
        not is_missing(row.get("gimbal_pitch_degree"))
        and not is_missing(row.get("gimbal_yaw_degree"))
        for row in metadata_rows
    )

    lines = [
        "DJI image metadata extraction summary",
        "",
        f"total rows in vt_pairs.csv: {total_pair_rows}",
        f"number of unique image files found: {len(image_records)}",
        f"number of metadata rows successfully extracted: {len(metadata_rows)}",
        f"number of failed files: {len(failed_files)}",
        f"number of images with GPS coordinates: {gps_count}",
        (
            "number of images with relative altitude: "
            f"{count_present(metadata_rows, 'relative_altitude')}"
        ),
        f"number of images with gimbal pitch/yaw: {gimbal_pitch_yaw_count}",
        f"output CSV path: {relative_posix(output_csv)}",
    ]

    if missing_paths:
        lines.extend(
            [
                f"number of listed image paths missing on disk: {len(missing_paths)}",
                "",
                "listed image paths missing on disk:",
            ]
        )
        lines.extend(f"- {path}" for path in missing_paths[:50])
        if len(missing_paths) > 50:
            lines.append(f"- ... {len(missing_paths) - 50} more")

    if failed_files:
        lines.extend(["", "failed files:"])
        for image_path, reason in sorted(failed_files.items()):
            lines.append(f"- {image_path}: {reason}")

    return lines


def csv_ready_row(row: dict[str, Any]) -> dict[str, Any]:
    """Convert None values to blanks before CSV writing."""
    ready: dict[str, Any] = {}
    for column in OUTPUT_COLUMNS:
        value = row.get(column)
        ready[column] = "" if value is None else value
    return ready


def write_outputs(
    metadata_rows: list[dict[str, Any]],
    summary_lines: list[str],
    output_csv: Path,
    summary_txt: Path,
) -> None:
    """Write the metadata CSV and summary report."""
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    summary_txt.parent.mkdir(parents=True, exist_ok=True)

    with output_csv.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(csv_ready_row(row) for row in metadata_rows)

    summary_txt.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")


def clean_message(message: str, max_length: int = 300) -> str:
    """Make subprocess failure messages compact enough for reports."""
    compact = " ".join(message.split())
    if len(compact) <= max_length:
        return compact
    return compact[: max_length - 3] + "..."


def print_next_command() -> None:
    """Print the command the user should run for this extraction step."""
    print()
    print("Next suggested command:")
    print(r"python scripts\02_extract_dji_metadata.py")


def main() -> int:
    root = project_root()
    input_csv = root / INPUT_CSV_NAME
    output_csv = root / OUTPUT_CSV_NAME
    summary_txt = root / SUMMARY_TXT_NAME

    print(f"Input pair table: {relative_posix(input_csv)}")
    try:
        pair_rows = load_vt_pairs(input_csv)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    image_records, missing_paths = collect_image_records_from_pairs(pair_rows)
    print(f"Rows in pair table: {len(pair_rows)}")
    print(f"Unique existing image files to process: {len(image_records)}")
    if missing_paths:
        print(f"Listed image paths missing on disk and skipped: {len(missing_paths)}")

    metadata_rows: list[dict[str, Any]] = []
    failed_files: dict[str, str] = {}
    if image_records:
        exiftool = check_exiftool_available()
        if not exiftool:
            return 1

        metadata_by_path, failed_files = run_exiftool_batch(exiftool, image_records)
        for image_record in image_records:
            image_path = image_record["image_path"]
            meta = metadata_by_path.get(image_path)
            if meta is None:
                continue
            metadata_rows.append(normalize_metadata_record(image_record, meta))

    summary_lines = build_summary_lines(
        total_pair_rows=len(pair_rows),
        image_records=image_records,
        metadata_rows=metadata_rows,
        failed_files=failed_files,
        missing_paths=missing_paths,
        output_csv=output_csv,
    )
    write_outputs(metadata_rows, summary_lines, output_csv, summary_txt)

    print()
    for line in summary_lines:
        print(line)
    print(f"Summary text path: {relative_posix(summary_txt)}")
    print_next_command()
    return 0


if __name__ == "__main__":
    sys.exit(main())
