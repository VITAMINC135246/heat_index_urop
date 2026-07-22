"""Resolve capture time once and carry explicit provenance through the workflow."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import pandas as pd
from PIL import ExifTags, Image


DJI_NAME = re.compile(
    r"^DJI_(?P<timestamp>\d{14})_(?P<sample>\d+)_[VT]$",
    re.IGNORECASE,
)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DJI_METADATA_PATH = PROJECT_ROOT / "data" / "metadata" / "dji_image_metadata.xlsx"
CAPTURE_TIME_RESOLVER_VERSION = "capture-time-priority-bundle-v2"
INVALID_CAPTURE_TIME_SOURCES = {
    "",
    "invalid",
    "missing",
    "none",
    "not_available",
    "unknown",
    "unavailable",
}


@dataclass(frozen=True, slots=True)
class CaptureTimeResult:
    capture_datetime: str = ""
    capture_time_local: str = ""
    capture_time_utc: str = ""
    capture_timezone: str = ""
    capture_time_source: str = "missing"
    timezone_assumption: str = ""
    capture_time_valid: bool = False
    raw_capture_time: str = ""

    @property
    def capture_time(self) -> str:
        """Backward-compatible alias used by schema-0.2 manifests."""
        return self.capture_datetime

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "capture_time": self.capture_time}


def _bool_value(value: Any, *, default: bool) -> bool:
    if value is None or (isinstance(value, str) and not value.strip()):
        return default
    try:
        if bool(pd.isna(value)):
            return default
    except (TypeError, ValueError):
        pass
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes", "y"}
    return bool(value)


def capture_time_bundle(
    record: dict[str, Any] | None,
    *,
    source_override: str = "",
    default_timezone: str = "",
) -> dict[str, Any] | None:
    """Return one internally consistent, explicitly valid capture-time bundle."""
    payload = dict(record or {})
    capture_datetime = _text(payload, "capture_datetime", "capture_time", "capture_time_local")
    declared_source = _text(payload, "capture_time_source")
    # An explicit ``missing``/``unknown`` marker is evidence that the record is
    # unusable; a caller-provided fallback label must not turn it into a valid
    # timestamp.  A genuinely legacy record with no source field may, however,
    # receive an explicit source_override such as ``part_a_capture_time_fallback``.
    if declared_source and declared_source.casefold() in INVALID_CAPTURE_TIME_SOURCES:
        return None
    source = source_override or declared_source
    valid = _bool_value(payload.get("capture_time_valid"), default=bool(capture_datetime))
    if not capture_datetime or not valid or source.strip().casefold() in INVALID_CAPTURE_TIME_SOURCES:
        return None
    local_time = _text(payload, "capture_time_local") or capture_datetime
    timezone_hint = _text(payload, "capture_timezone", "timezone") or default_timezone
    normalized = _normalized_result(
        local_time,
        source=source,
        default_timezone=timezone_hint or "UTC",
        timezone_hint=timezone_hint,
    )
    if normalized is None:
        return None
    expected_utc = pd.Timestamp(normalized.capture_time_utc)
    for key, assume_utc in (
        ("capture_datetime", False),
        ("capture_time", False),
        ("capture_time_local", False),
        ("capture_time_utc", True),
    ):
        value = _text(payload, key)
        if not value:
            continue
        instant = _utc_instant(value, timezone_hint=timezone_hint, assume_utc=assume_utc)
        if instant is None or abs((instant - expected_utc).total_seconds()) > 1e-6:
            return None
    result = normalized.to_dict()
    result["capture_time_source"] = source
    result["timezone_assumption"] = _text(payload, "timezone_assumption") or normalized.timezone_assumption
    result["capture_time_valid"] = True
    return result


def select_capture_time_bundle(
    *candidates: tuple[dict[str, Any] | None, str],
    missing_timezone: str = "",
) -> dict[str, Any]:
    """Select the first valid bundle without mixing fields across sources."""
    for record, source_override in candidates:
        bundle = capture_time_bundle(
            record,
            source_override=source_override,
            default_timezone=missing_timezone,
        )
        if bundle is not None:
            return bundle
    return CaptureTimeResult(capture_timezone=missing_timezone).to_dict()


def _text(record: dict[str, Any] | None, *keys: str) -> str:
    normalized = {str(key).strip().casefold(): value for key, value in (record or {}).items()}
    for key in keys:
        value = normalized.get(key.casefold())
        if value is not None and str(value).strip() and str(value).strip().casefold() != "nan":
            return str(value).strip()
    return ""


def _parse_datetime(value: str) -> datetime | None:
    text = value.strip()
    if not text:
        return None
    # EXIF uses ``YYYY:MM:DD HH:MM:SS`` while metadata tables generally use ISO.
    exif_match = re.match(
        r"^(?P<date>\d{4}:\d{2}:\d{2})[ T](?P<time>\d{2}:\d{2}:\d{2})(?P<rest>.*)$",
        text,
    )
    if exif_match:
        text = exif_match.group("date").replace(":", "-", 2) + "T" + exif_match.group("time") + exif_match.group("rest")
    try:
        stamp = pd.Timestamp(text)
    except (TypeError, ValueError):
        return None
    if pd.isna(stamp):
        return None
    return stamp.to_pydatetime()


def _utc_instant(value: str, *, timezone_hint: str, assume_utc: bool) -> pd.Timestamp | None:
    parsed = _parse_datetime(value)
    if parsed is None:
        return None
    stamp = pd.Timestamp(parsed)
    if stamp.tzinfo is None:
        zone_name = "UTC" if assume_utc else timezone_hint
        if not zone_name:
            return None
        try:
            ZoneInfo(zone_name)
            stamp = stamp.tz_localize(zone_name, ambiguous="raise", nonexistent="raise")
        except (KeyError, TypeError, ValueError):
            return None
    try:
        return stamp.tz_convert("UTC")
    except (KeyError, TypeError, ValueError):
        return None


def _normalized_result(
    value: str,
    *,
    source: str,
    default_timezone: str,
    timezone_hint: str = "",
) -> CaptureTimeResult | None:
    parsed = _parse_datetime(value)
    if parsed is None:
        return None
    stamp = pd.Timestamp(parsed)
    if stamp.tzinfo is None:
        zone_name = timezone_hint or default_timezone
        try:
            ZoneInfo(zone_name)
            stamp = stamp.tz_localize(zone_name, ambiguous="raise", nonexistent="raise")
        except (KeyError, TypeError, ValueError):
            return None
        assumption = "metadata_timezone" if timezone_hint else "project_default_timezone"
        local = stamp
    else:
        zone_name = timezone_hint or str(stamp.tzinfo)
        if timezone_hint:
            try:
                ZoneInfo(timezone_hint)
                local = stamp.tz_convert(timezone_hint)
            except (KeyError, TypeError, ValueError):
                return None
        else:
            local = stamp
        assumption = "embedded_offset_or_timezone"
    try:
        utc = stamp.tz_convert("UTC")
    except (KeyError, TypeError, ValueError):
        return None
    return CaptureTimeResult(
        capture_datetime=local.isoformat(),
        capture_time_local=local.isoformat(),
        capture_time_utc=utc.isoformat(),
        capture_timezone=zone_name,
        capture_time_source=source,
        timezone_assumption=assumption,
        capture_time_valid=True,
        raw_capture_time=value,
    )


def _exif_values(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        with Image.open(path) as image:
            exif = image.getexif()
            values = {str(ExifTags.TAGS.get(key, key)): str(value) for key, value in exif.items()}
            try:
                exif_ifd = exif.get_ifd(ExifTags.IFD.Exif)
            except (AttributeError, KeyError, TypeError, ValueError):
                exif_ifd = {}
            values.update({str(ExifTags.TAGS.get(key, key)): str(value) for key, value in exif_ifd.items()})
            return values
    except (OSError, ValueError):
        return {}


def _exif_candidate(path: Path, default_timezone: str) -> CaptureTimeResult | None:
    values = _exif_values(path)
    original = values.get("DateTimeOriginal", "").strip()
    subsecond = (
        values.get("SubsecTimeOriginal", "").strip()
        or values.get("SubSecTimeOriginal", "").strip()
    )
    offset = values.get("OffsetTimeOriginal", "").strip()
    if original and subsecond:
        raw = f"{original}.{re.sub(r'[^0-9]', '', subsecond)}{offset}"
        result = _normalized_result(raw, source="exif_subsec_datetime_original", default_timezone=default_timezone)
        if result:
            return result
    if original:
        result = _normalized_result(
            original + offset,
            source="exif_datetime_original",
            default_timezone=default_timezone,
        )
        if result:
            return result
    return None


def _filename_candidate(path: Path, default_timezone: str) -> CaptureTimeResult | None:
    match = DJI_NAME.match(path.stem)
    if not match:
        return None
    try:
        stamp = datetime.strptime(match.group("timestamp"), "%Y%m%d%H%M%S")
    except ValueError:
        return None
    return _normalized_result(
        stamp.isoformat(),
        source="dji_filename_timestamp",
        default_timezone=default_timezone,
    )


def _normal_path(value: Any) -> str:
    return str(value or "").replace("\\", "/").strip().casefold()


@lru_cache(maxsize=2)
def _metadata_records(path_text: str) -> tuple[dict[str, Any], ...]:
    path = Path(path_text)
    if not path.is_file():
        return ()
    frame = pd.read_excel(path, keep_default_na=False)
    return tuple(frame.to_dict(orient="records"))


def dji_metadata_for_paths(
    paths: Iterable[Path],
    *,
    metadata_path: Path = DJI_METADATA_PATH,
) -> list[dict[str, Any]]:
    requested_paths = {_normal_path(path.resolve()) for path in paths if str(path)}
    requested_names = {path.name.casefold() for path in paths if str(path)}
    rows: list[dict[str, Any]] = []
    for record in _metadata_records(str(metadata_path.resolve())):
        record_path = _normal_path(record.get("image_path") or record.get("source_file"))
        resolved = _normal_path((PROJECT_ROOT / str(record.get("image_path", ""))).resolve()) if record_path else ""
        name = str(record.get("image_name", "")).casefold()
        if record_path in requested_paths or resolved in requested_paths or name in requested_names:
            rows.append(dict(record))
    return rows


def resolve_capture_time(
    *,
    thermal_path: Path,
    visible_path: Path | None = None,
    dji_metadata_records: Iterable[dict[str, Any]] = (),
    user_metadata: dict[str, Any] | None = None,
    default_timezone: str = "Asia/Hong_Kong",
) -> CaptureTimeResult:
    """Apply the documented capture-time priority without fabricating a value."""
    ZoneInfo(default_timezone)
    image_paths = [thermal_path, *([visible_path] if visible_path is not None else [])]
    # Both EXIF priorities precede all external metadata. Thermal is preferred
    # within a priority because it is the temperature capture being analysed.
    exif_payloads = [(path, _exif_values(path)) for path in image_paths if path is not None]
    for path, values in exif_payloads:
        original = values.get("DateTimeOriginal", "").strip()
        subsecond = values.get("SubsecTimeOriginal", "").strip() or values.get("SubSecTimeOriginal", "").strip()
        if original and subsecond:
            offset = values.get("OffsetTimeOriginal", "").strip()
            result = _normalized_result(
                f"{original}.{re.sub(r'[^0-9]', '', subsecond)}{offset}",
                source="exif_subsec_datetime_original",
                default_timezone=default_timezone,
            )
            if result:
                return result
    for path, values in exif_payloads:
        original = values.get("DateTimeOriginal", "").strip()
        if original:
            result = _normalized_result(
                original + values.get("OffsetTimeOriginal", "").strip(),
                source="exif_datetime_original",
                default_timezone=default_timezone,
            )
            if result:
                return result
    for record in dji_metadata_records:
        declared_source = _text(record, "capture_time_source")
        if declared_source and declared_source.casefold() in INVALID_CAPTURE_TIME_SOURCES:
            continue
        if not _bool_value(record.get("capture_time_valid"), default=True):
            continue
        value = _text(record, "capture_datetime", "capture_time", "datetime_original")
        if value:
            result = _normalized_result(
                value,
                source="dji_metadata_record",
                default_timezone=default_timezone,
                timezone_hint=_text(record, "capture_timezone", "timezone"),
            )
            if result:
                return result
    supplied = user_metadata or {}
    supplied_source = _text(supplied, "capture_time_source")
    supplied_valid = _bool_value(supplied.get("capture_time_valid"), default=True)
    value = _text(supplied, "capture_datetime", "capture_time", "datetime_original")
    if (
        value
        and supplied_valid
        and not (supplied_source and supplied_source.casefold() in INVALID_CAPTURE_TIME_SOURCES)
    ):
        result = _normalized_result(
            value,
            source="user_supplied_metadata",
            default_timezone=default_timezone,
            timezone_hint=_text(supplied, "capture_timezone", "timezone"),
        )
        if result:
            return result
    for path in image_paths:
        if path is not None:
            result = _filename_candidate(path, default_timezone)
            if result:
                return result
    return CaptureTimeResult(capture_timezone=default_timezone)
