"""Camera-profile assumptions for DJI visible and thermal workflows.

The LUHK overlay scripts handle two different target image geometries:

* visible `_V.JPG` overlays use the visible image file and visible camera
  metadata/profile.
* thermal `_T.JPG` grids or thermal plots use the thermal image file and
  thermal camera metadata/profile.

Do not reuse `thermal_profile` for a visible overlay unless a script explicitly
labels the output as a diagnostic comparison.
"""

from __future__ import annotations

import math
from typing import Any


FULL_FRAME_WIDTH_MM = 36.0
FULL_FRAME_HEIGHT_MM = 24.0
FULL_FRAME_DIAGONAL_MM = math.hypot(FULL_FRAME_WIDTH_MM, FULL_FRAME_HEIGHT_MM)

thermal_profile = {
    "name": "thermal_profile",
    "target_image_type": "thermal",
    "target_suffix": "_T.JPG",
    "expected_resolution_px": (640, 512),
    "fallback_focal_length_mm": 12.0,
    "fallback_focal_length_35mm": 53.0,
    "fallback_aperture_f_number": 1.0,
    "fallback_horizontal_fov_deg": 61.0,
    "fallback_vertical_fov_deg": 48.0,
    "fallback_sensor_width_mm": None,
    "fallback_sensor_height_mm": None,
    "approximate": True,
    "notes": (
        "Thermal fallback profile for _T.JPG thermal-grid, temperature-matrix, "
        "or plots drawn directly on thermal images. The f/1.0 aperture may be "
        "recorded in metadata but is ignored for ground-footprint estimation."
    ),
}

visible_profile = {
    "name": "visible_profile",
    "target_image_type": "visible",
    "target_suffix": "_V.JPG",
    "expected_resolution_px": None,
    "fallback_focal_length_mm": None,
    "fallback_focal_length_35mm": None,
    "fallback_aperture_f_number": None,
    "fallback_horizontal_fov_deg": None,
    "fallback_vertical_fov_deg": None,
    "fallback_sensor_width_mm": None,
    "fallback_sensor_height_mm": None,
    "approximate": True,
    "notes": (
        "DJI Matrice 4T has wide, medium tele, and tele visible cameras. Do not "
        "apply one fixed visible fallback. Identify the per-image visible camera "
        "from EXIF/XMP focal length and 35mm-equivalent focal length before "
        "footprint estimation."
    ),
}

MATRICE_4T_CAMERA_RULES = {
    "wide_visible": {
        "image_type": "visible",
        "actual_focal_length_mm": 6.7,
        "focal_length_35mm": 24.0,
        "f_number": 1.7,
        "sensor": '1/1.3" CMOS',
        "notes": "Wide-angle visible camera.",
    },
    "medium_tele_visible": {
        "image_type": "visible",
        "actual_focal_length_mm": 19.4,
        "focal_length_35mm": 70.0,
        "f_number": 2.8,
        "sensor": '1/1.3" CMOS',
        "notes": "Medium tele visible camera.",
    },
    "tele_visible": {
        "image_type": "visible",
        "actual_focal_length_mm": 40.0,
        "focal_length_35mm": 168.0,
        "f_number": 2.8,
        "sensor": '1/1.5" CMOS',
        "notes": "Tele visible camera.",
    },
    "thermal": {
        "image_type": "thermal",
        "actual_focal_length_mm": 12.0,
        "focal_length_35mm": 53.0,
        "f_number": 1.0,
        "sensor": "uncooled VOx microbolometer",
        "notes": "Infrared thermal camera; metadata may report 52-53 mm equivalent focal length.",
    },
}

CAMERA_PROFILES = {
    "thermal": thermal_profile,
    "visible": visible_profile,
}

FOV_COLUMN_CANDIDATES = {
    "horizontal": [
        "horizontal_fov_deg",
        "horizontal_fov",
        "HorizontalFOV",
        "Horizontal Field Of View",
        "FOVHorizontal",
    ],
    "vertical": [
        "vertical_fov_deg",
        "vertical_fov",
        "VerticalFOV",
        "Vertical Field Of View",
        "FOVVertical",
    ],
}

SENSOR_WIDTH_CANDIDATES = [
    "sensor_width",
    "sensor_width_mm",
    "SensorWidth",
    "Sensor Width",
    "SensorWidthMM",
]

SENSOR_HEIGHT_CANDIDATES = [
    "sensor_height",
    "sensor_height_mm",
    "SensorHeight",
    "Sensor Height",
    "SensorHeightMM",
]


def camera_profile_for_target(target_image_type: str) -> dict[str, Any]:
    """Return the camera profile for a target image type."""
    key = str(target_image_type).strip().casefold()
    if key not in CAMERA_PROFILES:
        choices = ", ".join(sorted(CAMERA_PROFILES))
        raise ValueError(f"Unknown target_image_type '{target_image_type}'. Expected one of: {choices}")
    return CAMERA_PROFILES[key]


