"""Explicit, same-location temporal analysis for canonical measurements.

Temporal analysis is opt-in.  A timestamp, dataset, filename, target label, or
workflow run never establishes spatial identity on its own.  Every temporal
series therefore comes from a :class:`TemporalGroupDefinition` that records an
explicit same-location confirmation and a separately confirmed comparable ROI.

Pixels remain within-capture observations.  They are reduced to one row per
capture and compatibility stratum before any cross-time range is calculated.
Pixelwise temporal maps are a separate, stricter path and require an explicit
registration confirmation, method, and stable registration identifier.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

import matplotlib
import numpy as np
import pandas as pd

from .result_index import sha256_file


PROJECT_ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("MPLCONFIGDIR", str(PROJECT_ROOT / ".matplotlib-cache"))
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


STAT_NAMES = ("min", "max", "mean", "median", "q01", "q05", "q95", "q99")
TEMPERATURE_COMPATIBILITY_COLUMNS = [
    "measurement_type",
    "temperature_source",
    "temperature_definition",
    "temperature_unit",
    "source_method",
    "selection_scope",
    "roi_definition",
    "roi_method",
    "spatial_processing_method",
]
DELTA_T_COMPATIBILITY_COLUMNS = [
    *TEMPERATURE_COMPATIBILITY_COLUMNS,
    "ambient_source",
    "ambient_definition",
    "ambient_unit",
]
GROUP_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
DEFAULT_GPS_CONFLICT_THRESHOLD_M = 100.0
INVALID_CAPTURE_TIME_SOURCES = {"", "missing", "unknown", "unavailable", "invalid", "none", "null"}

REASON_MESSAGES = {
    "capture_time_marked_invalid": "The canonical record explicitly marks the capture time as invalid.",
    "capture_time_source_missing": "The capture-time source is missing or explicitly marked unavailable.",
    "ambiguous_capture_time_sources": "More than one capture-time source is recorded for this capture.",
    "capture_timestamp_missing": "The capture timestamp is missing.",
    "ambiguous_capture_timestamps": "More than one capture timestamp is recorded for this capture.",
    "invalid_capture_timestamp": "The capture timestamp cannot be parsed.",
    "ambiguous_capture_timezones": "More than one capture timezone is recorded for this capture.",
    "invalid_or_ambiguous_timezone": "The capture timezone is invalid or ambiguous.",
    "temperature_source_missing": "The temperature source is missing.",
    "temperature_definition_missing": "The temperature definition is missing.",
    "temperature_unit_missing": "The temperature unit is missing.",
    "ambient_source_missing": "The ambient-temperature source is missing, so ΔT is unavailable.",
    "ambient_definition_missing": "The ambient-temperature definition is missing, so ΔT is unavailable.",
    "ambient_unit_missing": "The ambient-temperature unit is missing, so ΔT is unavailable.",
    "ambient_temperature_or_delta_t_missing": "No finite ambient temperature or ΔT measurement is available.",
    "ambiguous_ambient_values_within_capture": "More than one ambient-temperature value is recorded within this capture.",
    "no_analysis_eligible_target_measurements": "No finite, accepted target measurement is eligible for analysis.",
    "duplicate_image_pixel_identifiers": "Duplicate pixel identifiers make the capture summary ambiguous.",
    "same_physical_location_not_confirmed": "The captures were not confirmed as the same physical location.",
    "comparable_target_roi_not_confirmed": "Comparable target ROIs were not confirmed across captures.",
    "qa_status_not_accepted": "The capture QA status is not allowed by this temporal plan.",
    "duplicate_capture_timestamp_within_compatibility_stratum": (
        "Two captures have the same timestamp in one compatibility stratum, so neither is ordered as a temporal observation."
    ),
    "outside_user_defined_observation_windows": "The capture is outside every user-defined observation window.",
    "image_id_not_found_in_canonical_input": "The submitted image ID is not present in the canonical input.",
    "incompatible_ambient_source_across_captures": (
        "Ambient-temperature sources differ across captures, so their ΔT values are not pooled."
    ),
    "incompatible_ambient_definition_across_captures": (
        "Ambient-temperature definitions differ across captures, so their ΔT values are not pooled."
    ),
    "incompatible_ambient_unit_across_captures": (
        "Ambient-temperature units differ across captures, so their ΔT values are not pooled."
    ),
}


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().casefold() in {"1", "true", "yes", "y", "confirmed", "accepted"}


def _reason_message(reason: str) -> str:
    """Translate an exact machine-readable exclusion code into ordinary language."""

    code = str(reason).strip()
    if not code:
        return ""
    if code in REASON_MESSAGES:
        return REASON_MESSAGES[code]
    if code.startswith("gps_distance_conflict:"):
        return f"Recorded GPS positions exceed the plan's distance threshold ({code})."
    if code.startswith("conflicting_") or "_mismatch:" in code:
        return f"Recorded spatial identity conflicts with the confirmed target ({code})."
    if code.startswith("invalid_gps_coordinates:"):
        return f"The capture has invalid GPS coordinates ({code})."
    if code.startswith("ambiguous_gps_coordinates_within_capture:"):
        return f"The capture has more than one GPS position ({code})."
    return code.replace("_", " ").rstrip(".").capitalize() + "."


def _ordinary_reasons(reasons: Iterable[str]) -> str:
    return " ".join(_reason_message(value) for value in dict.fromkeys(reasons) if str(value).strip())


def _metadata_missing(value: Any) -> bool:
    return str(value).strip().casefold() in INVALID_CAPTURE_TIME_SOURCES


@dataclass(slots=True)
class TemporalGroupDefinition:
    """User-confirmed definition of one physical location/target over time."""

    temporal_group_id: str
    image_ids: list[str]
    location_id: str
    target_id: str
    location_name: str = ""
    target_name: str = ""
    same_location_confirmed: bool = False
    confirmation_provenance: str = ""
    roi_comparable_confirmed: bool = False
    spatial_override_confirmed: bool = False
    spatial_override_reason: str = ""
    registration_confirmed: bool = False
    registration_method: str = ""
    registration_id: str = ""
    observation_windows: list[dict[str, str]] = field(default_factory=list)
    allowed_qa_statuses: list[str] = field(default_factory=lambda: ["pass", "warn"])
    full_day_sampling_confirmed: bool = False
    gps_conflict_threshold_m: float = DEFAULT_GPS_CONFLICT_THRESHOLD_M

    def __post_init__(self) -> None:
        self.temporal_group_id = str(self.temporal_group_id).strip()
        self.image_ids = list(dict.fromkeys(str(value).strip() for value in self.image_ids if str(value).strip()))
        self.location_id = str(self.location_id).strip()
        self.target_id = str(self.target_id).strip()
        self.location_name = str(self.location_name).strip()
        self.target_name = str(self.target_name).strip()
        self.confirmation_provenance = str(self.confirmation_provenance).strip()
        self.spatial_override_reason = str(self.spatial_override_reason).strip()
        self.registration_method = str(self.registration_method).strip()
        self.registration_id = str(self.registration_id).strip()
        self.allowed_qa_statuses = sorted(
            {str(value).strip().casefold() for value in self.allowed_qa_statuses if str(value).strip()}
        )
        self.gps_conflict_threshold_m = float(self.gps_conflict_threshold_m)
        if not self.temporal_group_id or not GROUP_ID_PATTERN.fullmatch(self.temporal_group_id):
            raise ValueError(
                "temporal_group_id must start with a letter or number and contain only letters, numbers, '.', '_' or '-'."
            )
        if not self.image_ids:
            raise ValueError(f"Temporal group {self.temporal_group_id!r} has no submitted captures.")
        if not self.location_id:
            raise ValueError(f"Temporal group {self.temporal_group_id!r} requires a stable location_id.")
        if not self.target_id:
            raise ValueError(f"Temporal group {self.temporal_group_id!r} requires a stable target_id.")
        if self.same_location_confirmed and not self.confirmation_provenance:
            raise ValueError("Same-location confirmation requires non-empty confirmation_provenance.")
        if self.spatial_override_confirmed and not self.spatial_override_reason:
            raise ValueError("A spatial conflict override requires a non-empty reason.")
        if self.registration_confirmed and (not self.registration_method or not self.registration_id):
            raise ValueError("Pixel registration confirmation requires registration_method and registration_id.")
        if not self.allowed_qa_statuses:
            raise ValueError("allowed_qa_statuses cannot be empty.")
        if not np.isfinite(self.gps_conflict_threshold_m) or self.gps_conflict_threshold_m <= 0:
            raise ValueError("gps_conflict_threshold_m must be a positive finite distance.")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TemporalGroupDefinition":
        data = dict(payload)
        image_ids = data.get(
            "image_ids",
            data.get("submitted_image_ids", data.get("submitted_capture_ids", data.get("selected_image_ids", []))),
        )
        if isinstance(image_ids, str):
            image_ids = [value.strip() for value in image_ids.split(",") if value.strip()]
        return cls(
            temporal_group_id=str(data.get("temporal_group_id", "")),
            image_ids=list(image_ids or []),
            location_id=str(data.get("location_id", "")),
            target_id=str(data.get("target_id", "")),
            location_name=str(data.get("location_name", data.get("name", ""))),
            target_name=str(data.get("target_name", "")),
            same_location_confirmed=_as_bool(data.get("same_location_confirmed", False)),
            confirmation_provenance=str(data.get("confirmation_provenance", data.get("confirmed_by", ""))),
            roi_comparable_confirmed=_as_bool(
                data.get("roi_comparable_confirmed", data.get("roi_compatible_confirmed", False))
            ),
            spatial_override_confirmed=_as_bool(
                data.get("spatial_override_confirmed", data.get("manual_override_confirmed", False))
            ),
            spatial_override_reason=str(
                data.get("spatial_override_reason", data.get("manual_override_reason", ""))
            ),
            registration_confirmed=_as_bool(data.get("registration_confirmed", False)),
            registration_method=str(data.get("registration_method", "")),
            registration_id=str(data.get("registration_id", "")),
            observation_windows=[dict(value) for value in data.get("observation_windows", [])],
            allowed_qa_statuses=list(data.get("allowed_qa_statuses", ["pass", "warn"])),
            full_day_sampling_confirmed=_as_bool(data.get("full_day_sampling_confirmed", False)),
            gps_conflict_threshold_m=float(
                data.get("gps_conflict_threshold_m", DEFAULT_GPS_CONFLICT_THRESHOLD_M)
            ),
        )


@dataclass(slots=True)
class TemporalAnalysisPlan:
    """Serializable run-level opt-in and its independently confirmed groups."""

    temporal_requested: bool = False
    groups: list[TemporalGroupDefinition] = field(default_factory=list)

    def __post_init__(self) -> None:
        seen_groups: set[str] = set()
        seen_images: set[str] = set()
        for group in self.groups:
            if group.temporal_group_id in seen_groups:
                raise ValueError(f"Duplicate temporal_group_id: {group.temporal_group_id}")
            seen_groups.add(group.temporal_group_id)
            overlap = seen_images.intersection(group.image_ids)
            if overlap:
                raise ValueError(f"A capture may belong to only one temporal group: {sorted(overlap)}")
            seen_images.update(group.image_ids)
        if not self.temporal_requested and self.groups:
            raise ValueError("Temporal groups cannot be supplied when temporal_requested is false.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "temporal_requested": self.temporal_requested,
            "groups": [group.to_dict() for group in self.groups],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TemporalAnalysisPlan":
        groups = [
            value if isinstance(value, TemporalGroupDefinition) else TemporalGroupDefinition.from_dict(value)
            for value in payload.get("groups", payload.get("temporal_groups", []))
        ]
        requested = _as_bool(payload.get("temporal_requested", bool(groups)))
        return cls(temporal_requested=requested, groups=groups)


def parse_temporal_plan(
    plan: TemporalAnalysisPlan | Mapping[str, Any] | Path | str | None = None,
    *,
    temporal_requested: bool | None = None,
    temporal_groups: Iterable[TemporalGroupDefinition | Mapping[str, Any]] | None = None,
) -> TemporalAnalysisPlan:
    """Parse a program-created plan; this function never infers groups from data."""

    if isinstance(plan, TemporalAnalysisPlan):
        parsed = plan
    elif isinstance(plan, Mapping):
        parsed = TemporalAnalysisPlan.from_dict(plan)
    elif isinstance(plan, (str, Path)):
        path = Path(plan)
        parsed = TemporalAnalysisPlan.from_dict(json.loads(path.read_text(encoding="utf-8")))
    elif plan is None:
        groups = [
            value if isinstance(value, TemporalGroupDefinition) else TemporalGroupDefinition.from_dict(value)
            for value in (temporal_groups or [])
        ]
        parsed = TemporalAnalysisPlan(
            temporal_requested=bool(groups) if temporal_requested is None else bool(temporal_requested),
            groups=groups,
        )
    else:
        raise TypeError(f"Unsupported temporal plan type: {type(plan).__name__}")
    if temporal_requested is not None and bool(temporal_requested) != parsed.temporal_requested:
        raise ValueError("temporal_requested conflicts with the supplied temporal plan.")
    if temporal_groups is not None and plan is not None:
        raise ValueError("Supply temporal groups inside the plan or through temporal_groups, not both.")
    return parsed


@dataclass(slots=True)
class TemporalRunResult:
    status: str
    output_root: Path
    run_manifest: Path
    run_summary: Path
    validation: Path
    temporal_requested: bool
    temporal_series_available: bool
    group_manifests: list[Path] = field(default_factory=list)
    capture_summary: Path | None = None
    stratum_summary: Path | None = None
    inclusion_exclusion: Path | None = None
    diagnostics: Path | None = None
    qa_report: Path | None = None
    report: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status,
            "output_root": self.output_root.resolve().as_posix(),
            "run_manifest": self.run_manifest.resolve().as_posix(),
            "run_summary": self.run_summary.resolve().as_posix(),
            "validation": self.validation.resolve().as_posix(),
            "temporal_requested": self.temporal_requested,
            "temporal_series_available": self.temporal_series_available,
            "group_manifests": [path.resolve().as_posix() for path in self.group_manifests],
        }
        for name in (
            "capture_summary",
            "stratum_summary",
            "inclusion_exclusion",
            "diagnostics",
            "qa_report",
            "report",
        ):
            value = getattr(self, name)
            payload[name] = value.resolve().as_posix() if value is not None else ""
        return payload


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _write_csv(frame: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8-sig", float_format="%.8g")
    return path


def _json_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Return strict-JSON-compatible records (no NaN/NaT tokens)."""

    if frame.empty:
        return []
    clean = frame.astype(object).where(pd.notna(frame), None)
    return clean.to_dict(orient="records")


