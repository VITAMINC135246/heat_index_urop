"""Revised Part A input discovery and structured V/T validation."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Iterable

from PIL import Image, UnidentifiedImageError

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
    stem = re.sub(r"_[VT]$", "", path.stem, flags=re.IGNORECASE)
    return stem


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


def _inspect_image(path: Path) -> tuple[bool, dict[str, object], str]:
    if path.suffix.lower() not in SUPPORTED_IMAGE_TYPES:
        return False, {}, f"unsupported_file_type:{path.suffix.lower()}"
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            metadata: dict[str, object] = {
                "format": image.format or "",
                "width": int(image.width),
                "height": int(image.height),
                "mode": image.mode,
            }
            exif = image.getexif()
            if exif:
                metadata["exif_tag_count"] = len(exif)
        return True, metadata, ""
    except (OSError, ValueError, UnidentifiedImageError) as exc:
        return False, {}, f"unreadable_image:{type(exc).__name__}"


def validate_group(group: GroupInput, *, timestamp_warning_seconds: float = 5.0) -> ValidationRecord:
    visible = Path(group.visible_path).expanduser().resolve()
    thermal = Path(group.thermal_path).expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    visible_meta: dict[str, object] = {}
    thermal_meta: dict[str, object] = {}

    for role, path in (("visible", visible), ("thermal", thermal)):
        if not path.is_file():
            errors.append(f"missing_{role}_image")
            continue
        valid, metadata, reason = _inspect_image(path)
        if role == "visible":
            visible_meta = metadata
        else:
            thermal_meta = metadata
        if not valid:
            errors.append(f"invalid_{role}_image:{reason}")

    v_role = image_role(visible)
    t_role = image_role(thermal)
    if v_role != "V":
        errors.append("visible_role_not_confirmed")
    if t_role != "T":
        errors.append("thermal_role_not_confirmed")

    v_id = image_identifier(visible)
    t_id = image_identifier(thermal)
    if v_id != t_id:
        errors.append("filename_identifier_mismatch")

    v_time = _capture_timestamp(visible)
    t_time = _capture_timestamp(thermal)
    capture_time = (t_time or v_time).isoformat() if (t_time or v_time) else ""
    if v_time and t_time:
        difference = abs((v_time - t_time).total_seconds())
        if difference > timestamp_warning_seconds:
            warnings.append(f"timestamp_difference_seconds:{difference:g}")
    else:
        warnings.append("capture_timestamp_unavailable")

    v_session = _session(visible)
    t_session = _session(thermal)
    if v_session != t_session:
        warnings.append(f"session_mismatch:{v_session}:{t_session}")

    thermal_valid = thermal.is_file() and bool(thermal_meta) and t_role == "T"
    status = ValidationStatus.FAIL if errors else (ValidationStatus.WARN if warnings else ValidationStatus.PASS)
    processing = ProcessingStatus.FAILED if errors else ProcessingStatus.READY
    image_id = t_id or v_id
    pair_id = f"{group.dataset_id or 'selected'}::{image_id}"
    return ValidationRecord(
        group_id=group.group_id,
        pair_id=pair_id,
        image_id=image_id,
        dataset_id=group.dataset_id,
        visible_path=visible.as_posix(),
        thermal_path=thermal.as_posix(),
        capture_time=capture_time,
        session=t_session or v_session,
        visible_camera_metadata=visible_meta,
        thermal_camera_metadata=thermal_meta,
        validation_status=status,
        warnings=warnings,
        errors=errors,
        processing_status=processing,
        thermal_valid=thermal_valid,
    )


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
        if "V" not in roles or "T" not in roles:
            continue
        groups.append(
            GroupInput(
                group_id=f"{resolved_dataset_id}::{base}",
                visible_path=str(roles["V"]),
                thermal_path=str(roles["T"]),
                dataset_id=resolved_dataset_id,
            )
        )
    return groups


def validate_groups(groups: Iterable[GroupInput]) -> list[ValidationRecord]:
    return [validate_group(group) for group in groups]
