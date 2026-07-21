# Version 0.3 canonical/schema decision

## Decision

Version 0.3 keeps canonical schema `0.2.0` and changes only
`processing_version` to `heat-index-urop-0.3.1` for the current maintenance release.

A schema `0.3.0` bump is unnecessary because the required pixel contract did
not change: image/pixel identity, native coordinates, temperature, cover/LUHK,
target mask, shadow, eligibility, exclusion, measurement type, source, QA, and
provenance already exist. v0.3 adds optional `target_id`, capture timezone, and
mapped temperature/ambient definition columns. Older 0.2 and 0.1 manifests can
still be read; missing optional values are reported rather than invented.

## Stable target linkage

`target_name` is a display label. `target_id` is the stable cross-capture
identifier. Temporal target series require a non-empty explicit `target_id`.
When it is absent, a capture may still receive descriptive statistics, but its
linkage key is isolated as `unlinked:<image_id>` and it cannot be pooled with
another capture by target name alone.

Each capture requires its own accepted `target_mask`. Coordinates from one
image must not be reused for another image unless separately validated
registration/transfer evidence exists and is recorded. The current software
does not silently transfer polygons.

## Definitions and provenance

- `measurement_type` separates full thermal pixels, polygon-selected pixels,
  TAT3 points, and TAT3 regions.
- `temperature_source` and `temperature_definition` identify how apparent
  surface temperature was obtained.
- `ambient_temperature_c`, `ambient_source`, and `ambient_definition` identify
  the air-temperature reference. Missing ambient produces missing ΔT.
- `surface_cover_provenance` and `luhk_provenance` remain independent.
- `target_mask`, `label_known`, and `analysis_eligible` are independent flags.
- Polygon exterior cover/LUHK context is unknown; it is not assigned the target
  class and is not analysis eligible.

## Read compatibility

Schema-0.2 is the active writer contract. Schema-0.1 compatibility remains
read-only through the existing compatibility reader. Missing v0.3 optional
metadata appears as empty/unknown and leads to explicit temporal exclusions;
it never causes fabricated target, time, ambient, LUHK, or shadow values.