def normalized_name(name: str) -> str:
    """Normalize a metadata column name for tolerant lookup."""
    return "".join(char for char in name.lower() if char.isalnum())


def row_keys(row: Any) -> list[str]:
    """Return a list of available row keys for dict-like or pandas rows."""
    if hasattr(row, "index"):
        return [str(key) for key in row.index]
    if hasattr(row, "keys"):
        return [str(key) for key in row.keys()]
    return []


def is_missing(value: Any) -> bool:
    """Return True when a metadata value should be treated as missing."""
    if value is None:
        return True
    try:
        if value != value:
            return True
    except (TypeError, ValueError):
        pass
    if isinstance(value, str):
        return value.strip() == ""
    return False


def first_existing_value(row: Any, candidates: list[str]) -> Any:
    """Return the first non-empty row value from possible metadata columns."""
    keys = row_keys(row)
    normalized_to_key = {normalized_name(key): key for key in keys}

    for candidate in candidates:
        if candidate in keys:
            value = row[candidate]
            if not is_missing(value):
                return value

    for candidate in candidates:
        key = normalized_to_key.get(normalized_name(candidate))
        if key is None:
            continue
        value = row[key]
        if not is_missing(value):
            return value

    return None


def parse_float(value: Any) -> float | None:
    """Parse a positive or signed float, preserving missing values as None."""
    if is_missing(value) or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def valid_positive(value: float | None) -> bool:
    """Return True for positive finite values."""
    return value is not None and math.isfinite(value) and value > 0


def approximately_equal(value: float | None, expected: float, tolerance: float = 1.0) -> bool:
    """Return True when a numeric metadata value is close to an expected value."""
    return value is not None and abs(value - expected) <= tolerance


def classify_matrice_4t_camera(row: Any) -> dict[str, Any]:
    """Classify a DJI Matrice 4T image camera from existing metadata.

    This is a preliminary metadata rule for later footprint and alignment work.
    It uses per-image EXIF/XMP focal length, 35mm-equivalent focal length, image
    type, and image dimensions. Callers should still treat the result as
    unvalidated until visual QA or vendor metadata checks confirm it.
    """
    image_type = str(first_existing_value(row, ["image_type", "ImageType"]) or "").casefold()
    focal_length = parse_float(first_existing_value(row, ["focal_length", "focal_length_mm", "FocalLength"]))
    focal_35mm = parse_float(
        first_existing_value(row, ["focal_length_35mm", "FocalLengthIn35mmFormat", "FocalLength35mm"])
    )
    image_width = parse_float(first_existing_value(row, ["image_width", "ImageWidth"]))
    image_height = parse_float(first_existing_value(row, ["image_height", "ImageHeight"]))

    if image_type == "thermal":
        if approximately_equal(focal_length, 12.0, 0.5) and (
            approximately_equal(focal_35mm, 53.0, 1.5) or approximately_equal(focal_35mm, 52.0, 1.5)
        ):
            return {
                "camera_key": "thermal",
                "confidence": "high",
                "reason": "thermal image with 12 mm actual focal length and approximately 52-53 mm 35mm-equivalent focal length",
            }
        return {
            "camera_key": "thermal_unconfirmed",
            "confidence": "needs_review",
            "reason": "thermal image type but focal-length metadata does not match the expected Matrice 4T thermal camera rule",
        }

    if image_type == "visible":
        visible_rules = ["wide_visible", "medium_tele_visible", "tele_visible"]
        for key in visible_rules:
            rule = MATRICE_4T_CAMERA_RULES[key]
            if approximately_equal(focal_35mm, float(rule["focal_length_35mm"]), 1.0):
                actual_match = approximately_equal(focal_length, float(rule["actual_focal_length_mm"]), 0.5)
                return {
                    "camera_key": key,
                    "confidence": "high" if actual_match else "medium",
                    "reason": (
                        f"visible image with {focal_35mm:g} mm 35mm-equivalent focal length"
                        + (" and matching actual focal length" if actual_match else "")
                    ),
                }
        return {
            "camera_key": "visible_unclassified",
            "confidence": "needs_review",
            "reason": (
                "visible image does not match expected Matrice 4T visible focal-length rules; "
                f"metadata focal_length={focal_length}, focal_length_35mm={focal_35mm}, "
                f"image_size={image_width}x{image_height}"
            ),
        }

    return {
        "camera_key": "unknown",
        "confidence": "needs_review",
        "reason": "missing or unknown image_type metadata",
    }


