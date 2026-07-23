"""Ordinary-user prompts for explicit same-location temporal groups."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Callable, Iterable

from .canonical_result import load_manifest
from .capture_time import select_capture_time_bundle
from .temporal_analysis import (
    DEFAULT_GPS_CONFLICT_THRESHOLD_M,
    TemporalAnalysisPlan,
    TemporalGroupDefinition,
)


InputFunction = Callable[[str], str]
OutputFunction = Callable[[str], Any]


def _yes_no(prompt: str, *, input_func: InputFunction, default: bool = False) -> bool:
    suffix = " [Y/n]" if default else " [y/N]"
    while True:
        try:
            value = input_func(prompt + suffix + ": ").strip().casefold()
        except EOFError:
            return default
        if not value:
            return default
        if value in {"y", "yes"}:
            return True
        if value in {"n", "no"}:
            return False


def _ask(prompt: str, *, input_func: InputFunction, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        return input_func(prompt + suffix + ": ").strip() or default
    except EOFError:
        return default


def _numbers(value: str, maximum: int) -> list[int]:
    result: list[int] = []
    for item in value.replace(" ", "").split(","):
        if not item:
            continue
        if "-" in item:
            start_text, end_text = item.split("-", 1)
            start, end = int(start_text), int(end_text)
            result.extend(range(min(start, end), max(start, end) + 1))
        else:
            result.append(int(item))
    ordered = list(dict.fromkeys(result))
    if any(value < 1 or value > maximum for value in ordered):
        raise ValueError(f"Selection must use numbers 1-{maximum}.")
    return ordered


def _distance_m(first: tuple[float, float], second: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, first)
    lat2, lon2 = map(math.radians, second)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6_371_008.8 * math.asin(min(1.0, math.sqrt(value)))


def _capture_cards(manifest_paths: Iterable[Path]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for path in manifest_paths:
        manifest = load_manifest(Path(path))
        part_a = manifest.part_a or {}
        manifest_capture = {
            "capture_datetime": manifest.capture_datetime,
            "capture_time_local": manifest.capture_time_local,
            "capture_time_utc": manifest.capture_time_utc,
            "capture_timezone": manifest.capture_timezone,
            "capture_time_source": manifest.capture_time_source,
            "timezone_assumption": manifest.timezone_assumption,
            "capture_time_valid": manifest.capture_time_valid,
        }
        capture = select_capture_time_bundle(
            (manifest_capture, ""),
            (manifest.temperature_metadata or {}, ""),
            (part_a, "part_a_capture_time_fallback"),
            missing_timezone=str(
                manifest.capture_timezone
                or (manifest.temperature_metadata or {}).get("capture_timezone")
                or part_a.get("capture_timezone")
                or ""
            ),
        )
        cards.append(
            {
                "manifest": manifest,
                "image_id": manifest.image_id,
                "visible_path": manifest.visible_path,
                "thermal_path": manifest.thermal_path,
                "capture_datetime": capture["capture_time_local"] or capture["capture_datetime"],
                "capture_time_local": capture["capture_time_local"],
                "capture_time_utc": capture["capture_time_utc"],
                "capture_timezone": capture["capture_timezone"],
                "capture_time_source": capture["capture_time_source"],
                "capture_time_valid": capture["capture_time_valid"],
                "timezone_assumption": capture["timezone_assumption"],
                "gps_latitude": part_a.get("gps_latitude"),
                "gps_longitude": part_a.get("gps_longitude"),
                "target_id": manifest.target_id or "",
                "location_id": manifest.location_id or "",
                "target_name": manifest.target_name or "",
                "spatial_registration_id": str((getattr(manifest, "part_b", {}) or {}).get("spatial_registration_id", "")),
                "roi_boundary_overlap_fraction": (getattr(manifest, "annotation_review", {}) or {}).get(
                    "roi_boundary_overlap_fraction", ""
                ),
                "dataset_id": manifest.dataset_id,
                "measurement_source": manifest.temperature_source,
                "measurement_type": manifest.measurement_type.value,
            }
        )
    return cards


def _spatial_conflicts(
    cards: list[dict[str, Any]],
    location_id: str,
    target_id: str,
    target_name: str = "",
) -> list[str]:
    conflicts: list[str] = []
    recorded_locations = {str(card["location_id"]).strip() for card in cards if str(card["location_id"]).strip()}
    recorded_targets = {str(card["target_id"]).strip() for card in cards if str(card["target_id"]).strip()}
    if len(recorded_locations) > 1:
        conflicts.append("Recorded location IDs differ: " + ", ".join(sorted(recorded_locations)))
    elif recorded_locations and location_id not in recorded_locations:
        conflicts.append(f"Confirmed location_id={location_id} differs from recorded {next(iter(recorded_locations))}.")
    if len(recorded_targets) > 1:
        conflicts.append("Recorded target IDs differ: " + ", ".join(sorted(recorded_targets)))
    elif recorded_targets and target_id not in recorded_targets:
        conflicts.append(f"Confirmed target_id={target_id} differs from recorded {next(iter(recorded_targets))}.")
    recorded_names = {
        str(card.get("target_name", "")).strip()
        for card in cards
        if str(card.get("target_name", "")).strip()
    }
    if len({value.casefold() for value in recorded_names}) > 1:
        conflicts.append("Recorded target names differ: " + ", ".join(sorted(recorded_names)))
    elif recorded_names and target_name and next(iter(recorded_names)).casefold() != target_name.strip().casefold():
        conflicts.append(
            f"Confirmed target name={target_name} differs from recorded {next(iter(recorded_names))}."
        )
    registration_ids = {
        str(card.get("spatial_registration_id", "")).strip()
        for card in cards
        if str(card.get("spatial_registration_id", "")).strip()
    }
    if len(registration_ids) > 1:
        conflicts.append("Recorded spatial registration IDs differ: " + ", ".join(sorted(registration_ids)))
    for card in cards:
        try:
            overlap = float(card.get("roi_boundary_overlap_fraction", ""))
        except (TypeError, ValueError):
            continue
        if math.isfinite(overlap) and overlap <= 0.0:
            conflicts.append(
                f"Recorded accepted-ROI overlap is zero for image {card.get('image_id', 'unknown')}."
            )
    coordinates: list[tuple[float, float]] = []
    for card in cards:
        try:
            latitude = float(card["gps_latitude"])
            longitude = float(card["gps_longitude"])
        except (TypeError, ValueError):
            continue
        if math.isfinite(latitude) and math.isfinite(longitude):
            coordinates.append((latitude, longitude))
    if len(coordinates) >= 2:
        maximum = max(
            _distance_m(coordinates[first], coordinates[second])
            for first in range(len(coordinates))
            for second in range(first + 1, len(coordinates))
        )
        if maximum > DEFAULT_GPS_CONFLICT_THRESHOLD_M:
            conflicts.append(
                f"GPS centres are as much as {maximum:.1f} m apart "
                f"(>{DEFAULT_GPS_CONFLICT_THRESHOLD_M:.0f} m review threshold)."
            )
    return conflicts


def collect_temporal_plan(
    manifest_paths: Iterable[Path],
    *,
    requested: bool | None = None,
    input_func: InputFunction = input,
    output_func: OutputFunction = print,
) -> TemporalAnalysisPlan:
    """Collect an explicit plan; the ordinary user never authors JSON/config."""
    if requested is None:
        requested = _yes_no(
            "Do you want to perform temporal analysis for repeated observations of the same location?",
            input_func=input_func,
            default=False,
        )
    if not requested:
        output_func("Temporal analysis was not requested. Normal single-image and spatial analysis will continue.")
        return TemporalAnalysisPlan(temporal_requested=False)

    cards = _capture_cards(manifest_paths)
    output_func("Temporal analysis was requested.")
    output_func("Which images belong to the same physical location or target area?")
    for index, card in enumerate(cards, start=1):
        gps = (
            f"{card['gps_latitude']}, {card['gps_longitude']}"
            if card["gps_latitude"] not in (None, "") and card["gps_longitude"] not in (None, "")
            else "unavailable"
        )
        output_func(
            f"[{index}] image_id={card['image_id']}\n"
            f"    visible={card['visible_path']}\n"
            f"    thermal={card['thermal_path']}\n"
            f"    capture={card['capture_datetime'] or 'missing'} (source={card['capture_time_source']})\n"
            f"    GPS={gps}; target_id={card['target_id'] or 'unassigned'}; "
            f"location_id={card['location_id'] or 'unassigned'}\n"
            f"    target={card['target_name'] or 'unassigned'}; dataset={card['dataset_id']}; "
            f"measurement={card['measurement_source'] or 'unavailable'} / {card['measurement_type']}"
        )

    definitions: list[TemporalGroupDefinition] = []
    assigned: set[int] = set()
    while cards:
        value = _ask(
            "Select captures for one physical location (for example 1,3-4; press Enter when finished)",
            input_func=input_func,
        )
        if not value:
            break
        try:
            selected_numbers = _numbers(value, len(cards))
        except (TypeError, ValueError) as exc:
            output_func(f"Invalid selection: {exc}")
            continue
        overlap = assigned.intersection(selected_numbers)
        if overlap:
            output_func(f"These selections already belong to another temporal group: {sorted(overlap)}")
            continue
        selected = [cards[index - 1] for index in selected_numbers]
        location_name = _ask("Human-readable location or target name", input_func=input_func)
        location_id = _ask("Short stable location ID (for example hkust-football-field)", input_func=input_func)
        target_id = _ask("Short stable target ID (for example natural-turf-pitch)", input_func=input_func)
        temporal_group_id = _ask(
            "Short group ID for these repeated observations (for example field-20260202)",
            input_func=input_func,
        )
        if not all((location_name, location_id, target_id, temporal_group_id)):
            output_func("Location name, location_id, target_id, and temporal_group_id are all required.")
            continue
        output_func("Review the visible/thermal paths and spatial evidence shown above before confirming.")
        confirmed = _yes_no(
            "I confirm that all selected captures represent the same physical location or target area.",
            input_func=input_func,
            default=False,
        )
        roi_confirmed = _yes_no(
            "I confirm that each selected capture uses an accepted, comparable ROI for this same target.",
            input_func=input_func,
            default=False,
        )
        conflicts = _spatial_conflicts(selected, location_id, target_id, location_name)
        override = False
        override_reason = ""
        if conflicts:
            output_func("Spatial evidence conflict detected:")
            for conflict in conflicts:
                output_func(f"  - {conflict}")
            override = _yes_no(
                "Do you explicitly override these conflicts after manual spatial review?",
                input_func=input_func,
                default=False,
            )
            if override:
                override_reason = _ask("Reason for the manual spatial override", input_func=input_func)
                if not override_reason:
                    output_func("A non-empty override reason is required; this group was not accepted.")
                    continue
            else:
                output_func(
                    "This temporal group was not accepted because the spatial conflicts were not overridden. "
                    "The selected captures remain available for a corrected group."
                )
                continue
        registration = _yes_no(
            "Is reliable pixel-level spatial registration confirmed for these captures?",
            input_func=input_func,
            default=False,
        )
        registration_method = _ask("Registration method", input_func=input_func) if registration else ""
        registration_id = _ask("Stable registration_id", input_func=input_func) if registration else ""
        try:
            definition = TemporalGroupDefinition(
                temporal_group_id=temporal_group_id,
                image_ids=[str(card["image_id"]) for card in selected],
                location_id=location_id,
                target_id=target_id,
                location_name=location_name,
                target_name=location_name,
                same_location_confirmed=confirmed,
                confirmation_provenance="ordinary_user_interactive_cli",
                roi_comparable_confirmed=roi_confirmed,
                spatial_override_confirmed=override,
                spatial_override_reason=override_reason,
                registration_confirmed=registration,
                registration_method=registration_method,
                registration_id=registration_id,
            )
        except ValueError as exc:
            output_func(f"Temporal group was not accepted: {exc}")
            continue
        definitions.append(definition)
        assigned.update(selected_numbers)
        output_func(
            f"{len(selected)} capture(s) were submitted for location: {location_name}. "
            "Scientific compatibility will be checked before any range is calculated."
        )
        if not _yes_no("Do you want to define another temporal group?", input_func=input_func, default=False):
            break
    return TemporalAnalysisPlan(temporal_requested=True, groups=definitions)