def _config_hash(default_timezone: str, plan: TemporalAnalysisPlan) -> str:
    payload = {
        "processing_version": "heat-index-urop-0.3.2",
        "method_sha256": sha256_file(Path(__file__).resolve()),
        "default_timezone": default_timezone,
        "interpolation": "disabled",
        "temporal_unit": "one confirmed capture of one physical target",
        "statistics": list(STAT_NAMES),
        "plan": plan.to_dict(),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _ensure_columns(frame: pd.DataFrame) -> pd.DataFrame:
    work = frame.copy()
    legacy_ambient_fields = {
        column: column not in work.columns
        for column in ("ambient_data_qa_status", "ambient_provenance", "ambient_source_record")
    }
    aliases = {
        "capture_datetime": ("capture_datetime", "capture_time", "capture_time_local", "capture_time_utc"),
        "thermal_row": ("thermal_row", "pixel_y"),
        "thermal_col": ("thermal_col", "pixel_x"),
    }
    for target, candidates in aliases.items():
        if target in work:
            continue
        for candidate in candidates:
            if candidate in work:
                work[target] = work[candidate]
                break
    required = {"image_id", "temperature_c", "measurement_type"}
    missing = sorted(required.difference(work.columns))
    if missing:
        raise ValueError(f"Temporal input is missing required fields: {missing}")
    # Old canonical files predate the explicit validity flag.  For those files
    # only, a non-empty timestamp is the legacy validity signal.  Once the flag
    # exists, an explicit false must survive normalization and remain a hard
    # exclusion even when the timestamp text happens to parse.
    if "capture_time_valid" not in work:
        raw_capture_time = (
            work["capture_datetime"]
            if "capture_datetime" in work
            else pd.Series("", index=work.index, dtype=str)
        )
        work["capture_time_valid"] = raw_capture_time.fillna("").astype(str).str.strip().ne("")
    else:
        work["capture_time_valid"] = work["capture_time_valid"].map(_as_bool)
    defaults: dict[str, Any] = {
        "capture_datetime": "",
        "capture_timezone": "",
        "capture_time_source": "",
        "temperature_source": "",
        "temperature_definition": "",
        # temperature_c is itself an explicit Celsius contract for old canonical files.
        "temperature_unit": "degC",
        "source_method": "unknown",
        "selection_scope": "",
        "surface_cover_provenance": "unknown",
        "luhk_provenance": "unknown",
        "target_id": "",
        "target_name": "",
        "location_id": "",
        "location_name": "",
        "roi_id": "",
        "roi_definition": "",
        "roi_method": "",
        "roi_mask_sha256": "",
        "roi_polygon_area_px2": np.nan,
        "roi_target_pixel_count": np.nan,
        "roi_target_coverage_fraction": np.nan,
        "roi_boundary_overlap_fraction": np.nan,
        "roi_comparability_evidence": "",
        "spatial_processing_method": "",
        "spatial_registration_id": "",
        "qa_status": "unknown",
        "ambient_source": "",
        "ambient_definition": "",
        # Unlike temperature_c, delta_t_c does not prove the provenance or
        # declared unit of the ambient reference.  Missing ambient metadata is
        # therefore explicit rather than silently defaulted.
        "ambient_unit": "",
        "ambient_data_qa_status": "",
        "ambient_provenance": "",
        "ambient_source_record": "",
        "ambient_metadata_legacy_fallback": False,
        "ambient_temperature_c": np.nan,
        "delta_t_c": np.nan,
        "analysis_eligible": True,
        "temperature_is_finite": True,
        "label_known": True,
        "target_mask": True,
        "exclusion_reason": "",
        "dataset_id": "",
        "group_id": "",
        "visible_path": "",
        "thermal_path": "",
        "pixel_uid": "",
        "thermal_row": np.nan,
        "thermal_col": np.nan,
        "image_height": np.nan,
        "image_width": np.nan,
        "gps_latitude": np.nan,
        "gps_longitude": np.nan,
    }
    for column, value in defaults.items():
        if column not in work:
            work[column] = value
    if legacy_ambient_fields["ambient_data_qa_status"]:
        work["ambient_data_qa_status"] = work["qa_status"]
    if legacy_ambient_fields["ambient_provenance"]:
        has_ambient = work["ambient_source"].fillna("").astype(str).str.strip().ne("")
        work.loc[has_ambient, "ambient_provenance"] = (
            "legacy_fallback: ambient provenance was not separately recorded in this canonical input"
        )
    if legacy_ambient_fields["ambient_source_record"]:
        work["ambient_source_record"] = work["ambient_source"]
    work["ambient_metadata_legacy_fallback"] = any(legacy_ambient_fields.values())
    text_columns = [
        "image_id",
        "capture_datetime",
        "capture_timezone",
        "capture_time_source",
        "measurement_type",
        "temperature_source",
        "temperature_definition",
        "temperature_unit",
        "source_method",
        "selection_scope",
        "surface_cover_provenance",
        "luhk_provenance",
        "target_id",
        "target_name",
        "location_id",
        "location_name",
        "roi_id",
        "roi_definition",
        "roi_method",
        "roi_mask_sha256",
        "roi_comparability_evidence",
        "spatial_processing_method",
        "spatial_registration_id",
        "qa_status",
        "ambient_source",
        "ambient_definition",
        "ambient_unit",
        "ambient_data_qa_status",
        "ambient_provenance",
        "ambient_source_record",
        "dataset_id",
        "group_id",
        "visible_path",
        "thermal_path",
        "pixel_uid",
    ]
    for column in text_columns:
        work[column] = work[column].fillna("").astype(str)
    for column in (
        "temperature_c",
        "delta_t_c",
        "ambient_temperature_c",
        "thermal_row",
        "thermal_col",
        "image_height",
        "image_width",
        "gps_latitude",
        "gps_longitude",
        "roi_polygon_area_px2",
        "roi_target_pixel_count",
        "roi_target_coverage_fraction",
        "roi_boundary_overlap_fraction",
    ):
        work[column] = pd.to_numeric(work[column], errors="coerce")
    for column in ("analysis_eligible", "temperature_is_finite", "label_known", "target_mask"):
        work[column] = work[column].map(_as_bool)
    work["temperature_is_finite"] &= np.isfinite(work["temperature_c"])
    return work


def _unique_text(values: pd.Series) -> list[str]:
    return sorted({value.strip() for value in values.fillna("").astype(str) if value.strip()})


def _parse_capture_time(
    raw_values: pd.Series,
    timezone_values: pd.Series,
    default_timezone: str,
) -> tuple[pd.Timestamp | pd.NaT, pd.Timestamp | pd.NaT, str, str]:
    raw = _unique_text(raw_values)
    zones = _unique_text(timezone_values)
    if len(raw) != 1:
        reason = "capture_timestamp_missing" if not raw else "ambiguous_capture_timestamps"
        return pd.NaT, pd.NaT, reason, reason
    if len(zones) > 1:
        return pd.NaT, pd.NaT, "ambiguous_capture_timezones", "ambiguous_capture_timezones"
    try:
        stamp = pd.Timestamp(raw[0])
    except (TypeError, ValueError):
        return pd.NaT, pd.NaT, "invalid_capture_timestamp", "invalid_capture_timestamp"
    try:
        if stamp.tzinfo is None:
            zone_name = zones[0] if zones else default_timezone
            ZoneInfo(zone_name)
            stamp = stamp.tz_localize(zone_name, ambiguous="raise", nonexistent="raise")
            assumption = "capture_timezone_metadata" if zones else "default_timezone_assumed"
        else:
            assumption = "embedded_offset_or_timezone"
        local = stamp.tz_convert(default_timezone)
        utc = stamp.tz_convert("UTC")
    except (TypeError, ValueError, KeyError):
        return pd.NaT, pd.NaT, "invalid_or_ambiguous_timezone", "invalid_or_ambiguous_timezone"
    return local, utc, assumption, ""


def _stats(values: pd.Series, prefix: str) -> dict[str, float]:
    array = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)
    array = array[np.isfinite(array)]
    if not array.size:
        return {f"{prefix}_{name}_c": np.nan for name in STAT_NAMES}
    return {
        f"{prefix}_min_c": float(np.min(array)),
        f"{prefix}_max_c": float(np.max(array)),
        f"{prefix}_mean_c": float(np.mean(array)),
        f"{prefix}_median_c": float(np.median(array)),
        f"{prefix}_q01_c": float(np.quantile(array, 0.01)),
        f"{prefix}_q05_c": float(np.quantile(array, 0.05)),
        f"{prefix}_q95_c": float(np.quantile(array, 0.95)),
        f"{prefix}_q99_c": float(np.quantile(array, 0.99)),
    }


def _extreme_coordinate(group: pd.DataFrame, values: pd.Series, *, maximum: bool) -> tuple[float, float]:
    numeric = pd.to_numeric(values, errors="coerce")
    numeric = numeric.loc[np.isfinite(numeric)]
    if numeric.empty:
        return np.nan, np.nan
    index = numeric.idxmax() if maximum else numeric.idxmin()
    return float(group.loc[index, "thermal_row"]), float(group.loc[index, "thermal_col"])


def _stratum_id(row: Mapping[str, Any] | pd.Series, columns: Sequence[str]) -> str:
    payload = "|".join(f"{column}={str(row.get(column, ''))}" for column in columns)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _duplicate_image_ids(frame: pd.DataFrame) -> set[str]:
    identifiers = frame["pixel_uid"].fillna("").astype(str)
    usable = identifiers.ne("")
    if not usable.any():
        return set()
    duplicate = frame.loc[usable].assign(_pixel_uid=identifiers[usable]).duplicated(
        subset=["image_id", "_pixel_uid"], keep=False
    )
    return set(frame.loc[usable].loc[duplicate, "image_id"].astype(str))


