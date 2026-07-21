# Version 0.3 workflow

## Scope

Version 0.3 extends the completed v0.2 A–E workflow. It does not replace Part A
validation, Part B0 structural triage, reviewed Part B, reviewed SLIC Part C,
thermal-polygon Part C*, shared DJI/TAT3 extraction, canonical eligibility,
spatial thinning, descriptive statistics, effect sizes, KDE spectra, extremes,
or temporary TAT3 analysis.

The maintenance release processing version is `heat-index-urop-0.3.1`; canonical schema remains
`0.2.0`. The supported default configuration is
`config/workflow_v0_3.json`; acceptance uses the isolated
`config/workflow_v0_3_acceptance.json`.

## Persistent route

1. Part A validates V/T inputs, timestamps, metadata, native dimensions, and
   temperature-grid compatibility.
2. Part B0 produces match/mismatch/review evidence only. An explicit accepted
   B0 review may continue to full Part B but cannot accept final alignment.
3. Full Part B requires explicit accepted correspondence and full thermal
   support for the normal route. Rejected/unusable visible correspondence may
   enter Part C* when thermal input remains valid.
4. Normal Part C requires an accepted reviewed superpixel result. Bare label
   NPY files without accepted review evidence remain invalid.
5. Part C* requires an accepted polygon, target name, cover, LUHK category and
   provenance. Cancellation or draft status cannot create a canonical success.
6. Part D uses a real compatible matrix from an explicit NPY override or the
   shared DJI SDK/TAT3 route. Matrix dimensions must equal the native thermal
   grid. Failed temperature QA is isolated from Part E.
7. Canonical pixels retain full native grids, target/known/eligibility masks,
   source/measurement/provenance, and missing-layer semantics.
8. Part E aggregates normal and polygon results without default source pooling,
   preserves validated sampling/statistics/KDE stages, generates canonical
   spatial figures, then generates capture-level temporal outputs.

## Spatial completion

The runner now executes from `sample` through `spatial-figures`. It skips the
optional supporting/Excel stages unless explicitly requested. Spatial resume
requires `spatial_figure_validation.json`, control CSVs, and every listed
PNG/PDF to exist and match the canonical and spatial-method SHA-256 values. A
no-pixel source such as a TAT3 point produces a recorded not-applicable
exclusion, never an unexplained empty directory.

## Temporal completion

The temporal unit is one image/capture. The temporal module accepts canonical
manifests, a run summary, or compatible shared Parquet through
`scripts/run_temporal_analysis.py`. It records timezone assumptions, sorts UTC
times deterministically, detects duplicates, preserves irregular intervals,
requires explicit target linkage for cross-capture target series, and separates
measurement/source/temperature/ambient/provenance/QA strata.

No interpolation is performed. Single captures are descriptive, not trends.
All multi-capture interpretation is exploratory. q01/q95/q99 bands are
within-image descriptive variation, not confidence intervals.

## Cache dependencies

- Per-image cache: source hashes, group configuration, review decisions,
  dependency fingerprints, schema, processing version, and artifact hashes.
- Formal Part E resume: combined canonical Parquet SHA-256 plus a deterministic
  signature of the generated config and sampling/statistics/spectrum/spatial/
  temporal implementations.
- Spatial resume: canonical and spatial-method SHA-256 plus listed output
  presence/size.
- Temporal resume: canonical SHA-256, timezone/method configuration SHA-256,
  and all expected tables/figures/reports.

Changing a polygon, target ID, label/review, temperature matrix, ambient value
or definition, source method, capture timestamp/timezone, configuration, or
canonical artifact invalidates the relevant downstream cache.
