"""Controlled LUHK context vocabulary and provenance validation."""

from __future__ import annotations

from dataclasses import dataclass

from .models import LUHKProvenance


LUHK_CATEGORIES = {
    "residential": "Residential",
    "commercial": "Commercial",
    "industrial": "Industrial",
    "gic_open_space": "GIC / open space",
    "transport": "Transport",
    "other_urban_built_up": "Other urban / built-up land",
    "agriculture": "Agriculture",
    "woodland_shrubland_grassland_wetland": "Woodland / shrubland / grassland / wetland",
    "barren_land": "Barren land",
    "water_bodies": "Water bodies",
}


@dataclass(frozen=True, slots=True)
class LUHKContext:
    code: str
    category: str
    provenance: LUHKProvenance


def resolve_luhk_context(value: str, provenance: str) -> LUHKContext:
    text = value.strip()
    if not text:
        raise ValueError("Part C* requires a LUHK category.")
    normalized = text.casefold().replace("/", " ").replace("-", " ")
    normalized = "_".join(normalized.split())
    by_name = {name.casefold(): code for code, name in LUHK_CATEGORIES.items()}
    code = text if text in LUHK_CATEGORIES else by_name.get(text.casefold(), normalized)
    if code not in LUHK_CATEGORIES:
        raise ValueError(f"Unknown LUHK category: {value!r}")
    resolved_provenance = LUHKProvenance(provenance)
    if resolved_provenance == LUHKProvenance.UNKNOWN:
        raise ValueError("An accepted Part C* target requires official or user-supplied LUHK provenance.")
    return LUHKContext(code=code, category=LUHK_CATEGORIES[code], provenance=resolved_provenance)