def build_capture_summary(
    frame: pd.DataFrame,
    *,
    default_timezone: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Compatibility helper: summarize captures without creating temporal groups.

    This function intentionally does not claim same-location identity and is not
    used by :func:`run_temporal_analysis` to bypass an explicit plan.
    """

    work = _ensure_columns(frame)
    captures = _capture_summaries(work, default_timezone=default_timezone)
    inclusion_rows: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    for row in captures.itertuples(index=False):
        reasons = list(filter(None, str(row.capture_exclusion_reasons).split(";")))
        if not str(row.target_id).strip():
            reasons.append("missing_target_id_cross_capture_linkage_disabled")
            diagnostics.append(
                {
                    "image_id": row.image_id,
                    "diagnostic": "missing_target_id_for_cross_capture_linkage",
                    "severity": "warning",
                    "detail": "Capture description is allowed; explicit plan confirmation is still required for temporal grouping.",
                }
            )
        if not row.capture_time_valid:
            diagnostics.append(
                {
                    "image_id": row.image_id,
                    "diagnostic": row.capture_time_error,
                    "severity": "error",
                    "detail": "Capture excluded from chronological series.",
                }
            )
        inclusion_rows.append(
            {
                "image_id": row.image_id,
                "measurement_type": row.measurement_type,
                "source_method": row.source_method,
                "target_id": row.target_id,
                "capture_time_utc": row.capture_time_utc,
                "temperature_descriptive_included": row.analysis_eligible_count > 0,
                "temperature_trend_eligible": bool(row.temperature_base_eligible),
                "delta_t_descriptive_included": row.finite_delta_t_count > 0,
                "delta_t_trend_eligible": bool(row.delta_t_base_eligible),
                "reasons": ";".join(dict.fromkeys(reasons)),
            }
        )
    inclusion = pd.DataFrame(inclusion_rows)
    diagnostic_frame = pd.DataFrame(diagnostics, columns=["image_id", "diagnostic", "severity", "detail"])
    return captures, inclusion, diagnostic_frame


def build_stratum_summary(captures: pd.DataFrame) -> pd.DataFrame:
    """Compatibility helper for already summarized captures.

    Its output is descriptive only.  The production run path requires an
    explicit :class:`TemporalAnalysisPlan` before using any rows as a series.
    """

    rows: list[dict[str, Any]] = []
    for family, stratum_column, eligible_column, metric in (
        ("temperature", "temperature_stratum_id", "temperature_base_eligible", "temperature_mean_c"),
        ("delta_t", "delta_t_stratum_id", "delta_t_base_eligible", "delta_t_mean_c"),
    ):
        if captures.empty or stratum_column not in captures:
            continue
        for stratum_id, group in captures.groupby(stratum_column, sort=True, dropna=False, observed=True):
            valid = group.loc[group[eligible_column].astype(bool)].copy()
            valid["_time"] = pd.to_datetime(valid["capture_time_utc"], utc=True, errors="coerce")
            valid = valid.loc[valid["_time"].notna()].sort_values(["_time", "image_id"], kind="mergesort")
            intervals = valid["_time"].diff().dt.total_seconds().dropna().to_numpy(float)
            count = len(valid)
            values = pd.to_numeric(valid.get(metric, pd.Series(dtype=float)), errors="coerce")
            rows.append(
                {
                    "metric_family": family,
                    "stratum_id": str(stratum_id),
                    "compatible_capture_count": count,
                    "trend_status": (
                        "no_compatible_capture"
                        if count == 0
                        else "single_capture_descriptive_no_trend"
                        if count == 1
                        else "explicit_plan_required_before_temporal_series"
                    ),
                    "irregular_intervals": bool(
                        len(intervals) > 1 and not np.allclose(intervals, intervals[0], rtol=0, atol=1.0)
                    ),
                    "interval_seconds_json": json.dumps(intervals.tolist()),
                    "first_capture_utc": valid["capture_time_utc"].iloc[0] if count else "",
                    "last_capture_utc": valid["capture_time_utc"].iloc[-1] if count else "",
                    "equal_image_mean_of_capture_means_c": float(values.mean()) if values.notna().any() else np.nan,
                    "aggregation_policy": "equal capture weighting",
                    "interpolation": "disabled",
                    "inference": "descriptive; explicit same-location plan required",
                }
            )
    columns = [
        "metric_family",
        "stratum_id",
        "compatible_capture_count",
        "trend_status",
        "irregular_intervals",
        "interval_seconds_json",
        "first_capture_utc",
        "last_capture_utc",
        "equal_image_mean_of_capture_means_c",
        "aggregation_policy",
        "interpolation",
        "inference",
    ]
    return pd.DataFrame(rows, columns=columns)


def _capture_summaries(work: pd.DataFrame, *, default_timezone: str) -> pd.DataFrame:
    duplicate_images = _duplicate_image_ids(work)
    metadata_columns = list(
        dict.fromkeys(
            [
                "image_id",
                *TEMPERATURE_COMPATIBILITY_COLUMNS,
                "surface_cover_provenance",
                "luhk_provenance",
                "target_id",
                "target_name",
                "location_id",
                "location_name",
                "roi_id",
                "roi_mask_sha256",
                "roi_comparability_evidence",
                "qa_status",
                "spatial_processing_method",
                "spatial_registration_id",
                "ambient_source",
                "ambient_definition",
                "ambient_unit",
                "ambient_data_qa_status",
                "ambient_provenance",
                "ambient_source_record",
                "ambient_metadata_legacy_fallback",
                "dataset_id",
                "group_id",
                "visible_path",
                "thermal_path",
            ]
        )
    )
    rows: list[dict[str, Any]] = []
    for keys, group in work.groupby(metadata_columns, sort=True, dropna=False, observed=True):
        row = dict(zip(metadata_columns, keys))
        image_id = str(row["image_id"])
        local, utc, timezone_assumption, time_error = _parse_capture_time(
            group["capture_datetime"], group["capture_timezone"], default_timezone
        )
        capture_timezones = _unique_text(group["capture_timezone"])
        sources = _unique_text(group["capture_time_source"])
        normalized_sources = [value.casefold() for value in sources]
        valid_sources = [
            value for value in sources if value.strip().casefold() not in INVALID_CAPTURE_TIME_SOURCES
        ]
        upstream_time_valid = group["capture_time_valid"].map(_as_bool)
        finite = group["temperature_is_finite"].astype(bool) & np.isfinite(group["temperature_c"])
        eligible = group["analysis_eligible"].astype(bool) & group["target_mask"].astype(bool) & finite
        delta_values = pd.to_numeric(group["delta_t_c"], errors="coerce")
        delta_eligible = eligible & np.isfinite(delta_values)
        target = group["target_mask"].astype(bool)
        known = group["label_known"].astype(bool)
        ambient_values = pd.to_numeric(group["ambient_temperature_c"], errors="coerce")
        ambient_unique = np.unique(np.round(ambient_values[np.isfinite(ambient_values)], 7))
        gps_pairs = {
            (round(float(latitude), 8), round(float(longitude), 8))
            for latitude, longitude in zip(group["gps_latitude"], group["gps_longitude"])
            if np.isfinite(latitude) and np.isfinite(longitude)
            and -90.0 <= float(latitude) <= 90.0
            and -180.0 <= float(longitude) <= 180.0
        }
        errors: list[str] = []
        if time_error:
            errors.append(time_error)
        if not upstream_time_valid.all():
            errors.append("capture_time_marked_invalid")
        if image_id in duplicate_images:
            errors.append("duplicate_image_pixel_identifiers")
        if len(sources) > 1:
            errors.append("ambiguous_capture_time_sources")
        if not valid_sources or any(value in INVALID_CAPTURE_TIME_SOURCES for value in normalized_sources):
            errors.append("capture_time_source_missing")
        if _metadata_missing(row["temperature_source"]):
            errors.append("temperature_source_missing")
        if _metadata_missing(row["temperature_definition"]):
            errors.append("temperature_definition_missing")
        if _metadata_missing(row["temperature_unit"]):
            errors.append("temperature_unit_missing")
        if not eligible.any():
            errors.append("no_analysis_eligible_target_measurements")
        time_reasons = [
            value
            for value in errors
            if value
            in {
                "capture_timestamp_missing",
                "ambiguous_capture_timestamps",
                "invalid_capture_timestamp",
                "ambiguous_capture_timezones",
                "invalid_or_ambiguous_timezone",
                "capture_time_marked_invalid",
                "capture_time_source_missing",
                "ambiguous_capture_time_sources",
            }
        ]
        capture_time_valid = bool(not time_reasons and pd.notna(utc))
        roi_area_values = pd.to_numeric(group["roi_polygon_area_px2"], errors="coerce")
        roi_pixel_values = pd.to_numeric(group["roi_target_pixel_count"], errors="coerce")
        roi_coverage_values = pd.to_numeric(group["roi_target_coverage_fraction"], errors="coerce")
        roi_overlap_values = pd.to_numeric(group["roi_boundary_overlap_fraction"], errors="coerce")

        def _single_finite(values: pd.Series) -> float:
            unique = np.unique(np.round(values[np.isfinite(values)], 10))
            return float(unique[0]) if len(unique) == 1 else np.nan

        gps_pair = next(iter(gps_pairs)) if len(gps_pairs) == 1 else (np.nan, np.nan)
        row.update(
            {
                "capture_time_local": local.isoformat() if pd.notna(local) else "",
                "capture_time_utc": utc.isoformat() if pd.notna(utc) else "",
                "capture_timezone_source": capture_timezones[0] if len(capture_timezones) == 1 else "",
                "capture_timezone_output": default_timezone,
                "capture_time_source": valid_sources[0] if len(valid_sources) == 1 and len(sources) == 1 else "",
                "timezone_assumption": timezone_assumption,
                "capture_time_valid": capture_time_valid,
                "capture_time_error": ";".join(dict.fromkeys(time_reasons)),
                "duplicate_image_id": image_id in duplicate_images,
                "ambient_temperature_c": float(ambient_unique[0]) if len(ambient_unique) == 1 else np.nan,
                "ambient_available": bool(delta_eligible.any()),
                "gps_latitude": gps_pair[0],
                "gps_longitude": gps_pair[1],
                "total_measurement_count": int(len(group)),
                "finite_temperature_count": int(finite.sum()),
                "analysis_eligible_count": int(eligible.sum()),
                "finite_delta_t_count": int(delta_eligible.sum()),
                "target_measurement_count": int(target.sum()),
                "target_coverage_fraction": float(target.mean()) if len(target) else np.nan,
                "roi_polygon_area_px2": _single_finite(roi_area_values),
                "roi_target_pixel_count": (
                    _single_finite(roi_pixel_values)
                    if np.isfinite(_single_finite(roi_pixel_values))
                    else float(target.sum())
                ),
                "roi_target_coverage_fraction": (
                    _single_finite(roi_coverage_values)
                    if np.isfinite(_single_finite(roi_coverage_values))
                    else (float(target.mean()) if len(target) else np.nan)
                ),
                "roi_boundary_overlap_fraction": _single_finite(roi_overlap_values),
                "known_label_count": int(known.sum()),
                "unknown_label_count": int((~known).sum()),
                "capture_exclusion_reasons": ";".join(dict.fromkeys(errors)),
                "temporal_unit": "one confirmed capture of one physical target",
            }
        )
        row.update(_stats(group.loc[eligible, "temperature_c"], "temperature"))
        row.update(_stats(group.loc[delta_eligible, "delta_t_c"], "delta_t"))
        min_row, min_col = _extreme_coordinate(group.loc[eligible], group.loc[eligible, "temperature_c"], maximum=False)
        max_row, max_col = _extreme_coordinate(group.loc[eligible], group.loc[eligible, "temperature_c"], maximum=True)
        dmin_row, dmin_col = _extreme_coordinate(group.loc[delta_eligible], group.loc[delta_eligible, "delta_t_c"], maximum=False)
        dmax_row, dmax_col = _extreme_coordinate(group.loc[delta_eligible], group.loc[delta_eligible, "delta_t_c"], maximum=True)
        row.update(
            {
                "temperature_min_row": min_row,
                "temperature_min_col": min_col,
                "temperature_max_row": max_row,
                "temperature_max_col": max_col,
                "delta_t_min_row": dmin_row,
                "delta_t_min_col": dmin_col,
                "delta_t_max_row": dmax_row,
                "delta_t_max_col": dmax_col,
            }
        )
        row["temperature_stratum_id"] = _stratum_id(row, TEMPERATURE_COMPATIBILITY_COLUMNS)
        row["delta_t_stratum_id"] = _stratum_id(row, DELTA_T_COMPATIBILITY_COLUMNS)
        row["temperature_base_eligible"] = bool(not errors and eligible.any())
        delta_errors = list(errors)
        if len(ambient_unique) > 1:
            delta_errors.append("ambiguous_ambient_values_within_capture")
        if _metadata_missing(row["ambient_source"]):
            delta_errors.append("ambient_source_missing")
        if _metadata_missing(row["ambient_definition"]):
            delta_errors.append("ambient_definition_missing")
        if _metadata_missing(row["ambient_unit"]):
            delta_errors.append("ambient_unit_missing")
        if not delta_eligible.any():
            delta_errors.append("ambient_temperature_or_delta_t_missing")
        row["delta_t_exclusion_reasons"] = ";".join(dict.fromkeys(delta_errors))
        row["delta_t_base_eligible"] = bool(not delta_errors and delta_eligible.any())
        rows.append(row)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(
        ["capture_time_utc", "image_id", "temperature_stratum_id"], kind="mergesort"
    ).reset_index(drop=True)


def _identity_conflicts(work: pd.DataFrame, definition: TemporalGroupDefinition) -> list[str]:
    conflicts: list[str] = []
    for column, expected in (("location_id", definition.location_id), ("target_id", definition.target_id)):
        values = _unique_text(work[column])
        if len(values) > 1:
            conflicts.append(f"conflicting_{column}s:{','.join(values)}")
        elif values and values[0] != expected:
            conflicts.append(f"{column}_mismatch:recorded={values[0]}:confirmed={expected}")
    recorded_target_names = _unique_text(work["target_name"])
    normalized_target_names = {value.casefold() for value in recorded_target_names}
    if len(normalized_target_names) > 1:
        conflicts.append(f"conflicting_target_names:{','.join(recorded_target_names)}")
    elif (
        recorded_target_names
        and definition.target_name
        and recorded_target_names[0].casefold() != definition.target_name.casefold()
    ):
        conflicts.append(
            f"target_name_mismatch:recorded={recorded_target_names[0]}:confirmed={definition.target_name}"
        )
    recorded_registration_ids = _unique_text(work["spatial_registration_id"])
    if len(recorded_registration_ids) > 1:
        conflicts.append(f"conflicting_spatial_registration_ids:{','.join(recorded_registration_ids)}")
    elif (
        definition.registration_confirmed
        and recorded_registration_ids
        and recorded_registration_ids[0] != definition.registration_id
    ):
        conflicts.append(
            "spatial_registration_id_mismatch:"
            f"recorded={recorded_registration_ids[0]}:confirmed={definition.registration_id}"
        )
    for image_id, group in work.groupby("image_id", sort=True, observed=True):
        overlap = pd.to_numeric(group["roi_boundary_overlap_fraction"], errors="coerce")
        finite_overlap = overlap[np.isfinite(overlap)]
        if not finite_overlap.empty and float(finite_overlap.min()) <= 0.0:
            conflicts.append(f"accepted_roi_non_overlap:{image_id}")
    coordinates: dict[str, tuple[float, float]] = {}
    for image_id, group in work.groupby("image_id", sort=True, observed=True):
        pairs: set[tuple[float, float]] = set()
        invalid_coordinate = False
        for latitude, longitude in zip(group["gps_latitude"], group["gps_longitude"]):
            if not (np.isfinite(latitude) and np.isfinite(longitude)):
                continue
            latitude_value = float(latitude)
            longitude_value = float(longitude)
            if not (-90.0 <= latitude_value <= 90.0 and -180.0 <= longitude_value <= 180.0):
                invalid_coordinate = True
                continue
            pairs.add((round(latitude_value, 8), round(longitude_value, 8)))
        if invalid_coordinate:
            conflicts.append(f"invalid_gps_coordinates:{image_id}")
        if len(pairs) > 1:
            conflicts.append(f"ambiguous_gps_coordinates_within_capture:{image_id}")
        elif len(pairs) == 1:
            coordinates[str(image_id)] = next(iter(pairs))
    coordinate_items = sorted(coordinates.items())
    for index, (first_id, first) in enumerate(coordinate_items):
        for second_id, second in coordinate_items[index + 1 :]:
            distance = _haversine_distance_m(first[0], first[1], second[0], second[1])
            if distance > definition.gps_conflict_threshold_m:
                conflicts.append(
                    f"gps_distance_conflict:{first_id}:{second_id}:"
                    f"{distance:.1f}m>{definition.gps_conflict_threshold_m:.1f}m"
                )
    return conflicts


def _haversine_distance_m(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    radius_m = 6_371_008.8
    phi_a = math.radians(latitude_a)
    phi_b = math.radians(latitude_b)
    delta_phi = math.radians(latitude_b - latitude_a)
    delta_lambda = math.radians(longitude_b - longitude_a)
    value = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi_a) * math.cos(phi_b) * math.sin(delta_lambda / 2.0) ** 2
    )
    return 2.0 * radius_m * math.atan2(math.sqrt(value), math.sqrt(max(0.0, 1.0 - value)))


def spatial_identity_conflicts(
    frame: pd.DataFrame,
    definition: TemporalGroupDefinition,
) -> list[str]:
    """Return target/location/GPS conflicts for a submitted temporal group."""

    work = _ensure_columns(frame)
    selected = work.loc[work["image_id"].isin(definition.image_ids)]
    return _identity_conflicts(selected, definition) if not selected.empty else []


def _apply_group_gates(
    captures: pd.DataFrame,
    definition: TemporalGroupDefinition,
    conflicts: list[str],
) -> pd.DataFrame:
    work = captures.copy()
    if work.empty:
        return work
    work["group_gate_reasons"] = ""
    reasons: list[str] = []
    if not definition.same_location_confirmed:
        reasons.append("same_physical_location_not_confirmed")
    if not definition.roi_comparable_confirmed:
        reasons.append("comparable_target_roi_not_confirmed")
    if conflicts and not definition.spatial_override_confirmed:
        reasons.extend(conflicts)
    if conflicts and definition.spatial_override_confirmed and not definition.spatial_override_reason:
        reasons.append("spatial_override_reason_missing")
    work["qa_acceptable"] = work["qa_status"].astype(str).str.casefold().isin(definition.allowed_qa_statuses)
    work.loc[~work["qa_acceptable"], "group_gate_reasons"] = "qa_status_not_accepted"
    if reasons:
        shared = ";".join(reasons)
        work["group_gate_reasons"] = work["group_gate_reasons"].map(
            lambda value: ";".join(filter(None, [str(value), shared]))
        )
    work["temperature_series_eligible"] = (
        work["temperature_base_eligible"].astype(bool)
        & work["qa_acceptable"].astype(bool)
        & work["group_gate_reasons"].eq("")
    )
    work["delta_t_series_eligible"] = (
        work["delta_t_base_eligible"].astype(bool)
        & work["qa_acceptable"].astype(bool)
        & work["group_gate_reasons"].eq("")
    )
    for stratum_column, eligible_column in (
        ("temperature_stratum_id", "temperature_series_eligible"),
        ("delta_t_stratum_id", "delta_t_series_eligible"),
    ):
        candidates = work.loc[work[eligible_column].astype(bool)].copy()
        duplicate = candidates.duplicated(subset=[stratum_column, "capture_time_utc"], keep=False)
        for index in candidates.loc[duplicate].index:
            work.loc[index, eligible_column] = False
            current = str(work.loc[index, "group_gate_reasons"])
            work.loc[index, "group_gate_reasons"] = ";".join(
                filter(None, [current, "duplicate_capture_timestamp_within_compatibility_stratum"])
            )
    return work


def _window_bounds(value: Mapping[str, str], default_timezone: str) -> tuple[str, pd.Timestamp, pd.Timestamp]:
    identifier = str(value.get("observation_window_id", value.get("window_id", ""))).strip()
    if not identifier:
        raise ValueError("Every observation window requires observation_window_id.")
    start = pd.Timestamp(str(value.get("start", value.get("start_local", ""))))
    end = pd.Timestamp(str(value.get("end", value.get("end_local", ""))))
    if start.tzinfo is None:
        start = start.tz_localize(default_timezone)
    if end.tzinfo is None:
        end = end.tz_localize(default_timezone)
    if end <= start:
        raise ValueError(f"Observation window {identifier!r} must end after it starts.")
    return identifier, start.tz_convert("UTC"), end.tz_convert("UTC")


def _windowed_captures(
    captures: pd.DataFrame,
    definition: TemporalGroupDefinition,
    default_timezone: str,
) -> pd.DataFrame:
    if captures.empty:
        result = captures.copy()
        result["observation_window_id"] = pd.Series(dtype=str)
        return result
    work = captures.copy()
    work["_utc"] = pd.to_datetime(work["capture_time_utc"], utc=True, errors="coerce")
    rows: list[pd.DataFrame] = []
    if definition.observation_windows:
        for value in definition.observation_windows:
            identifier, start, end = _window_bounds(value, default_timezone)
            selected = work.loc[work["_utc"].between(start, end, inclusive="both")].copy()
            selected["observation_window_id"] = identifier
            rows.append(selected)
    else:
        work["observation_window_id"] = work["_utc"].dt.tz_convert(default_timezone).dt.strftime("%Y-%m-%d")
        work.loc[work["_utc"].isna(), "observation_window_id"] = "timestamp-unavailable"
        rows.append(work)
    return pd.concat(rows, ignore_index=True) if rows else work.iloc[0:0].copy()


def _range_row(
    valid: pd.DataFrame,
    *,
    family: str,
    statistic: str,
    stratum_id: str,
    window_id: str,
) -> dict[str, Any]:
    prefix = "temperature" if family == "temperature" else "delta_t"
    value_column = f"{prefix}_{statistic}_c"
    count = int(valid["image_id"].nunique())
    base = {
        "metric_family": family,
        "statistic": statistic,
        "primary_representative": statistic == "mean",
        "stratum_id": stratum_id,
        "observation_window_id": window_id,
        "eligible_capture_count": count,
        "available": False,
        "unavailable_reason": "fewer_than_two_compatible_captures" if count < 2 else "",
    }
    if family == "delta_t":
        base.update(
            {
                "ambient_source": ";".join(_unique_text(valid["ambient_source"])),
                "ambient_definition": ";".join(_unique_text(valid["ambient_definition"])),
                "ambient_unit": ";".join(_unique_text(valid["ambient_unit"])),
                "ambient_data_qa_statuses": ";".join(_unique_text(valid["ambient_data_qa_status"])),
                "ambient_provenance": ";".join(_unique_text(valid["ambient_provenance"])),
                "ambient_source_records": ";".join(_unique_text(valid["ambient_source_record"])),
                "ambient_metadata_legacy_fallback": bool(
                    valid["ambient_metadata_legacy_fallback"].map(_as_bool).any()
                ),
            }
        )
    if count < 2:
        return base
    if statistic == "absolute_pixel":
        high_index = pd.to_numeric(valid[f"{prefix}_max_c"], errors="coerce").idxmax()
        low_index = pd.to_numeric(valid[f"{prefix}_min_c"], errors="coerce").idxmin()
        high = valid.loc[high_index]
        low = valid.loc[low_index]
        high_value = float(high[f"{prefix}_max_c"])
        low_value = float(low[f"{prefix}_min_c"])
        high_row = float(high[f"{prefix}_max_row"])
        high_col = float(high[f"{prefix}_max_col"])
        low_row = float(low[f"{prefix}_min_row"])
        low_col = float(low[f"{prefix}_min_col"])
    else:
        values = pd.to_numeric(valid[value_column], errors="coerce")
        finite = values.loc[np.isfinite(values)]
        if finite.empty:
            return {**base, "unavailable_reason": f"{value_column}_missing"}
        high = valid.loc[finite.idxmax()]
        low = valid.loc[finite.idxmin()]
        high_value = float(finite.max())
        low_value = float(finite.min())
        high_row = high_col = low_row = low_col = np.nan
    high_time = pd.Timestamp(high["capture_time_utc"])
    low_time = pd.Timestamp(low["capture_time_utc"])
    return {
        **base,
        "available": True,
        "unavailable_reason": "",
        "observed_max_c": high_value,
        "observed_max_time_local": high["capture_time_local"],
        "observed_max_time_utc": high["capture_time_utc"],
        "observed_max_image_id": high["image_id"],
        "observed_max_row": high_row,
        "observed_max_col": high_col,
        "observed_min_c": low_value,
        "observed_min_time_local": low["capture_time_local"],
        "observed_min_time_utc": low["capture_time_utc"],
        "observed_min_image_id": low["image_id"],
        "observed_min_row": low_row,
        "observed_min_col": low_col,
        "observed_peak_to_trough_range_c": high_value - low_value,
        "max_min_time_interval_hours": abs((high_time - low_time).total_seconds()) / 3600.0,
    }


def _range_tables(windowed: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    temperature_rows: list[dict[str, Any]] = []
    delta_rows: list[dict[str, Any]] = []
    if windowed.empty:
        return pd.DataFrame(), pd.DataFrame()
    for (stratum_id, window_id), group in windowed.groupby(
        ["temperature_stratum_id", "observation_window_id"], sort=True, dropna=False, observed=True
    ):
        valid = group.loc[group["temperature_series_eligible"].astype(bool)].copy()
        for statistic in ("mean", "median", "q95", "max", "absolute_pixel"):
            temperature_rows.append(
                _range_row(
                    valid,
                    family="temperature",
                    statistic=statistic,
                    stratum_id=str(stratum_id),
                    window_id=str(window_id),
                )
            )
    for (stratum_id, window_id), group in windowed.groupby(
        ["delta_t_stratum_id", "observation_window_id"], sort=True, dropna=False, observed=True
    ):
        valid = group.loc[group["delta_t_series_eligible"].astype(bool)].copy()
        for statistic in ("mean", "median", "q95", "max", "absolute_pixel"):
            delta_rows.append(
                _range_row(
                    valid,
                    family="delta_t",
                    statistic=statistic,
                    stratum_id=str(stratum_id),
                    window_id=str(window_id),
                )
            )
    return pd.DataFrame(temperature_rows), pd.DataFrame(delta_rows)


def _sampling_coverage(windowed: pd.DataFrame, definition: TemporalGroupDefinition) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if windowed.empty:
        return pd.DataFrame()
    for (stratum_id, window_id), group in windowed.groupby(
        ["temperature_stratum_id", "observation_window_id"], sort=True, dropna=False, observed=True
    ):
        valid = group.loc[group["temperature_series_eligible"].astype(bool)].copy()
        valid["_utc"] = pd.to_datetime(valid["capture_time_utc"], utc=True, errors="coerce")
        valid["_local"] = pd.to_datetime(valid["capture_time_local"], errors="coerce")
        valid = valid.loc[valid["_utc"].notna()].sort_values(["_utc", "image_id"], kind="mergesort")
        intervals = valid["_utc"].diff().dt.total_seconds().dropna().to_numpy(float)
        gaps = [
            {
                "start_utc": valid.iloc[index - 1]["capture_time_utc"],
                "end_utc": valid.iloc[index]["capture_time_utc"],
                "duration_hours": float((valid.iloc[index]["_utc"] - valid.iloc[index - 1]["_utc"]).total_seconds() / 3600),
            }
            for index in range(1, len(valid))
        ]
        hours = valid["_local"].dt.hour if not valid.empty else pd.Series(dtype=int)
        daytime = bool(((hours >= 6) & (hours < 18)).any())
        nighttime = bool(((hours < 6) | (hours >= 18)).any())
        span_hours = (
            float((valid["_utc"].iloc[-1] - valid["_utc"].iloc[0]).total_seconds() / 3600)
            if len(valid) >= 2
            else 0.0
        )
        largest_gap_hours = float(intervals.max() / 3600) if intervals.size else np.nan
        true_daily = bool(
            definition.full_day_sampling_confirmed
            and len(valid) >= 6
            and daytime
            and nighttime
            and span_hours >= 23
            and np.isfinite(largest_gap_hours)
            and largest_gap_hours <= 4.0
        )
        if len(valid) == 0:
            status = "no_eligible_capture"
        elif len(valid) == 1:
            status = "single_capture"
        elif true_daily:
            status = "full_day_sampling_design_confirmed"
        elif daytime and nighttime:
            status = "day_and_night_observed_but_daily_extrema_not_established"
        else:
            status = "partial_observation_window"
        rows.append(
            {
                "stratum_id": str(stratum_id),
                "observation_window_id": str(window_id),
                "eligible_capture_count": len(valid),
                "observation_start_local": valid["capture_time_local"].iloc[0] if len(valid) else "",
                "observation_end_local": valid["capture_time_local"].iloc[-1] if len(valid) else "",
                "observation_start_utc": valid["capture_time_utc"].iloc[0] if len(valid) else "",
                "observation_end_utc": valid["capture_time_utc"].iloc[-1] if len(valid) else "",
                "observation_span_hours": span_hours,
                "interval_seconds_json": json.dumps(intervals.tolist()),
                "largest_interval_hours": largest_gap_hours,
                "missing_periods_json": json.dumps(gaps),
                "daytime_present": daytime,
                "nighttime_present": nighttime,
                "day_night_definition": "daytime=06:00-17:59 local; nighttime=18:00-05:59 local",
                "sampling_coverage_status": status,
                "true_daily_extrema_supported": true_daily,
                "full_day_sampling_confirmed": definition.full_day_sampling_confirmed,
                "full_day_minimum_capture_count": 6,
                "full_day_maximum_gap_hours": 4.0,
                "full_day_gate_failures": ";".join(
                    value
                    for value, failed in (
                        ("full_day_sampling_not_confirmed", not definition.full_day_sampling_confirmed),
                        ("fewer_than_six_eligible_captures", len(valid) < 6),
                        ("daytime_not_represented", not daytime),
                        ("nighttime_not_represented", not nighttime),
                        ("observation_span_less_than_23_hours", span_hours < 23),
                        (
                            "maximum_sampling_gap_exceeds_four_hours",
                            not np.isfinite(largest_gap_hours) or largest_gap_hours > 4.0,
                        ),
                    )
                    if failed
                ),
                "coverage_statement": (
                    "The confirmed sampling design meets the full-day evidence gate: at least six captures, day "
                    "and night observations, at least 23 hours of span, and no sampling gap longer than four hours."
                    if true_daily
                    else "Results are observed within the sampled window; the true daily maximum or minimum may be unobserved. "
                    "A full-day claim requires explicit confirmation, at least six captures, day and night observations, "
                    "at least 23 hours of span, and no gap longer than four hours."
                ),
            }
        )
    return pd.DataFrame(rows)


def _save_figure(fig: plt.Figure, directory: Path, stem: str) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    paths = [directory / f"{stem}.png", directory / f"{stem}.pdf"]
    fig.savefig(paths[0], dpi=180, bbox_inches="tight", facecolor="white")
    fig.savefig(paths[1], bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return paths


def _series_groups(windowed: pd.DataFrame, *, family: str) -> list[tuple[str, str, pd.DataFrame]]:
    stratum = "temperature_stratum_id" if family == "temperature" else "delta_t_stratum_id"
    eligible = "temperature_series_eligible" if family == "temperature" else "delta_t_series_eligible"
    groups: list[tuple[str, str, pd.DataFrame]] = []
    if windowed.empty:
        return groups
    for (stratum_id, window_id), group in windowed.groupby(
        [stratum, "observation_window_id"], sort=True, dropna=False, observed=True
    ):
        valid = group.loc[group[eligible].astype(bool)].copy()
        valid["_time"] = pd.to_datetime(valid["capture_time_local"], errors="coerce")
        valid = valid.loc[valid["_time"].notna()].sort_values(["_time", "image_id"], kind="mergesort")
        if valid["image_id"].nunique() >= 2:
            groups.append((str(stratum_id), str(window_id), valid))
    return groups


def _plot_temperature_series(windowed: pd.DataFrame, directory: Path, *, family: str) -> list[Path]:
    groups = _series_groups(windowed, family=family)
    if not groups:
        return []
    prefix = "temperature" if family == "temperature" else "delta_t"
    title = "Target temperature versus local time" if family == "temperature" else "Target ΔT versus local time"
    stem = "target_temperature_vs_local_time" if family == "temperature" else "target_delta_t_vs_local_time"
    figure, axis = plt.subplots(figsize=(12, 6), facecolor="white")
    for index, (stratum_id, window_id, valid) in enumerate(groups):
        color = plt.get_cmap("tab10")(index % 10)
        label = f"{window_id} / {stratum_id[:8]}"
        axis.plot(valid["_time"], valid[f"{prefix}_mean_c"], marker="o", color=color, label=f"mean — {label}")
        axis.plot(
            valid["_time"], valid[f"{prefix}_median_c"], marker=".", linestyle="--", color=color,
            alpha=0.85, label=f"median — {label}",
        )
        axis.plot(valid["_time"], valid[f"{prefix}_max_c"], marker="^", linestyle=":", color=color, alpha=0.7)
        axis.fill_between(
            valid["_time"],
            pd.to_numeric(valid[f"{prefix}_q05_c"], errors="coerce"),
            pd.to_numeric(valid[f"{prefix}_q95_c"], errors="coerce"),
            color=color,
            alpha=0.12,
        )
        for _, row in valid.iterrows():
            axis.annotate(
                str(row["image_id"]),
                (row["_time"], row[f"{prefix}_mean_c"]),
                fontsize=7,
                xytext=(3, 3),
                textcoords="offset points",
            )
        means = pd.to_numeric(valid[f"{prefix}_mean_c"], errors="coerce")
        finite_means = means.loc[np.isfinite(means)]
        if len(finite_means) >= 2:
            high = valid.loc[finite_means.idxmax()]
            low = valid.loc[finite_means.idxmin()]
            high_mean = float(high[f"{prefix}_mean_c"])
            low_mean = float(low[f"{prefix}_mean_c"])
            observed_range = float(finite_means.max() - finite_means.min())
            axis.scatter(
                [high["_time"], low["_time"]],
                [high[f"{prefix}_mean_c"], low[f"{prefix}_mean_c"]],
                marker="*",
                s=125,
                color=["#D55E00", "#0072B2"],
                edgecolor="white",
                linewidth=0.6,
                zorder=5,
            )
            axis.annotate(
                f"observed max\n{high_mean:.2f}°C",
                (high["_time"], high[f"{prefix}_mean_c"]),
                xytext=(8, 14),
                textcoords="offset points",
                fontsize=8,
            )
            axis.annotate(
                f"observed min\n{low_mean:.2f}°C\nΔ={observed_range:.2f}°C",
                (low["_time"], low[f"{prefix}_mean_c"]),
                xytext=(8, -38),
                textcoords="offset points",
                fontsize=8,
            )
    axis.set_title(title)
    axis.set_xlabel("Local capture time (observations only; no interpolation)")
    axis.set_ylabel("Temperature (°C)" if family == "temperature" else "ΔT (°C)")
    axis.grid(alpha=0.2)
    axis.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), fontsize=8, frameon=False)
    figure.text(0.01, 0.01, "q05–q95 bands describe within-capture spatial variation, not temporal confidence intervals.", fontsize=9)
    figure.subplots_adjust(bottom=0.28)
    return _save_figure(figure, directory, stem)


def _plot_range_summary(peaks: pd.DataFrame, directory: Path) -> list[Path]:
    available = peaks.loc[peaks.get("available", pd.Series(dtype=bool)).astype(bool)].copy()
    if available.empty:
        return []
    labels = (
        available["observation_window_id"].astype(str)
        + "\n"
        + available["statistic"].astype(str)
        + "\n"
        + available["stratum_id"].astype(str).str[:8]
    )
    values = pd.to_numeric(available["observed_peak_to_trough_range_c"], errors="coerce")
    figure, axis = plt.subplots(figsize=(max(9, len(available) * 1.4), 5.5), facecolor="white")
    bars = axis.bar(np.arange(len(available)), values, color=np.where(available["primary_representative"], "#D55E00", "#0072B2"))
    axis.bar_label(bars, fmt="%.2f°C", padding=3, fontsize=8)
    axis.set_xticks(np.arange(len(available)), labels, rotation=20, ha="right", fontsize=8)
    axis.set_ylabel("Observed peak-to-trough difference (°C)")
    axis.set_title("Observed target peak-to-trough summary")
    axis.grid(axis="y", alpha=0.2)
    figure.tight_layout()
    return _save_figure(figure, directory, "observed_peak_to_trough_summary")


def _plot_sampling_timeline(windowed: pd.DataFrame, directory: Path) -> list[Path]:
    groups = _series_groups(windowed, family="temperature")
    if not groups:
        return []
    figure, axis = plt.subplots(figsize=(12, max(3.5, len(groups) * 0.8 + 2)), facecolor="white")
    labels: list[str] = []
    for index, (stratum_id, window_id, valid) in enumerate(groups):
        labels.append(f"{window_id} / {stratum_id[:8]}")
        axis.scatter(valid["_time"], np.full(len(valid), index), s=55, color="#009E73")
        if len(valid) >= 2:
            axis.plot(valid["_time"], np.full(len(valid), index), color="#999999", linewidth=1)
        for _, row in valid.iterrows():
            axis.annotate(
                str(row["image_id"]),
                (row["_time"], index),
                fontsize=7,
                xytext=(3, 4),
                textcoords="offset points",
            )
    axis.set_yticks(np.arange(len(labels)), labels)
    axis.set_xlabel("Local capture time")
    axis.set_title("Sampling-coverage timeline (gaps are not interpolated)")
    axis.grid(axis="x", alpha=0.2)
    figure.tight_layout()
    return _save_figure(figure, directory, "sampling_coverage_timeline")


def _pixelwise_analysis(
    raw: pd.DataFrame,
    windowed: pd.DataFrame,
    definition: TemporalGroupDefinition,
    directory: Path,
) -> tuple[bool, str, list[Path]]:
    if not definition.registration_confirmed:
        return False, "cross_capture_registration_not_confirmed", []
    eligible_pairs = (
        windowed.loc[
            windowed["temperature_series_eligible"].astype(bool),
            ["temperature_stratum_id", "observation_window_id"],
        ]
        .drop_duplicates()
    )
    if len(eligible_pairs) > 1:
        return False, "multiple_compatibility_strata_or_observation_windows", []
    series = _series_groups(windowed, family="temperature")
    if not series:
        return False, "no_compatible_multi_capture_temperature_series", []
    if len(series) != 1:
        return False, "multiple_compatibility_strata_or_observation_windows", []
    stratum_id, window_id, captures = series[0]
    recorded_registration_ids = _unique_text(captures["spatial_registration_id"])
    if len(recorded_registration_ids) > 1:
        return False, "ambiguous_spatial_registration_ids", []
    if recorded_registration_ids and recorded_registration_ids[0] != definition.registration_id:
        return False, "spatial_registration_id_mismatch", []
    selected_ids = captures["image_id"].astype(str).tolist()
    shape: tuple[int, int] | None = None
    matrices: list[np.ndarray] = []
    masks: list[np.ndarray] = []
    times: list[str] = []
    reference_capture = captures.iloc[0]
    for image_id in selected_ids:
        rows = raw.loc[raw["image_id"].eq(image_id)].copy()
        for column in TEMPERATURE_COMPATIBILITY_COLUMNS:
            rows = rows.loc[rows[column].astype(str).eq(str(reference_capture[column]))]
        if rows.empty or rows.duplicated(subset=["thermal_row", "thermal_col"]).any():
            return False, f"pixel_grid_missing_or_duplicate:{image_id}", []
        row_values = pd.to_numeric(rows["thermal_row"], errors="coerce")
        col_values = pd.to_numeric(rows["thermal_col"], errors="coerce")
        if row_values.isna().any() or col_values.isna().any():
            return False, f"pixel_coordinates_missing:{image_id}", []
        current_shape = (int(row_values.max()) + 1, int(col_values.max()) + 1)
        if len(rows) != current_shape[0] * current_shape[1]:
            return False, f"pixel_grid_incomplete:{image_id}", []
        if shape is None:
            shape = current_shape
        elif current_shape != shape:
            return False, "registered_capture_shapes_differ", []
        ordered = rows.sort_values(["thermal_row", "thermal_col"], kind="mergesort")
        matrix = pd.to_numeric(ordered["temperature_c"], errors="coerce").to_numpy(float).reshape(current_shape)
        mask = (
            ordered["analysis_eligible"].astype(bool).to_numpy()
            & ordered["target_mask"].astype(bool).to_numpy()
            & ordered["temperature_is_finite"].astype(bool).to_numpy()
            & np.isfinite(matrix.ravel())
        ).reshape(current_shape)
        matrices.append(matrix)
        masks.append(mask)
        times.append(str(captures.loc[captures["image_id"].eq(image_id), "capture_time_local"].iloc[0]))
    assert shape is not None
    common = np.logical_and.reduce(masks)
    if not common.any():
        return False, "registered_target_intersection_empty", []
    stack = np.stack(matrices, axis=0)
    maximum = np.full(shape, np.nan, dtype=float)
    minimum = np.full(shape, np.nan, dtype=float)
    maximum[common] = np.max(stack[:, common], axis=0)
    minimum[common] = np.min(stack[:, common], axis=0)
    observed_range = maximum - minimum
    argmax = np.argmax(np.where(np.isfinite(stack), stack, -np.inf), axis=0)
    argmin = np.argmin(np.where(np.isfinite(stack), stack, np.inf), axis=0)
    directory.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for stem, array in (
        ("pixelwise_observed_max_temperature", maximum),
        ("pixelwise_observed_min_temperature", minimum),
        ("pixelwise_observed_temperature_range", observed_range),
    ):
        path = directory / f"{stem}.npy"
        np.save(path, array.astype(np.float32), allow_pickle=False)
        paths.append(path)
    coordinates = np.argwhere(common)
    order = np.argsort(observed_range[common])[::-1][: min(20, int(common.sum()))]
    largest_rows: list[dict[str, Any]] = []
    for rank, coordinate_index in enumerate(order, start=1):
        row, col = coordinates[coordinate_index]
        high_index = int(argmax[row, col])
        low_index = int(argmin[row, col])
        largest_rows.append(
            {
                "rank": rank,
                "thermal_row": int(row),
                "thermal_col": int(col),
                "observed_range_c": float(observed_range[row, col]),
                "observed_max_c": float(maximum[row, col]),
                "observed_max_image_id": selected_ids[high_index],
                "observed_max_time_local": times[high_index],
                "observed_min_c": float(minimum[row, col]),
                "observed_min_image_id": selected_ids[low_index],
                "observed_min_time_local": times[low_index],
                "registration_method": definition.registration_method,
                "registration_id": definition.registration_id,
                "stratum_id": stratum_id,
                "observation_window_id": window_id,
            }
        )
    changes_path = directory / "pixelwise_largest_observed_changes.csv"
    _write_csv(pd.DataFrame(largest_rows), changes_path)
    paths.append(changes_path)
    figure, axes = plt.subplots(1, 3, figsize=(15, 5), facecolor="white")
    for axis, array, title in zip(
        axes,
        (maximum, minimum, observed_range),
        ("Observed pixel maximum", "Observed pixel minimum", "Observed pixel range"),
    ):
        image = axis.imshow(array, cmap="inferno")
        axis.set_title(title)
        axis.set_xlabel("Thermal column")
        axis.set_ylabel("Thermal row")
        figure.colorbar(image, ax=axis, fraction=0.046, pad=0.04, label="°C")
    figure.suptitle(
        f"Registered pixelwise temporal results — {definition.registration_method} / {definition.registration_id}"
    )
    figure.tight_layout()
    paths.extend(_save_figure(figure, directory, "pixelwise_temporal_range_maps"))
    return True, "", paths


def _submitted_table(definition: TemporalGroupDefinition, available_ids: set[str]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "selection_number": index,
                "image_id": image_id,
                "submitted": True,
                "canonical_input_available": image_id in available_ids,
                "submission_status": "available" if image_id in available_ids else "image_id_not_found",
            }
            for index, image_id in enumerate(definition.image_ids, start=1)
        ]
    )


def _exclusion_table(definition: TemporalGroupDefinition, captures: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    present = set(captures["image_id"].astype(str)) if not captures.empty else set()
    for image_id in definition.image_ids:
        if image_id not in present:
            rows.append(
                {
                    "image_id": image_id,
                    "temperature_series_included": False,
                    "delta_t_series_included": False,
                    "exact_exclusion_reasons": "image_id_not_found_in_canonical_input",
                    "temperature_exclusion_reasons": "image_id_not_found_in_canonical_input",
                    "delta_t_exclusion_reasons": "image_id_not_found_in_canonical_input",
                    "exclusion_explanation": _reason_message("image_id_not_found_in_canonical_input"),
                    "delta_t_exclusion_explanation": _reason_message("image_id_not_found_in_canonical_input"),
                }
            )
            continue
        selected = captures.loc[captures["image_id"].eq(image_id)]
        temperature_reasons: list[str] = []
        for column in ("capture_exclusion_reasons", "group_gate_reasons"):
            for value in selected[column].astype(str):
                temperature_reasons.extend(filter(None, value.split(";")))
        delta_reasons: list[str] = []
        for column in ("delta_t_exclusion_reasons", "group_gate_reasons"):
            for value in selected[column].astype(str):
                delta_reasons.extend(filter(None, value.split(";")))
        temperature_reasons = list(dict.fromkeys(temperature_reasons))
        delta_reasons = list(dict.fromkeys(delta_reasons))
        rows.append(
            {
                "image_id": image_id,
                "temperature_series_included": bool(selected["temperature_series_eligible"].any()),
                "delta_t_series_included": bool(selected["delta_t_series_eligible"].any()),
                # Retain the historic field as the exact temperature-series
                # reason while making the two analysis families explicit.
                "exact_exclusion_reasons": ";".join(temperature_reasons),
                "temperature_exclusion_reasons": ";".join(temperature_reasons),
                "delta_t_exclusion_reasons": ";".join(delta_reasons),
                "exclusion_explanation": _ordinary_reasons(temperature_reasons),
                "delta_t_exclusion_explanation": _ordinary_reasons(delta_reasons),
            }
        )
    return pd.DataFrame(rows)


COMPATIBILITY_MESSAGES = {
    "measurement_type": "The captures use different measurement types.",
    "temperature_source": "The captures use different temperature sources.",
    "temperature_definition": "The captures use incompatible temperature definitions.",
    "temperature_unit": "The captures use different temperature units.",
    "source_method": "The captures use different temperature-extraction methods.",
    "selection_scope": "The captures use different target-selection scopes.",
    "roi_definition": "The ROI does not have the same definition in every capture.",
    "roi_method": "The ROI was produced by incompatible spatial selection methods.",
    "spatial_processing_method": "Spatial processing is not comparable across the captures.",
    "ambient_source": "Ambient-temperature sources are incompatible, so ΔT values were not pooled.",
    "ambient_definition": "Ambient-temperature definitions are incompatible, so ΔT values were not pooled.",
    "ambient_unit": "Ambient-temperature units are incompatible, so ΔT values were not pooled.",
}

MISSING_COMPATIBILITY_MESSAGES = {
    "measurement_type": "A measurement type is missing, so those captures cannot be pooled.",
    "temperature_source": "A temperature source is missing, so those captures cannot be pooled.",
    "temperature_definition": "A temperature definition is missing, so those captures cannot be pooled.",
    "temperature_unit": "A temperature unit is missing, so those captures cannot be pooled.",
    "source_method": "A temperature-extraction method is missing, so those captures cannot be pooled.",
    "selection_scope": "A target-selection scope is missing, so those captures cannot be pooled.",
    "roi_definition": "An ROI definition is missing, so target comparability cannot be established from metadata alone.",
    "roi_method": "An ROI method is missing, so target comparability cannot be established from metadata alone.",
    "spatial_processing_method": "A spatial-processing method is missing, so those captures cannot be pooled.",
    "ambient_source": "An ambient-temperature source is missing, so ΔT values from that capture are unavailable.",
    "ambient_definition": "An ambient-temperature definition is missing, so ΔT values from that capture are unavailable.",
    "ambient_unit": "An ambient-temperature unit is missing, so ΔT values from that capture are unavailable.",
}


def _compatibility_findings(captures: pd.DataFrame) -> list[dict[str, Any]]:
    """Describe why otherwise eligible captures split into distinct strata."""

    if captures.empty:
        return []
    findings: list[dict[str, Any]] = []
    for family, columns in (
        ("temperature", TEMPERATURE_COMPATIBILITY_COLUMNS),
        ("delta_t", ("ambient_source", "ambient_definition", "ambient_unit")),
    ):
        for column in columns:
            raw = captures[column].fillna("").astype(str).str.strip()
            missing = raw.str.casefold().isin(INVALID_CAPTURE_TIME_SOURCES)
            values = sorted(set(raw.loc[~missing]))
            if missing.any():
                findings.append(
                    {
                        "analysis_family": family,
                        "field": column,
                        "finding_type": "missing",
                        "code": f"{column}_missing",
                        "values": ["[missing or unavailable]", *values],
                        "affected_image_ids": sorted(set(captures.loc[missing, "image_id"].astype(str))),
                        "message": MISSING_COMPATIBILITY_MESSAGES[column],
                    }
                )
            if len(values) > 1:
                findings.append(
                    {
                        "analysis_family": family,
                        "field": column,
                        "finding_type": "incompatible",
                        "code": f"incompatible_{column}_across_captures",
                        "values": values,
                        "affected_image_ids": sorted(set(captures["image_id"].astype(str))),
                        "message": COMPATIBILITY_MESSAGES[column],
                    }
                )
    return findings


def _roi_comparability_summary(
    captures: pd.DataFrame,
    definition: TemporalGroupDefinition,
) -> dict[str, Any]:
    """Record ROI evidence without pretending independently drawn masks coincide."""

    if captures.empty:
        return {
            "status": "no_capture_roi_evidence",
            "roi_comparable_confirmed": definition.roi_comparable_confirmed,
            "target_level_statistics_valid": False,
            "target_level_only": True,
            "boundary_fingerprints": [],
            "capture_evidence": [],
            "boundary_overlap_status": "not_available",
        }
    evidence_columns = [
        "image_id",
        "roi_id",
        "roi_definition",
        "roi_method",
        "roi_mask_sha256",
        "roi_polygon_area_px2",
        "roi_target_pixel_count",
        "roi_target_coverage_fraction",
        "roi_boundary_overlap_fraction",
        "roi_comparability_evidence",
    ]
    evidence = captures[evidence_columns].drop_duplicates(subset=["image_id"], keep="first").copy()
    fingerprints = sorted(
        {
            value.strip()
            for value in evidence["roi_mask_sha256"].fillna("").astype(str)
            if value.strip() and not _metadata_missing(value)
        }
    )
    missing_fingerprints = int(
        evidence["roi_mask_sha256"].fillna("").astype(str).map(_metadata_missing).sum()
    )
    varying_boundaries = len(fingerprints) > 1
    if not definition.roi_comparable_confirmed:
        status = "roi_comparability_not_confirmed"
    elif varying_boundaries:
        status = "user_confirmed_varying_roi_target_level_only"
    elif missing_fingerprints:
        status = "user_confirmed_roi_evidence_incomplete_target_level_only"
    else:
        status = "user_confirmed_consistent_roi_fingerprint"
    overlap = pd.to_numeric(evidence["roi_boundary_overlap_fraction"], errors="coerce")
    overlap_status = (
        "recorded_per_capture"
        if np.isfinite(overlap).any()
        else "not_available_without_validated_cross_capture_registration"
    )
    return {
        "status": status,
        "roi_comparable_confirmed": definition.roi_comparable_confirmed,
        "target_level_statistics_valid": bool(definition.roi_comparable_confirmed),
        "target_level_only": bool(varying_boundaries or missing_fingerprints),
        "varying_boundaries": varying_boundaries,
        "boundary_fingerprints": fingerprints,
        "missing_boundary_fingerprint_count": missing_fingerprints,
        "boundary_overlap_status": overlap_status,
        "capture_evidence": _json_records(evidence),
        "interpretation": (
            "The user confirmed a comparable physical target, but mask boundaries vary; only capture-level ROI "
            "summaries are compared. Pixel coordinates are not treated as corresponding without separate registration."
            if varying_boundaries
            else "ROI evidence is recorded per capture; cross-capture identity still depends on the explicit user confirmation."
        ),
    }


def _delta_t_unavailability(
    captures: pd.DataFrame,
    findings: Sequence[Mapping[str, Any]],
    delta_available: bool,
) -> dict[str, Any]:
    if delta_available:
        return {"available": True, "exact_reasons": [], "explanations": []}
    reasons: list[str] = []
    if not captures.empty:
        for value in captures["delta_t_exclusion_reasons"].astype(str):
            reasons.extend(filter(None, value.split(";")))
        for value in captures["group_gate_reasons"].astype(str):
            reasons.extend(filter(None, value.split(";")))
    reasons.extend(
        str(finding.get("code", ""))
        for finding in findings
        if finding.get("analysis_family") == "delta_t" and finding.get("code")
    )
    reasons = list(dict.fromkeys(reasons))
    if not reasons:
        reasons.append("fewer_than_two_compatible_delta_t_captures")
    return {
        "available": False,
        "exact_reasons": reasons,
        "explanations": [_reason_message(value) for value in reasons],
    }


def _group_report(
    definition: TemporalGroupDefinition,
    manifest: Mapping[str, Any],
    peaks: pd.DataFrame,
    delta_peaks: pd.DataFrame,
    coverage: pd.DataFrame,
    exclusions: pd.DataFrame,
) -> str:
    lines = [
        f"# Temporal group: {definition.temporal_group_id}",
        "",
        f"- Location: {definition.location_name or definition.location_id} (`{definition.location_id}`)",
        f"- Target: {definition.target_name or definition.target_id} (`{definition.target_id}`)",
        f"- Same physical location confirmed: {str(definition.same_location_confirmed).lower()}",
        f"- Submitted captures: {manifest['submitted_capture_count']}",
        f"- Eligible captures: {manifest['eligible_capture_count']}",
        f"- Temporal series available: {str(manifest['temporal_series_available']).lower()}",
        f"- Trend status: `{manifest['trend_status']}`",
        f"- ROI comparability status: `{manifest['roi_comparability']['status']}`",
        f"- Pixelwise temporal analysis available: {str(manifest['pixelwise_temporal_analysis_available']).lower()}",
        f"- Pixelwise availability reason: `{manifest['pixelwise_unavailable_reason'] or 'available'}`",
        "",
    ]
    roi_summary = manifest["roi_comparability"]
    lines.extend(
        [
            "## ROI comparability evidence",
            "",
            f"- Status: `{roi_summary['status']}`",
            f"- Boundary fingerprints recorded: {len(roi_summary['boundary_fingerprints'])}",
            f"- Boundary overlap status: `{roi_summary['boundary_overlap_status']}`",
            f"- Interpretation: {roi_summary['interpretation']}",
            "",
        ]
    )
    primary = peaks.loc[
        peaks.get("available", pd.Series(dtype=bool)).astype(bool)
        & peaks.get("primary_representative", pd.Series(dtype=bool)).astype(bool)
    ] if not peaks.empty else pd.DataFrame()
    if not primary.empty:
        for row in primary.itertuples(index=False):
            lines.extend(
                [
                    f"## Primary observed target range — {row.observation_window_id}",
                    "",
                    f"- Observed maximum ROI mean: {row.observed_max_c:.3f}°C at {row.observed_max_time_local} ({row.observed_max_image_id})",
                    f"- Observed minimum ROI mean: {row.observed_min_c:.3f}°C at {row.observed_min_time_local} ({row.observed_min_image_id})",
                    f"- Observed peak-to-trough difference: {row.observed_peak_to_trough_range_c:.3f}°C",
                    "- This is an observed range inside the sampled window, not automatically a true daily range.",
                    "",
                ]
            )
            window_ranges = peaks.loc[
                peaks.get("available", pd.Series(dtype=bool)).astype(bool)
                & peaks["observation_window_id"].astype(str).eq(str(row.observation_window_id))
                & peaks["stratum_id"].astype(str).eq(str(row.stratum_id))
            ]
            labels = {
                "median": "ROI median range",
                "q95": "ROI q95 range",
                "max": "range of capture-level ROI maxima",
                "absolute_pixel": "absolute observed pixel max–min range",
            }
            for statistic, label in labels.items():
                selected = window_ranges.loc[window_ranges["statistic"].eq(statistic)]
                if not selected.empty:
                    result = selected.iloc[0]
                    value = float(result["observed_peak_to_trough_range_c"])
                    if statistic == "absolute_pixel":
                        lines.extend(
                            [
                                f"- Absolute observed pixel maximum: {float(result['observed_max_c']):.3f}°C at "
                                f"{result['observed_max_time_local']} ({result['observed_max_image_id']}), "
                                f"row={result['observed_max_row']}, col={result['observed_max_col']}",
                                f"- Absolute observed pixel minimum: {float(result['observed_min_c']):.3f}°C at "
                                f"{result['observed_min_time_local']} ({result['observed_min_image_id']}), "
                                f"row={result['observed_min_row']}, col={result['observed_min_col']}",
                                f"- {label}: {value:.3f}°C",
                            ]
                        )
                    else:
                        lines.append(f"- {label}: {value:.3f}°C")
            lines.append("")
    else:
        lines.extend(["## Temporal result unavailable", ""])
        if not manifest["same_location_confirmed"]:
            lines.append(
                "Temporal analysis did not proceed because the user did not confirm that the captures represent "
                "the same physical location or target area."
            )
        elif not definition.roi_comparable_confirmed:
            lines.append(
                "Temporal analysis did not proceed because a comparable accepted ROI for the same target was not confirmed."
            )
        elif manifest["eligible_capture_count"] == 1:
            lines.append(
                "Only one eligible capture is available; no temporal trend or peak-to-trough difference can be estimated."
            )
            eligible_records = [
                value for value in manifest.get("capture_records", [])
                if value.get("temperature_series_eligible")
            ]
            if eligible_records:
                capture = eligible_records[0]
                lines.extend(
                    [
                        "",
                        "### Single-capture descriptive statistics",
                        "",
                        f"- Capture: `{capture['image_id']}`",
                        f"- Capture time (local): {capture.get('capture_time_local') or 'unavailable'}",
                        f"- Capture time (UTC): {capture.get('capture_time_utc') or 'unavailable'}",
                        f"- Capture-time source: {capture.get('capture_time_source') or 'unavailable'}",
                        f"- Capture timezone (source): {capture.get('capture_timezone_source') or 'unavailable'}",
                        f"- Temporal output timezone: {capture.get('capture_timezone_output') or 'unavailable'}",
                    ]
                )
                for field, label in (
                    ("temperature_min_c", "ROI minimum"),
                    ("temperature_max_c", "ROI maximum"),
                    ("temperature_mean_c", "ROI mean"),
                    ("temperature_median_c", "ROI median"),
                    ("temperature_q01_c", "ROI q01"),
                    ("temperature_q05_c", "ROI q05"),
                    ("temperature_q95_c", "ROI q95"),
                    ("temperature_q99_c", "ROI q99"),
                ):
                    value = capture.get(field)
                    rendered = f"{float(value):.3f}°C" if value is not None and np.isfinite(float(value)) else "unavailable"
                    lines.append(f"- {label}: {rendered}")
        elif manifest.get("recorded_identity_conflicts"):
            lines.append(
                "The submitted captures have conflicting spatial evidence and were not treated as the same location."
            )
        else:
            lines.append(
                "No compatible pair of confirmed captures is available. At least two observations of the same "
                "accepted target ROI at different valid times are required."
            )
        findings = manifest.get("compatibility_findings", [])
        if findings:
            lines.extend(["", "Compatibility findings:"])
            for finding in findings:
                lines.append(
                    f"- {finding['message']} Recorded values: {', '.join(str(value) for value in finding['values'])}."
                )
        lines.append("")
    delta_primary = delta_peaks.loc[
        delta_peaks.get("available", pd.Series(dtype=bool)).astype(bool)
        & delta_peaks.get("primary_representative", pd.Series(dtype=bool)).astype(bool)
    ] if not delta_peaks.empty else pd.DataFrame()
    ambient_findings = [
        finding for finding in manifest.get("compatibility_findings", [])
        if finding.get("analysis_family") == "delta_t"
    ]
    if not delta_primary.empty:
        lines.extend(["## Compatible ΔT range", ""])
        for row in delta_primary.itertuples(index=False):
            lines.extend(
                [
                    f"- Observation window: {row.observation_window_id}",
                    f"- Observed maximum ROI-mean ΔT: {row.observed_max_c:.3f}°C at "
                    f"{row.observed_max_time_local} ({row.observed_max_image_id})",
                    f"- Observed minimum ROI-mean ΔT: {row.observed_min_c:.3f}°C at "
                    f"{row.observed_min_time_local} ({row.observed_min_image_id})",
                    f"- Observed peak-to-trough ΔT difference: {row.observed_peak_to_trough_range_c:.3f}°C",
                    f"- Ambient source: {row.ambient_source or 'unavailable'}",
                    f"- Ambient source record: {row.ambient_source_records or 'unavailable'}",
                    f"- Ambient definition: {row.ambient_definition or 'unavailable'}",
                    f"- Ambient unit: {row.ambient_unit or 'unavailable'}",
                    f"- Ambient-data QA status: {row.ambient_data_qa_statuses or 'unavailable'}",
                    f"- Ambient provenance: {row.ambient_provenance or 'unavailable'}",
                    f"- Ambient metadata legacy fallback used: {str(bool(row.ambient_metadata_legacy_fallback)).lower()}",
                    "",
                ]
            )
        if ambient_findings:
            lines.extend(
                [
                    "### ΔT compatibility warnings",
                    "",
                    "The compatible strata above were calculated separately; incompatible ambient references were never pooled.",
                ]
            )
            for finding in ambient_findings:
                lines.append(
                    f"- {finding['message']} Recorded values: "
                    f"{', '.join(str(value) for value in finding['values'])}."
                )
            lines.append("")
    else:
        lines.extend(["## ΔT temporal range unavailable", ""])
        if ambient_findings:
            for finding in ambient_findings:
                lines.append(
                    f"- {finding['message']} Recorded values: "
                    f"{', '.join(str(value) for value in finding['values'])}."
                )
        exact_delta_reasons = manifest.get("delta_t_unavailability", {}).get("exact_reasons", [])
        explanations = manifest.get("delta_t_unavailability", {}).get("explanations", [])
        if exact_delta_reasons:
            lines.append(f"- Exact reason codes: `{';'.join(exact_delta_reasons)}`")
        for explanation in explanations:
            lines.append(f"- {explanation}")
        lines.append("")
    if not coverage.empty:
        lines.extend(["## Sampling coverage", ""])
        for row in coverage.itertuples(index=False):
            lines.append(
                f"- {row.observation_window_id}: {row.observation_start_local or 'unavailable'} to "
                f"{row.observation_end_local or 'unavailable'}; captures={row.eligible_capture_count}; "
                f"status={row.sampling_coverage_status}. {row.coverage_statement}"
            )
            interval_hours = [float(value) / 3600.0 for value in json.loads(row.interval_seconds_json)]
            lines.append(
                "  - Intervals between eligible captures (hours): "
                + (", ".join(f"{value:.3f}" for value in interval_hours) if interval_hours else "not available")
            )
            lines.append(
                f"  - Daytime represented: {str(bool(row.daytime_present)).lower()}; "
                f"nighttime represented: {str(bool(row.nighttime_present)).lower()}."
            )
            if interval_hours:
                lines.append(
                    f"  - Largest unsampled interval between captures: {max(interval_hours):.3f} hours."
                )
        lines.append("")
    excluded = exclusions.loc[
        exclusions["exact_exclusion_reasons"].astype(str).ne("")
        | exclusions["delta_t_exclusion_reasons"].astype(str).ne("")
    ]
    if not excluded.empty:
        lines.extend(["## Exclusions and warnings", ""])
        for row in excluded.itertuples(index=False):
            if row.exact_exclusion_reasons:
                lines.append(f"- `{row.image_id}` temperature exact codes: `{row.exact_exclusion_reasons}`")
                if row.exclusion_explanation:
                    lines.append(f"  - {row.exclusion_explanation}")
            else:
                lines.append(f"- `{row.image_id}` temperature series: included")
            if row.delta_t_exclusion_reasons and row.delta_t_exclusion_reasons != row.exact_exclusion_reasons:
                lines.append(f"  - ΔT exact codes: `{row.delta_t_exclusion_reasons}`")
                lines.append(f"  - {row.delta_t_exclusion_explanation}")
        lines.append("")
    return "\n".join(lines) + "\n"


def _process_group(
    raw: pd.DataFrame,
    definition: TemporalGroupDefinition,
    *,
    output_root: Path,
    default_timezone: str,
) -> tuple[dict[str, Any], list[Path]]:
    group_root = output_root / definition.temporal_group_id
    tables = group_root / "tables"
    qa = group_root / "qa"
    figures = group_root / "figures"
    submitted = _submitted_table(definition, set(raw["image_id"].astype(str)))
    submitted_path = _write_csv(submitted, tables / "submitted_captures.csv")
    selected_raw = raw.loc[raw["image_id"].isin(definition.image_ids)].copy()
    conflicts = _identity_conflicts(selected_raw, definition) if not selected_raw.empty else []
    captures = _capture_summaries(selected_raw, default_timezone=default_timezone)
    captures = _apply_group_gates(captures, definition, conflicts)
    compatibility_findings = _compatibility_findings(captures)
    roi_comparability = _roi_comparability_summary(captures, definition)
    windowed = _windowed_captures(captures, definition, default_timezone)
    if definition.observation_windows and not captures.empty:
        window_members = set(windowed["image_id"].astype(str))
        outside = ~captures["image_id"].astype(str).isin(window_members)
        captures.loc[outside, ["temperature_series_eligible", "delta_t_series_eligible"]] = False
        captures.loc[outside, "group_gate_reasons"] = captures.loc[outside, "group_gate_reasons"].map(
            lambda value: ";".join(filter(None, [str(value), "outside_user_defined_observation_windows"]))
        )
        windowed = _windowed_captures(captures, definition, default_timezone)
    if not captures.empty:
        captures["capture_exclusion_explanation"] = captures["capture_exclusion_reasons"].map(
            lambda value: _ordinary_reasons(filter(None, str(value).split(";")))
        )
        captures["delta_t_exclusion_explanation"] = captures["delta_t_exclusion_reasons"].map(
            lambda value: _ordinary_reasons(filter(None, str(value).split(";")))
        )
        captures["group_gate_explanation"] = captures["group_gate_reasons"].map(
            lambda value: _ordinary_reasons(filter(None, str(value).split(";")))
        )
    peaks, delta_peaks = _range_tables(windowed)
    coverage = _sampling_coverage(windowed, definition)
    exclusions = _exclusion_table(definition, captures)
    capture_path = _write_csv(captures, tables / "per_capture_statistics.csv")
    compatibility_path = _write_csv(
        captures[
            [
                "image_id",
                "capture_time_local",
                "capture_time_utc",
                "capture_time_source",
                "capture_timezone_source",
                "capture_timezone_output",
                "capture_time_valid",
                "temperature_stratum_id",
                "delta_t_stratum_id",
                "temperature_series_eligible",
                "delta_t_series_eligible",
                "capture_exclusion_reasons",
                "capture_exclusion_explanation",
                "delta_t_exclusion_reasons",
                "delta_t_exclusion_explanation",
                "group_gate_reasons",
                "group_gate_explanation",
                "roi_mask_sha256",
                "roi_polygon_area_px2",
                "roi_target_pixel_count",
                "roi_target_coverage_fraction",
                "roi_boundary_overlap_fraction",
                "roi_comparability_evidence",
                "ambient_data_qa_status",
                "ambient_provenance",
                "ambient_source_record",
                "ambient_metadata_legacy_fallback",
            ]
        ] if not captures.empty else pd.DataFrame(
            columns=[
                "image_id", "capture_time_local", "capture_time_utc", "capture_time_source",
                "capture_timezone_source", "capture_timezone_output",
                "capture_time_valid",
                "temperature_stratum_id", "delta_t_stratum_id", "temperature_series_eligible",
                "delta_t_series_eligible", "capture_exclusion_reasons", "capture_exclusion_explanation",
                "delta_t_exclusion_reasons", "delta_t_exclusion_explanation", "group_gate_reasons",
                "group_gate_explanation", "roi_mask_sha256", "roi_polygon_area_px2",
                "roi_target_pixel_count", "roi_target_coverage_fraction",
                "roi_boundary_overlap_fraction", "roi_comparability_evidence", "ambient_data_qa_status",
                "ambient_provenance", "ambient_source_record", "ambient_metadata_legacy_fallback",
            ]
        ),
        tables / "capture_compatibility.csv",
    )
    peak_path = _write_csv(
        peaks if not peaks.empty else pd.DataFrame(columns=["metric_family", "statistic", "available"]),
        tables / "peak_to_trough_statistics.csv",
    )
    delta_peak_path = _write_csv(
        delta_peaks if not delta_peaks.empty else pd.DataFrame(columns=["metric_family", "statistic", "available"]),
        tables / "delta_t_peak_to_trough_statistics.csv",
    )
    coverage_path = _write_csv(
        coverage if not coverage.empty else pd.DataFrame(columns=["sampling_coverage_status"]),
        tables / "sampling_coverage.csv",
    )
    exclusion_path = _write_csv(exclusions, qa / "exclusions.csv")
    spatial_identity_path = qa / "spatial_identity_confirmation.json"
    _atomic_text(
        spatial_identity_path,
        json.dumps(
            {
                **definition.to_dict(),
                "recorded_identity_conflicts": conflicts,
                "override_applied": bool(conflicts and definition.spatial_override_confirmed),
                "roi_comparability": roi_comparability,
            },
            indent=2,
            ensure_ascii=False,
        ),
    )
    artifact_paths: list[Path] = [
        submitted_path,
        capture_path,
        compatibility_path,
        peak_path,
        delta_peak_path,
        coverage_path,
        exclusion_path,
        spatial_identity_path,
    ]
    temperature_series = bool(not peaks.empty and peaks.get("available", pd.Series(dtype=bool)).astype(bool).any())
    peak_available = bool(
        not peaks.empty
        and (
            peaks.get("available", pd.Series(dtype=bool)).astype(bool)
            & peaks.get("primary_representative", pd.Series(dtype=bool)).astype(bool)
        ).any()
    )
    delta_available = bool(not delta_peaks.empty and delta_peaks.get("available", pd.Series(dtype=bool)).astype(bool).any())
    delta_t_availability = _delta_t_unavailability(captures, compatibility_findings, delta_available)
    if temperature_series:
        artifact_paths.extend(_plot_temperature_series(windowed, figures, family="temperature"))
        artifact_paths.extend(_plot_range_summary(peaks, figures))
        artifact_paths.extend(_plot_sampling_timeline(windowed, figures))
    if delta_available:
        artifact_paths.extend(_plot_temperature_series(windowed, figures, family="delta_t"))
    pixelwise_available, pixelwise_reason, pixel_paths = _pixelwise_analysis(
        selected_raw, windowed, definition, figures
    )
    artifact_paths.extend(pixel_paths)
    eligible_capture_count = int(
        windowed.loc[windowed["temperature_series_eligible"].astype(bool), "image_id"].nunique()
    ) if not windowed.empty else 0
    if not definition.same_location_confirmed:
        trend_status = "same_location_not_confirmed"
    elif conflicts and not definition.spatial_override_confirmed:
        trend_status = "spatial_identity_conflict"
    elif not definition.roi_comparable_confirmed:
        trend_status = "roi_comparability_not_confirmed"
    elif temperature_series:
        trend_status = "multi_capture_observed_series"
    elif eligible_capture_count == 1:
        trend_status = "single_capture_descriptive_no_trend"
    else:
        trend_status = "no_compatible_temporal_series"
    coverage_statuses = sorted(set(coverage.get("sampling_coverage_status", pd.Series(dtype=str)).astype(str)))
    group_manifest: dict[str, Any] = {
        "status": "complete",
        "analysis_completion_status": "complete",
        "temporal_requested": True,
        "same_location_confirmed": definition.same_location_confirmed,
        "temporal_group_id": definition.temporal_group_id,
        "location_id": definition.location_id,
        "target_id": definition.target_id,
        "submitted_capture_count": len(definition.image_ids),
        "eligible_capture_count": eligible_capture_count,
        "temporal_series_available": temperature_series,
        "temporal_result_availability": "available" if temperature_series else "unavailable",
        "peak_to_trough_available": peak_available,
        "delta_t_peak_to_trough_available": delta_available,
        "delta_t_result_availability": "available" if delta_available else "unavailable",
        "delta_t_unavailability": delta_t_availability,
        "pixelwise_temporal_analysis_available": pixelwise_available,
        "pixelwise_unavailable_reason": pixelwise_reason,
        "trend_status": trend_status,
        "sampling_coverage_status": ";".join(coverage_statuses) if coverage_statuses else "not_available",
        "spatial_identity_confirmation": definition.to_dict(),
        "recorded_identity_conflicts": conflicts,
        "submitted_capture_list": definition.image_ids,
        "included_capture_list": sorted(
            set(captures.loc[captures["temperature_series_eligible"].astype(bool), "image_id"].astype(str))
        ) if not captures.empty else [],
        "excluded_capture_list": exclusions.loc[
            ~exclusions["temperature_series_included"].astype(bool), "image_id"
        ].astype(str).tolist(),
        "exclusion_reasons": {
            str(row.image_id): str(row.exact_exclusion_reasons)
            for row in exclusions.itertuples(index=False)
            if str(row.exact_exclusion_reasons)
        },
        "exclusion_explanations": {
            str(row.image_id): str(row.exclusion_explanation)
            for row in exclusions.itertuples(index=False)
            if str(row.exclusion_explanation)
        },
        "delta_t_exclusion_reasons": {
            str(row.image_id): str(row.delta_t_exclusion_reasons)
            for row in exclusions.itertuples(index=False)
            if str(row.delta_t_exclusion_reasons)
        },
        "delta_t_exclusion_explanations": {
            str(row.image_id): str(row.delta_t_exclusion_explanation)
            for row in exclusions.itertuples(index=False)
            if str(row.delta_t_exclusion_explanation)
        },
        "compatibility_policy": {
            "temperature": TEMPERATURE_COMPATIBILITY_COLUMNS,
            "delta_t": DELTA_T_COMPATIBILITY_COLUMNS,
            "allowed_qa_statuses": definition.allowed_qa_statuses,
            "interpolation": "disabled",
        },
        "compatibility_findings": compatibility_findings,
        "roi_comparability": roi_comparability,
        "capture_records": _json_records(
            captures[
                [
                    "image_id",
                    "capture_time_local",
                    "capture_time_utc",
                    "capture_time_source",
                    "capture_timezone_source",
                    "capture_timezone_output",
                    "capture_time_valid",
                    "capture_time_error",
                    "timezone_assumption",
                    "gps_latitude",
                    "gps_longitude",
                    "roi_id",
                    "roi_definition",
                    "roi_method",
                    "spatial_processing_method",
                    "spatial_registration_id",
                    "target_measurement_count",
                    "target_coverage_fraction",
                    "roi_mask_sha256",
                    "roi_polygon_area_px2",
                    "roi_target_pixel_count",
                    "roi_target_coverage_fraction",
                    "roi_boundary_overlap_fraction",
                    "roi_comparability_evidence",
                    "temperature_source",
                    "temperature_definition",
                    "temperature_unit",
                    "temperature_min_c",
                    "temperature_max_c",
                    "temperature_mean_c",
                    "temperature_median_c",
                    "temperature_q01_c",
                    "temperature_q05_c",
                    "temperature_q95_c",
                    "temperature_q99_c",
                    "ambient_source",
                    "ambient_definition",
                    "ambient_unit",
                    "ambient_data_qa_status",
                    "ambient_provenance",
                    "ambient_source_record",
                    "ambient_metadata_legacy_fallback",
                    "ambient_temperature_c",
                    "qa_status",
                    "temperature_series_eligible",
                    "delta_t_series_eligible",
                    "capture_exclusion_reasons",
                    "capture_exclusion_explanation",
                    "delta_t_exclusion_reasons",
                    "delta_t_exclusion_explanation",
                    "group_gate_reasons",
                    "group_gate_explanation",
                ]
            ]
        ) if not captures.empty else [],
        "sampling_coverage": _json_records(coverage),
        "peak_to_trough_statistics": _json_records(peaks.loc[peaks.get("available", pd.Series(dtype=bool)).astype(bool)])
        if not peaks.empty else [],
        "delta_t_peak_to_trough_statistics": _json_records(
            delta_peaks.loc[delta_peaks.get("available", pd.Series(dtype=bool)).astype(bool)]
        ) if not delta_peaks.empty else [],
        "figure_files": [],
        "artifact_files": [],
    }
    report_path = group_root / "temporal_summary.md"
    _atomic_text(report_path, _group_report(definition, group_manifest, peaks, delta_peaks, coverage, exclusions))
    qa_path = qa / "temporal_group_qa.md"
    _atomic_text(
        qa_path,
        "\n".join(
            [
                f"# Temporal QA — {definition.temporal_group_id}",
                "",
                f"- Stage status: complete",
                f"- Temporal series available: {str(temperature_series).lower()}",
                f"- Peak-to-trough available: {str(peak_available).lower()}",
                f"- ΔT peak-to-trough available: {str(delta_available).lower()}",
                f"- ΔT exact unavailability reasons: {json.dumps(delta_t_availability['exact_reasons'], ensure_ascii=False)}",
                f"- Pixelwise analysis available: {str(pixelwise_available).lower()}",
                f"- Pixelwise reason: {pixelwise_reason or 'available'}",
                f"- ROI comparability status: {roi_comparability['status']}",
                f"- Identity conflicts: {json.dumps(conflicts, ensure_ascii=False)}",
                "- A full-day claim additionally requires at least six captures, day and night observations, at least "
                "23 hours of span, and no gap longer than four hours.",
                "- Within-capture quantiles describe spatial variation, not temporal confidence intervals.",
            ]
        )
        + "\n",
    )
    artifact_paths.extend([report_path, qa_path])
    group_manifest_path = group_root / "temporal_group_manifest.json"
    group_manifest["figure_files"] = [
        path.resolve().as_posix() for path in artifact_paths if path.suffix.casefold() in {".png", ".pdf"}
    ]
    group_manifest["artifact_files"] = [path.resolve().as_posix() for path in artifact_paths]
    _atomic_text(group_manifest_path, json.dumps(group_manifest, indent=2, ensure_ascii=False))
    artifact_paths.append(group_manifest_path)
    return group_manifest, artifact_paths


def validate_temporal_outputs(output_root: Path, *, canonical_hash: str | None = None) -> dict[str, Any]:
    validation_path = output_root / "temporal_output_validation.json"
    if not validation_path.is_file():
        # Read compatibility with the superseded layout.
        validation_path = output_root / "qa" / "temporal_output_validation.json"
    if not validation_path.is_file():
        raise ValueError("Temporal output validation record is missing.")
    payload = json.loads(validation_path.read_text(encoding="utf-8"))
    if canonical_hash and payload.get("canonical_sha256") != canonical_hash:
        raise ValueError("Temporal outputs do not match the current canonical input.")
    missing = [
        value
        for value in payload.get("expected_files", [])
        if not Path(str(value)).is_file() or Path(str(value)).stat().st_size == 0
    ]
    if missing:
        raise ValueError(f"Temporal output is incomplete: {missing[:10]}")
    legacy_files = [
        path
        for name in ("figures", "qa", "summaries", "tables")
        for path in (output_root / name).rglob("*")
        if path.is_file()
    ]
    if legacy_files:
        raise ValueError(
            "Temporal output contains superseded top-level artifacts: "
            f"{[path.as_posix() for path in legacy_files[:10]]}"
        )
    return payload


def _remove_prior_generated_outputs(output_root: Path, validation_path: Path) -> None:
    """Remove only artifacts listed by this stage's prior validation record."""
    root = output_root.resolve()
    validation_paths = [validation_path, output_root / "qa" / "temporal_output_validation.json"]
    for prior_validation in validation_paths:
        if not prior_validation.is_file():
            continue
        try:
            payload = json.loads(prior_validation.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        for value in payload.get("expected_files", []):
            path = Path(str(value))
            path = path if path.is_absolute() else output_root / path
            try:
                resolved = path.resolve()
            except OSError:
                continue
            if not resolved.is_relative_to(root) or not resolved.is_file():
                continue
            resolved.unlink()
    # The pre-v0.3.2 temporal stage wrote global comparison files into these
    # top-level folders.  The current layout only writes inside explicit group
    # directories, so these names are generated legacy output, never user data.
    for name in ("figures", "qa", "summaries", "tables"):
        legacy = output_root / name
        if legacy.is_dir() and legacy.resolve().is_relative_to(root):
            shutil.rmtree(legacy)
    for path in sorted(output_root.rglob("*"), key=lambda value: len(value.parts), reverse=True):
        if path.is_dir():
            try:
                path.rmdir()
            except OSError:
                pass


def _result_from_outputs(output_root: Path, *, status: str) -> TemporalRunResult:
    run_manifest_path = output_root / "temporal_run_manifest.json"
    payload = json.loads(run_manifest_path.read_text(encoding="utf-8"))
    group_manifests = [Path(value) for value in payload.get("group_manifest_files", [])]
    first_root = group_manifests[0].parent if group_manifests else None
    return TemporalRunResult(
        status=status,
        output_root=output_root,
        run_manifest=run_manifest_path,
        run_summary=output_root / "temporal_run_summary.md",
        validation=output_root / "temporal_output_validation.json",
        temporal_requested=bool(payload.get("temporal_requested", False)),
        temporal_series_available=bool(payload.get("temporal_series_available", False)),
        group_manifests=group_manifests,
        capture_summary=(first_root / "tables" / "per_capture_statistics.csv") if first_root else None,
        stratum_summary=(first_root / "tables" / "peak_to_trough_statistics.csv") if first_root else None,
        inclusion_exclusion=(first_root / "qa" / "exclusions.csv") if first_root else None,
        diagnostics=(first_root / "qa" / "temporal_group_qa.md") if first_root else None,
        qa_report=(first_root / "qa" / "temporal_group_qa.md") if first_root else None,
        report=(first_root / "temporal_summary.md") if first_root else output_root / "temporal_run_summary.md",
    )


def run_temporal_analysis(
    canonical_parquet: Path,
    *,
    output_root: Path,
    default_timezone: str,
    plan: TemporalAnalysisPlan | Mapping[str, Any] | Path | str | None = None,
    temporal_requested: bool | None = None,
    temporal_groups: Iterable[TemporalGroupDefinition | Mapping[str, Any]] | None = None,
    resume: bool = True,
    dry_run: bool = False,
) -> TemporalRunResult | dict[str, Any]:
    """Run opt-in temporal analysis without ever inferring spatial identity."""

    ZoneInfo(default_timezone)
    parsed_plan = parse_temporal_plan(
        plan,
        temporal_requested=temporal_requested,
        temporal_groups=temporal_groups,
    )
    canonical_parquet = canonical_parquet.resolve()
    if not canonical_parquet.is_file():
        raise FileNotFoundError(canonical_parquet)
    canonical_hash = sha256_file(canonical_parquet)
    config_hash = _config_hash(default_timezone, parsed_plan)
    state_path = output_root / "temporal_stage_state.json"
    validation_path = output_root / "temporal_output_validation.json"
    if dry_run:
        return {
            "status": "planned_dry_run",
            "canonical_parquet": canonical_parquet.as_posix(),
            "canonical_sha256": canonical_hash,
            "default_timezone": default_timezone,
            "temporal_requested": parsed_plan.temporal_requested,
            "temporal_group_count": len(parsed_plan.groups),
            "plan": parsed_plan.to_dict(),
        }
    if resume and state_path.is_file() and validation_path.is_file():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state.get("canonical_sha256") == canonical_hash and state.get("config_sha256") == config_hash:
            try:
                validate_temporal_outputs(output_root, canonical_hash=canonical_hash)
            except (OSError, ValueError, json.JSONDecodeError):
                pass
            else:
                return _result_from_outputs(output_root, status="cache_hit")

    _remove_prior_generated_outputs(output_root, validation_path)
    output_root.mkdir(parents=True, exist_ok=True)
    artifact_paths: list[Path] = []
    group_manifests: list[dict[str, Any]] = []
    group_manifest_paths: list[Path] = []
    if parsed_plan.temporal_requested:
        raw = _ensure_columns(pd.read_parquet(canonical_parquet))
        for definition in parsed_plan.groups:
            manifest, paths = _process_group(
                raw,
                definition,
                output_root=output_root,
                default_timezone=default_timezone,
            )
            group_manifests.append(manifest)
            artifact_paths.extend(paths)
            group_manifest_paths.append(output_root / definition.temporal_group_id / "temporal_group_manifest.json")

    series_available = any(bool(value.get("temporal_series_available")) for value in group_manifests)
    peak_available = any(bool(value.get("peak_to_trough_available")) for value in group_manifests)
    run_manifest = {
        "status": "complete",
        "analysis_completion_status": "complete",
        "temporal_requested": parsed_plan.temporal_requested,
        "temporal_group_count": len(parsed_plan.groups),
        "temporal_series_available": series_available,
        "temporal_result_availability": (
            "not_requested"
            if not parsed_plan.temporal_requested
            else "available"
            if series_available
            else "unavailable"
        ),
        "peak_to_trough_available": peak_available,
        "pixelwise_temporal_analysis_available": any(
            bool(value.get("pixelwise_temporal_analysis_available")) for value in group_manifests
        ),
        "default_timezone": default_timezone,
        "canonical_parquet": canonical_parquet.as_posix(),
        "canonical_sha256": canonical_hash,
        "config_sha256": config_hash,
        "plan": parsed_plan.to_dict(),
        "groups": group_manifests,
        "group_manifest_files": [path.resolve().as_posix() for path in group_manifest_paths],
    }
    run_manifest_path = output_root / "temporal_run_manifest.json"
    _atomic_text(run_manifest_path, json.dumps(run_manifest, indent=2, ensure_ascii=False))
    if not parsed_plan.temporal_requested:
        summary_lines = [
            "# Temporal run summary",
            "",
            "Temporal analysis was not requested.",
            "",
            "All applicable non-temporal single-image, spatial, spectrum, and descriptive outputs remain independent of this clean skip.",
        ]
    elif not parsed_plan.groups:
        summary_lines = [
            "# Temporal run summary",
            "",
            "Temporal analysis was requested, but no explicit same-location temporal group was submitted.",
            "",
            "No temporal series or figures were created.",
        ]
    else:
        summary_lines = [
            "# Temporal run summary",
            "",
            f"- Temporal groups submitted: {len(group_manifests)}",
            f"- Groups with an observed temporal series: {sum(bool(value.get('temporal_series_available')) for value in group_manifests)}",
            f"- Groups with peak-to-trough results: {sum(bool(value.get('peak_to_trough_available')) for value in group_manifests)}",
            "",
        ]
        for value in group_manifests:
            summary_lines.append(
                f"- `{value['temporal_group_id']}`: {value['trend_status']}; "
                f"eligible captures={value['eligible_capture_count']}; "
                f"series={str(value['temporal_series_available']).lower()}"
            )
            primary_results = [
                result
                for result in value.get("peak_to_trough_statistics", [])
                if result.get("primary_representative") and result.get("available")
            ]
            for result in primary_results:
                summary_lines.extend(
                    [
                        f"  - Window `{result['observation_window_id']}` observed maximum ROI mean: "
                        f"{float(result['observed_max_c']):.3f}°C at {result['observed_max_time_local']} "
                        f"({result['observed_max_image_id']})",
                        f"  - Observed minimum ROI mean: {float(result['observed_min_c']):.3f}°C at "
                        f"{result['observed_min_time_local']} ({result['observed_min_image_id']})",
                        f"  - Observed peak-to-trough difference: "
                        f"{float(result['observed_peak_to_trough_range_c']):.3f}°C",
                    ]
                )
            if value["eligible_capture_count"] == 1:
                summary_lines.append(
                    "  - Only one eligible capture is available; no temporal trend or peak-to-trough difference can be estimated."
                )
    run_summary_path = output_root / "temporal_run_summary.md"
    _atomic_text(run_summary_path, "\n".join(summary_lines) + "\n")
    artifact_paths.extend([run_manifest_path, run_summary_path])
    validation = {
        "status": "complete",
        "analysis_completion_status": "complete",
        "temporal_requested": parsed_plan.temporal_requested,
        "temporal_series_available": series_available,
        "peak_to_trough_available": peak_available,
        "canonical_sha256": canonical_hash,
        "config_sha256": config_hash,
        "expected_files": [path.resolve().as_posix() for path in artifact_paths],
        "figure_files": [
            path.resolve().as_posix() for path in artifact_paths if path.suffix.casefold() in {".png", ".pdf"}
        ],
    }
    _atomic_text(validation_path, json.dumps(validation, indent=2, ensure_ascii=False))
    _atomic_text(
        state_path,
        json.dumps(
            {
                "status": "complete",
                "canonical_sha256": canonical_hash,
                "config_sha256": config_hash,
                "temporal_requested": parsed_plan.temporal_requested,
                "temporal_series_available": series_available,
            },
            indent=2,
        ),
    )
    validate_temporal_outputs(output_root, canonical_hash=canonical_hash)
    return _result_from_outputs(output_root, status="complete")
