"""Structured Part A discovery, metadata normalization, and V/T validation."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from PIL import ExifTags, Image, UnidentifiedImageError

from scripts.camera_profiles import resolve_camera_parameters

from .models import GroupInput, ProcessingStatus, ValidationRecord, ValidationStatus


SUPPORTED_IMAGE_TYPES = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
DJI_NAME = re.compile(
    r"^(?P<base>DJI_(?P<timestamp>\d{14})_(?P<sample>\d+))_(?P<role>[VT])$",
    re.IGNORECASE,
)


def image_role(path: Path) -> str | None:
    match = DJI_NAME.match(path.stem)
    return match.group("role").upper() if match else None


def image_identifier(path: Path) -> str:
    match = DJI_NAME.match(path.stem)
    if match:
        return match.group("base")
    return re.sub(r"_[VT]$", "", path.stem, flags=re.IGNORECASE)


def _capture_timestamp(path: Path) -> datetime | None:
    match = DJI_NAME.match(path.stem)
    if not match:
        return None
    try:
        return datetime.strptime(match.group("timestamp"), "%Y%m%d%H%M%S")
    except ValueError:
        return None


def _session(path: Path) -> str:
    for parent in [path.parent, *path.parents]:
        if parent.name.upper().startswith("DJI_"):
            return parent.name
    return path.parent.name


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _inspect_image(path: Path) -> tuple[bool, dict[str, Any], str]:
    if path.suffix.lower() not in SUPPORTED_IMAGE_TYPES:
        return False, {}, f"unsupported_file_type:{path.suffix.lower()}"
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            exif = {ExifTags.TAGS.get(key, str(key)): value for key, value in image.getexif().items()}
            metadata: dict[str, Any] = {
                "format": image.format or "",
                "width": int(image.width),
                "height": int(image.height),
                "mode": image.mode,
                "camera_model": str(exif.get("Model", "")),
                "make": str(exif.get("Make", "")),
                "focal_length": str(exif.get("FocalLength", "")),
                "capture_datetime": str(exif.get("DateTimeOriginal", exif.get("DateTime", ""))),
                "exif_tag_count": len(exif),
            }
        return True, metadata, ""
    except (OSError, ValueError, UnidentifiedImageError) as exc:
        return False, {}, f"unreadable_image:{type(exc).__name__}"


def _metadata_value(record: dict[str, Any], *names: str) -> Any:
    normalized = {str(key).strip().casefold(): value for key, value in record.items()}
    for name in names:
        value = normalized.get(name.casefold())
        if value not in (None, ""):
            return value
    return None


def validate_group(
    group: GroupInput,
    *,
    timestamp_warning_seconds: float = 5.0,
    temperature_shape: tuple[int, int] | None = None,
) -> ValidationRecord:
    """Validate Part A while separating fatal thermal and visible-only defects."""
    visible = Path(group.visible_path).expanduser().resolve()
    thermal = Path(group.thermal_path).expanduser().resolve()
    fatal: list[str] = []
    visible_errors: list[str] = []
    warnings: list[str] = []

    visible_valid, visible_meta, visible_reason = (False, {}, "missing")
    if visible.is_file():
        visible_valid, visible_meta, visible_reason = _inspect_image(visible)
        if not visible_valid:
            visible_errors.append(f"invalid_visible_image:{visible_reason}")
    else:
        visible_errors.append("missing_visible_image")

    thermal_valid, thermal_meta, thermal_reason = (False, {}, "missing")
    if thermal.is_file():
        thermal_valid, thermal_meta, thermal_reason = _inspect_image(thermal)
        if not thermal_valid:
            fatal.append(f"invalid_thermal_image:{thermal_reason}")
    else:
        fatal.append("missing_thermal_image")

    v_role = image_role(visible)
    t_role = image_role(thermal)
    if v_role != "V":
        visible_errors.append("visible_role_not_confirmed")
        visible_valid = False
    if t_role != "T":
        fatal.append("thermal_role_not_confirmed")
        thermal_valid = False

    v_id = image_identifier(visible)
    t_id = image_identifier(thermal)
    pairing_uncertain = False
    if v_id != t_id:
        warnings.append("filename_identifier_mismatch")
        pairing_uncertain = True

    v_time = _capture_timestamp(visible)
    t_time = _capture_timestamp(thermal)
    capture_time = (t_time or v_time).isoformat() if (t_time or v_time) else ""
    if v_time and t_time:
        difference = abs((v_time - t_time).total_seconds())
        if difference > timestamp_warning_seconds:
            warnings.append(f"timestamp_difference_seconds:{difference:g}")
            pairing_uncertain = True
    else:
        warnings.append("capture_timestamp_unavailable")

    v_session = _session(visible)
    t_session = _session(thermal)
    if v_session != t_session:
        warnings.append(f"session_mismatch:{v_session}:{t_session}")
        pairing_uncertain = True

    supplied = dict(group.metadata_record)
    metadata_source = str(_metadata_value(supplied, "metadata_source") or ("supplied_record" if supplied else "embedded_exif"))
    altitude = _number(_metadata_value(supplied, "relative_altitude", "absolute_altitude", "gps_altitude", "altitude_m"))
    latitude = _number(_metadata_value(supplied, "gps_latitude", "latitude"))
    longitude = _number(_metadata_value(supplied, "gps_longitude", "longitude"))
    camera_model = str(
        _metadata_value(supplied, "camera_model", "model")
        or visible_meta.get("camera_model")
        or thermal_meta.get("camera_model")
        or ""
    )
    focal = _number(_metadata_value(supplied, "focal_length", "focal_length_mm") or visible_meta.get("focal_length"))
    camera_row = {**visible_meta, **supplied, "camera_model": camera_model, "focal_length": focal}
    try:
        profile = resolve_camera_parameters(camera_row, target_image_type="visible") if visible_valid else {}
    except (KeyError, TypeError, ValueError):
        profile = {}
        warnings.append("camera_profile_unresolved")
    if altitude is None:
        warnings.append("altitude_unavailable")
    if latitude is None or longitude is None:
        warnings.append("gps_unavailable")
    if not camera_model:
        warnings.append("camera_model_unavailable")
    if focal is None and not profile:
        warnings.append("focal_length_or_camera_profile_unavailable")

    grid_compatible: bool | None = None
    if temperature_shape is not None and thermal_valid:
        native_shape = (int(thermal_meta["height"]), int(thermal_meta["width"]))
        grid_compatible = tuple(map(int, temperature_shape)) == native_shape
        if not grid_compatible:
            fatal.append(f"temperature_native_dimension_mismatch:{temperature_shape}:{native_shape}")
            thermal_valid = False

    errors = [*fatal, *visible_errors]
    if fatal:
        status = ValidationStatus.FAIL
        processing = ProcessingStatus.FAILED
    elif visible_errors or warnings:
        status = ValidationStatus.WARN
        processing = ProcessingStatus.READY
    else:
        status = ValidationStatus.PASS
        processing = ProcessingStatus.READY
    image_id = t_id or v_id
    pair_id = f"{group.dataset_id or 'selected'}::{image_id}"
    thermal_meta["usable_dji_thermal_assessment"] = (
        "readable_thermal_role_jpeg_sdk_validation_deferred" if thermal_valid and thermal.suffix.lower() in {".jpg", ".jpeg"}
        else "not_established"
    )
    return ValidationRecord(
        group_id=group.group_id,
        pair_id=pair_id,
        image_id=image_id,
        dataset_id=group.dataset_id,
        visible_path=visible.as_posix(),
        thermal_path=thermal.as_posix(),
        capture_time=capture_time,
        session=t_session or v_session,
        altitude_m=altitude,
        gps_latitude=latitude,
        gps_longitude=longitude,
        camera_model=camera_model,
        focal_length_mm=focal,
        camera_profile=profile,
        metadata_source=metadata_source,
        visible_camera_metadata=visible_meta,
        thermal_camera_metadata=thermal_meta,
        validation_status=status,
        warnings=warnings,
        errors=errors,
        fatal_errors=fatal,
        visible_errors=visible_errors,
        pairing_uncertain=pairing_uncertain,
        visible_valid=visible_valid,
        thermal_valid=thermal_valid,
        temperature_grid_compatible=grid_compatible,
        processing_status=processing,
    )


def write_validation_record(record: ValidationRecord, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(record.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)
    return path


def discover_dataset_groups(dataset_root: Path, dataset_id: str | None = None) -> list[GroupInput]:
    root = dataset_root.expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Dataset directory does not exist: {root}")
    by_key: dict[tuple[Path, str], dict[str, Path]] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_IMAGE_TYPES:
            continue
        match = DJI_NAME.match(path.stem)
        if not match:
            continue
        key = (path.parent, match.group("base"))
        by_key.setdefault(key, {})[match.group("role").upper()] = path
    groups: list[GroupInput] = []
    resolved_dataset_id = dataset_id or root.name
    for (_, base), roles in sorted(by_key.items(), key=lambda item: str(item[0])):
        if "T" not in roles:
            continue
        groups.append(
            GroupInput(
                group_id=f"{resolved_dataset_id}::{base}",
                visible_path=str(roles.get("V", "")),
                thermal_path=str(roles["T"]),
                dataset_id=resolved_dataset_id,
            )
        )
    return groups


def validate_groups(groups: Iterable[GroupInput]) -> list[ValidationRecord]:
    return [validate_group(group) for group in groups]