def fov_from_focal_and_sensor(
    focal_length_mm: float,
    sensor_width_mm: float,
    sensor_height_mm: float,
) -> tuple[float, float]:
    """Calculate horizontal and vertical FOV from focal length and sensor size."""
    horizontal = math.degrees(2.0 * math.atan(sensor_width_mm / (2.0 * focal_length_mm)))
    vertical = math.degrees(2.0 * math.atan(sensor_height_mm / (2.0 * focal_length_mm)))
    return horizontal, vertical


def sensor_size_from_35mm_equivalent(
    focal_length_mm: float,
    focal_length_35mm: float,
    image_width_px: float,
    image_height_px: float,
) -> tuple[float, float, float]:
    """Estimate sensor size from focal length, 35mm-equivalent focal length, and aspect."""
    crop_factor = focal_length_35mm / focal_length_mm
    sensor_diagonal_mm = FULL_FRAME_DIAGONAL_MM / crop_factor
    image_diagonal_px = math.hypot(image_width_px, image_height_px)
    sensor_width_mm = sensor_diagonal_mm * image_width_px / image_diagonal_px
    sensor_height_mm = sensor_diagonal_mm * image_height_px / image_diagonal_px
    return sensor_width_mm, sensor_height_mm, crop_factor


def resolve_camera_parameters(
    row: Any,
    target_image_type: str,
    actual_image_size_px: tuple[int, int] | None = None,
) -> dict[str, Any]:
    """Resolve footprint camera parameters for one metadata row.

    Footprint estimation prefers explicit FOV metadata. If FOV is unavailable,
    it uses focal length plus sensor dimensions only when both are available.
    Focal length alone is not enough. When visible sensor/FOV metadata is
    incomplete, this function does not apply a visible fallback because DJI
    Matrice 4T has multiple visible cameras.
    """
    profile = camera_profile_for_target(target_image_type)
    warnings: list[str] = []

    metadata_width = parse_float(first_existing_value(row, ["image_width", "image_width_px", "ImageWidth"]))
    metadata_height = parse_float(first_existing_value(row, ["image_height", "image_height_px", "ImageHeight"]))
    if actual_image_size_px is not None:
        image_width_px = int(actual_image_size_px[0])
        image_height_px = int(actual_image_size_px[1])
        image_dimension_source = "actual_image_file"
    else:
        image_width_px = int(metadata_width) if valid_positive(metadata_width) else None
        image_height_px = int(metadata_height) if valid_positive(metadata_height) else None
        image_dimension_source = "EXIF/XMP metadata"

    focal_metadata = parse_float(
        first_existing_value(row, ["focal_length", "focal_length_mm", "FocalLength"])
    )
    focal_35mm_metadata = parse_float(
        first_existing_value(
            row,
            [
                "focal_length_35mm",
                "focal_length_35mm_mm",
                "FocalLengthIn35mmFormat",
                "FocalLength35mm",
            ],
        )
    )
    sensor_width_metadata = parse_float(first_existing_value(row, SENSOR_WIDTH_CANDIDATES))
    sensor_height_metadata = parse_float(first_existing_value(row, SENSOR_HEIGHT_CANDIDATES))
    horizontal_fov_metadata = parse_float(
        first_existing_value(row, FOV_COLUMN_CANDIDATES["horizontal"])
    )
    vertical_fov_metadata = parse_float(
        first_existing_value(row, FOV_COLUMN_CANDIDATES["vertical"])
    )

    focal_length_mm: float | None = focal_metadata
    focal_length_source = "EXIF/XMP metadata" if valid_positive(focal_metadata) else ""
    sensor_width_mm: float | None = sensor_width_metadata
    sensor_height_mm: float | None = sensor_height_metadata
    sensor_source = (
        "EXIF/XMP metadata"
        if valid_positive(sensor_width_metadata) and valid_positive(sensor_height_metadata)
        else ""
    )
    crop_factor: float | None = None
    fallback_used = False
    footprint_approximate = True

    if valid_positive(horizontal_fov_metadata) and valid_positive(vertical_fov_metadata):
        horizontal_fov_deg = horizontal_fov_metadata
        vertical_fov_deg = vertical_fov_metadata
        fov_source = "EXIF/XMP metadata"
        parameter_source = "EXIF/XMP FOV metadata"
    elif (
        valid_positive(focal_metadata)
        and valid_positive(sensor_width_metadata)
        and valid_positive(sensor_height_metadata)
    ):
        horizontal_fov_deg, vertical_fov_deg = fov_from_focal_and_sensor(
            focal_metadata,
            sensor_width_metadata,
            sensor_height_metadata,
        )
        fov_source = "EXIF/XMP focal length + EXIF/XMP sensor size"
        parameter_source = fov_source
    elif (
        valid_positive(focal_metadata)
        and valid_positive(focal_35mm_metadata)
        and valid_positive(image_width_px)
        and valid_positive(image_height_px)
    ):
        sensor_width_mm, sensor_height_mm, crop_factor = sensor_size_from_35mm_equivalent(
            focal_metadata,
            focal_35mm_metadata,
            float(image_width_px),
            float(image_height_px),
        )
        horizontal_fov_deg, vertical_fov_deg = fov_from_focal_and_sensor(
            focal_metadata,
            sensor_width_mm,
            sensor_height_mm,
        )
        sensor_source = (
            "derived from EXIF/XMP focal_length_35mm and target image aspect"
        )
        fov_source = "computed from EXIF/XMP focal length + 35mm-equivalent-derived sensor size"
        parameter_source = (
            "EXIF/XMP focal length + focal_length_35mm-derived sensor size"
        )
    elif profile["target_image_type"] == "visible":
        fallback_used = False
        footprint_approximate = True
        horizontal_fov_deg = None
        vertical_fov_deg = None
        fov_source = "missing"
        parameter_source = "incomplete visible metadata; no fallback applied"
        warnings.append(
            "Visible metadata lacks enough FOV/sensor/35mm-equivalent information; no fallback profile was applied."
        )
    else:
        fallback_used = True
        footprint_approximate = True
        if not valid_positive(focal_length_mm):
            focal_length_mm = float(profile["fallback_focal_length_mm"])
            focal_length_source = "thermal_profile fallback"
        horizontal_fov_deg = float(profile["fallback_horizontal_fov_deg"])
        vertical_fov_deg = float(profile["fallback_vertical_fov_deg"])
        fov_source = "thermal_profile fallback FOV"
        parameter_source = "thermal_profile fallback assumptions"
        warnings.append(
            "Thermal metadata lacks explicit FOV/sensor size; using thermal_profile fallback FOV."
        )

    relative_altitude_m = parse_float(
        first_existing_value(row, ["relative_altitude", "relative_altitude_m", "RelativeAltitude"])
    )
    altitude_source = "EXIF/XMP RelativeAltitude" if relative_altitude_m is not None else ""
    center_lat = parse_float(first_existing_value(row, ["gps_latitude", "center_lat", "GPSLatitude"]))
    center_lon = parse_float(first_existing_value(row, ["gps_longitude", "center_lon", "GPSLongitude"]))
    gps_source = "EXIF/XMP GPS" if center_lat is not None and center_lon is not None else ""

    aperture = parse_float(first_existing_value(row, ["aperture", "Aperture"]))
    f_number = parse_float(first_existing_value(row, ["f_number", "FNumber"]))
    gimbal_yaw = parse_float(first_existing_value(row, ["gimbal_yaw_degree", "GimbalYawDegree"]))
    flight_yaw = parse_float(first_existing_value(row, ["flight_yaw_degree", "FlightYawDegree"]))
    yaw_source = ""
    if gimbal_yaw is not None:
        yaw_source = "EXIF/XMP gimbal_yaw_degree"
    elif flight_yaw is not None:
        yaw_source = "EXIF/XMP flight_yaw_degree"

    return {
        "target_image_type": profile["target_image_type"],
        "camera_profile_used": profile["name"],
        "profile_notes": profile["notes"],
        "image_width_px": image_width_px,
        "image_height_px": image_height_px,
        "metadata_image_width_px": metadata_width,
        "metadata_image_height_px": metadata_height,
        "image_dimension_source": image_dimension_source,
        "focal_length_mm": focal_length_mm,
        "focal_length_35mm": focal_35mm_metadata,
        "focal_length_source": focal_length_source or "not used",
        "sensor_width_mm": sensor_width_mm,
        "sensor_height_mm": sensor_height_mm,
        "crop_factor_from_35mm": crop_factor,
        "sensor_source": sensor_source or "not used",
        "horizontal_fov_deg": horizontal_fov_deg,
        "vertical_fov_deg": vertical_fov_deg,
        "fov_source": fov_source,
        "parameter_source": parameter_source,
        "fallback_used": fallback_used,
        "footprint_approximate": footprint_approximate,
        "relative_altitude_m": relative_altitude_m,
        "altitude_source": altitude_source or "missing",
        "center_lat": center_lat,
        "center_lon": center_lon,
        "gps_source": gps_source or "missing",
        "gimbal_yaw_degree": gimbal_yaw,
        "flight_yaw_degree": flight_yaw,
        "yaw_source": yaw_source or "missing",
        "yaw_used_for_footprint": False,
        "yaw_assumption": "not applied; approximate north-up rectangular footprint",
        "aperture_value": aperture,
        "f_number_value": f_number,
        "aperture_ignored": True,
        "matrice_4t_camera": classify_matrice_4t_camera(row),
        "warnings": warnings,
    }
