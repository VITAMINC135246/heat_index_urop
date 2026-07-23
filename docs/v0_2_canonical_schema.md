# Canonical schema 0.2, provenance, and cache contract

Persistent results use `schema_version = 0.2.0` and
`processing_version = heat-index-urop-0.2`. Schema 0.1 manifests can be read by
the deliberate compatibility reader but are not silently rewritten or indexed
as schema 0.2.

## Per-image layout

The default root is `data/processed/images/<image_id>/`:

- `manifest.json`
- `temperature.npy` (`float32`, native thermal grid)
- `surface_cover_labels.npy` (`int16`, `-1` only as unknown storage sentinel)
- `surface_cover_known_mask.npy` (`bool`)
- `luhk_labels.npy` and `luhk_known_mask.npy`
- `target_mask.npy`
- optional `shadow_mask.npy`
- `pixels.parquet`
- extreme summary/coordinate CSVs and PNG/PDF location figures

NPY, Parquet, and manifest writes use temporary sibling files and atomic replace
where practical. The result index is updated only after a successful manifest
and artifacts exist. A partial write without a manifest is not reusable.

## Manifest content

The manifest records configuration, dependency, source, derived-input, and
tool fingerprints; image/group/pair/dataset identity; Part A; Part B0; full
Part B transform/GCP/review evidence; route; native dimensions; temperature and
ambient metadata; polygon/target context; surface-cover and LUHK provenance;
selection scope; QA; annotation review; exclusions; notes; timestamps; and a
hash/dtype/shape reference for each artifact.

Measurement types are exact:

- `full_thermal_pixel`: normal accepted visible/thermal route
- `polygon_selected_thermal_pixel`: accepted Part C* target pixels
- `manual_tat3_point`: temporary report point; never persistent by default
- `manual_tat3_region`: temporary report region statistic; never persistent by
  default

Normal results use `surface_cover_provenance = visible_review`. Polygon results
use `surface_cover_provenance = thermal_polygon_user_annotation`. LUHK
provenance is independent: `official_luhk_lookup`, `user_supplied_luhk`, or
`unknown` where unavailable. Accepted polygons may not use unknown LUHK.

## Shared pixel schema and eligibility

Each row retains image identity, native row/column and pixel UID, temperature,
ambient and delta temperature, measurement and temperature source, source
method, cover label/known/provenance, LUHK label/known/provenance, target flag,
optional shadow value/validity, review and QA states, eligibility, and exclusion
reason.

Temperature can be finite while a label or ambient value is unavailable.
`analysis_eligible` never invents a label. Formal delta-temperature sampling
additionally requires finite `delta_t_c`; missing ambient excludes that image
from delta analysis without discarding its temperature matrix.

For target polygons, exterior rows remain in the full matrix but have
`target_mask = false`, target-specific cover/LUHK unknown, and
`exclusion_reason = outside_target_selection`.

## Cache dependencies

The lightweight index key/check covers, where relevant:

- raw visible and thermal hashes;
- metadata record;
- B0 configuration and explicit decision;
- full Part B transform, GCP, coverage, and final review evidence;
- Part C segments/review/mapping and optional shadow mapping;
- LUHK source/version/context;
- polygon coordinates, target, cover, LUHK, notes, and review decision;
- temperature NPY or TAT3 parameter row;
- SDK configuration and SDK executable identity/hash;
- schema/processing versions and per-group relevant configuration.

Lookup reloads and validates the manifest, successful processing and non-failed
QA, every required artifact, artifact hash, NPY dtype/shape, and native
temperature dimensions. Stale dependencies, missing or damaged artifacts,
schema mismatch, failed QA, and partial writes are cache misses.

Request-global payloads are reduced to per-image fingerprints so changing one
polygon or review does not invalidate unrelated images.
