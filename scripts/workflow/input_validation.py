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

from .capture_time import dji_metadata_for_paths, resolve_capture_time
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
    default_timezone: str = "Asia/Hong_Kong",
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
    discovery_warning = str(group.metadata_record.get("discovery_pairing_warning", "")).strip()
    if bool(group.metadata_record.get("discovery_pairing_uncertain")):
        pairing_uncertain = True
    if discovery_warning:
        warnings.append(f"dataset_pairing:{discovery_warning}")
    if v_id != t_id:
        warnings.append("filename_identifier_mismatch")
        pairing_uncertain = True

    dji_records = dji_metadata_for_paths([thermal, visible])
    capture = resolve_capture_time(
        thermal_path=thermal,
        visible_path=visible,
        dji_metadata_records=dji_records,
        user_metadata=group.metadata_record,
        default_timezone=default_timezone,
    )
    capture_time = capture.capture_datetime
    thermal_records = [row for row in dji_records if str(row.get("image_type", "")).casefold() == "thermal"]
    visible_records = [row for row in dji_records if str(row.get("image_type", "")).casefold() == "visible"]
    thermal_capture = resolve_capture_time(
        thermal_path=thermal,
        dji_metadata_records=thermal_records,
        user_metadata=group.metadata_record,
        default_timezone=default_timezone,
    )
    visible_capture = resolve_capture_time(
        thermal_path=visible,
        dji_metadata_records=visible_records,
        user_metadata=group.metadata_record,
        default_timezone=default_timezone,
    )
    if thermal_capture.capture_time_valid and visible_capture.capture_time_valid:
        difference = abs(
            (
                datetime.fromisoformat(thermal_capture.capture_time_utc)
                - datetime.fromisoformat(visible_capture.capture_time_utc)
            ).total_seconds()
        )
        if difference > timestamp_warning_seconds:
            warnings.append(f"timestamp_difference_seconds:{difference:g}")
            pairing_uncertain = True
    if not capture.capture_time_valid:
        warnings.append("capture_timestamp_unavailable")

    v_session = _session(visible)
    t_session = _session(thermal)
    if v_session != t_session:
        warnings.append(f"session_mismatch:{v_session}:{t_session}")
        pairing_uncertain = True

    supplied = dict(group.metadata_record)
    thermal_dji = next(
        (record for record in dji_records if str(record.get("image_type", "")).casefold() == "thermal"),
        dji_records[0] if dji_records else {},
    )
    visible_dji = next(
        (record for record in dji_records if str(record.get("image_type", "")).casefold() == "visible"),
        thermal_dji,
    )
    spatial_metadata = {**thermal_dji, **supplied}
    camera_metadata = {**visible_dji, **supplied}
    if supplied and thermal_dji:
        metadata_source = "dji_metadata_table+user_supplied_record"
    elif supplied:
        metadata_source = str(_metadata_value(supplied, "metadata_source") or "supplied_record")
    elif thermal_dji:
        metadata_source = "data/metadata/dji_image_metadata.xlsx"
    else:
        metadata_source = "embedded_exif"
    altitude = _number(_metadata_value(spatial_metadata, "relative_altitude", "absolute_altitude", "gps_altitude", "altitude_m"))
    latitude = _number(_metadata_value(spatial_metadata, "gps_latitude", "latitude"))
    longitude = _number(_metadata_value(spatial_metadata, "gps_longitude", "longitude"))
    camera_model = str(
        _metadata_value(camera_metadata, "camera_model", "model")
        or visible_meta.get("camera_model")
        or thermal_meta.get("camera_model")
        or ""
    )
    focal = _number(_metadata_value(camera_metadata, "focal_length", "focal_length_mm") or visible_meta.get("focal_length"))
    camera_row = {**visible_meta, **camera_metadata, "camera_model": camera_model, "focal_length": focal}
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
        capture_datetime=capture.capture_datetime,
        capture_time_local=capture.capture_time_local,
        capture_time_utc=capture.capture_time_utc,
        capture_timezone=capture.capture_timezone,
        capture_time_source=capture.capture_time_source,
        timezone_assumption=capture.timezone_assumption,
        capture_time_valid=capture.capture_time_valid,
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
    # DJI visible/thermal frames often have adjacent timestamps (typically one
    # second apart) while retaining the same sample counter.  Discover by
    # session directory + sample counter, then pair only when the candidate is
    # unique and temporally close.  Ambiguous inputs remain thermal-only rather
    # than being silently attached to the wrong visible frame.
    by_sample: dict[tuple[Path, str], dict[str, list[tuple[Path, str, str]]]] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_IMAGE_TYPES:
            continue
        match = DJI_NAME.match(path.stem)
        if not match:
            continue
        key = (path.parent, match.group("sample"))
        by_sample.setdefault(key, {}).setdefault(match.group("role").upper(), []).append(
            (path, match.group("timestamp"), match.group("base"))
        )
    groups: list[GroupInput] = []
    resolved_dataset_id = dataset_id or root.name
    for (_, _sample), roles in sorted(by_sample.items(), key=lambda item: str(item[0])):
        visibles = roles.get("V", [])
        for thermal, thermal_stamp, thermal_base in roles.get("T", []):
            exact = [item for item in visibles if item[2].casefold() == thermal_base.casefold()]
            close: list[tuple[Path, str, str, float]] = []
            thermal_time = datetime.strptime(thermal_stamp, "%Y%m%d%H%M%S")
            for visible, visible_stamp, visible_base in visibles:
                visible_time = datetime.strptime(visible_stamp, "%Y%m%d%H%M%S")
                difference = abs((thermal_time - visible_time).total_seconds())
                if difference <= 10.0:
                    close.append((visible, visible_stamp, visible_base, difference))
            metadata: dict[str, Any] = {}
            selected_visible: Path | None = None
            if len(exact) == 1:
                selected_visible = exact[0][0]
                metadata["discovery_pairing_method"] = "exact_dji_base"
            elif len(close) == 1:
                selected_visible = close[0][0]
                metadata.update({
                    "discovery_pairing_method": "session_sample_unique_timestamp_tolerance",
                    "discovery_timestamp_difference_seconds": close[0][3],
                    "discovery_pairing_uncertain": True,
                })
            elif len(close) > 1:
                metadata.update({
                    "discovery_pairing_method": "ambiguous_unpaired",
                    "discovery_pairing_warning": "multiple_visible_candidates_within_10_seconds",
                    "discovery_visible_candidate_count": len(close),
                    "discovery_pairing_uncertain": True,
                })
            else:
                metadata.update({
                    "discovery_pairing_method": "thermal_only_no_close_visible_candidate",
                    "discovery_pairing_warning": "no_unique_visible_candidate_within_10_seconds",
                    "discovery_pairing_uncertain": True,
                })
            groups.append(
                GroupInput(
                    group_id=f"{resolved_dataset_id}::{thermal_base}",
                    visible_path=str(selected_visible or ""),
                    thermal_path=str(thermal),
                    dataset_id=resolved_dataset_id,
                    metadata_record=metadata,
                )
            )
    return groups


def validate_groups(groups: Iterable[GroupInput]) -> list[ValidationRecord]:
    return [validate_group(group) for group in groups]
