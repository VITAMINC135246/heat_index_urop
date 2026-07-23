# Version 0.3.2 temporal-analysis methodology

## Default: no temporal claim

Temporal analysis is optional and defaults to **No** in the ordinary-user
workflow. Starting the program remains one command:

```powershell
.\.venv\Scripts\python.exe scripts\run_user_workflow.py
```

Pressing Enter at the temporal question records that temporal analysis was not
requested. All normal single-capture, extreme-temperature, spectrum, spatial,
and statistical outputs remain available. No empty trend figure and no implied
cross-capture grouping is created.

## Explicit spatial identity is required

A temporal group is a user-confirmed set of repeated observations of one
physical target, not every image processed in one run. The software never
groups captures automatically from a folder, date, filename, target display
name, timestamp proximity, or GPS proximity.

For every group, the user selects capture numbers and provides:

- a human-readable location or target name;
- one stable `location_id`;
- one stable `target_id`;
- one unique `temporal_group_id`;
- explicit confirmation that all captures show the same physical location;
- explicit confirmation that the accepted ROIs are comparable.

The program shows each image ID, V/T paths, capture time and source, GPS,
recorded target/location IDs, dataset, temperature source, and measurement type
before confirmation. Conflicting recorded IDs or GPS centres more than the
review threshold apart are displayed. A conflict needs an explicit override
and a non-empty reason; otherwise the group is excluded. One capture can belong
to only one temporal group in the same run. The user may define multiple
independent groups one after another.

One capture is still useful descriptively, but it cannot produce a trend,
hottest-versus-coolest comparison, or peak-to-trough range. At least two
compatible captures are required.

## Scientific unit and compatibility

One accepted capture of one physical target is one temporal observation.
Thermal pixels inside that capture are within-capture spatial measurements;
they are summarized before cross-time comparison and are never treated as
independent time replicates.

Temperature series remain separate when measurement type, temperature source
or definition, source method, target identity, surface-cover provenance, LUHK
provenance, or QA compatibility differs. ΔT series additionally require
compatible ambient source and ambient definition. Missing ambient preserves
temperature results but makes ΔT unavailable; no ambient value is imputed.

For polygon captures, only accepted finite pixels satisfying
`analysis_eligible=true` and `target_mask=true` enter the target summary.
Polygon-exterior temperatures remain auditable source data but do not affect the
football-field hottest, coolest, or range result.

## What “hottest”, “coolest”, and “range” mean

Results are calculated independently within each compatible stratum and
observation window.

The primary reported target comparison uses the capture-level ROI mean:

- hottest capture: the capture with the largest accepted-target ROI mean;
- coolest capture: the capture with the smallest accepted-target ROI mean;
- observed peak-to-trough range: hottest ROI mean minus coolest ROI mean;
- timestamps and image IDs: reported for both endpoints;
- time interval: absolute elapsed time between those endpoint captures.

The same table also reports ranges for ROI median, ROI q95, and the sequence of
capture-level ROI maxima. Median is a robust central summary. q95 is the
recommended robust hot-tail summary when the question concerns unusually hot
target pixels but a single maximum is too sensitive to noise. Neither is a
confidence interval.

`absolute_pixel` is deliberately separate. It is the hottest single accepted
pixel observed in any compatible capture minus the coolest single accepted
pixel observed in any compatible capture. It records the endpoint image, time,
row, and column. This value is sensitive to isolated noise, emissivity errors,
misregistration, and small objects, so it must not replace the ROI mean/median
or robust q95 range. Without registration, its two endpoints are not claimed to
be the same ground point.

Temperature and ΔT have separate peak-to-trough tables. A statement such as
“up to +26°C” is not considered reproduced until its metric family, statistic,
ROI, ambient definition, and endpoint captures match the original procedure.

## Sampling limitations

Capture times are converted to UTC for ordering while the recorded/default
timezone remains visible. Invalid times, duplicates, irregular intervals,
missing periods, and incompatible captures are listed rather than repaired.
Interpolation is disabled.

Every temporal result describes the sampled observation window. The output
lists its start/end time, span, interval sequence, largest gap, daytime/nighttime
presence, and exact exclusions. A 09:00–17:00 sequence is a daytime observed
range, not a daily maximum/minimum. Even observing both day and night does not
prove that the true daily extrema were captured. The ordinary interactive
workflow therefore uses sampled-window wording and does not silently promote a
partial flight schedule to a full-day design.

Within-capture q05–q95 or q01–q99 bands show spatial variation inside each ROI;
they are not uncertainty bands for the time series. Multi-capture results are
descriptive and exploratory, not evidence of a general seasonal or causal
effect.

## Pixelwise analysis requires registration

Comparable target-level ROIs are sufficient for capture-level mean, median,
q95, maximum, and range summaries. They are not sufficient for pixel-to-pixel
change maps.

The pixelwise branch defaults to No. It runs only if reliable cross-capture
registration is explicitly confirmed and both a registration method and stable
`registration_id` are recorded. It then checks compatible grids and target
coverage before writing registered pixelwise maximum, minimum, and observed
range maps. If registration is absent or invalid, the group report states the
exact unavailable reason; no array-index correspondence is fabricated.

## Current output structure

The temporal root contains run-level control files:

- `temporal_run_summary.md` — readable requested/skipped and group summary;
- `temporal_run_manifest.json` — plan, group status, and artifact index;
- `temporal_output_validation.json` — canonical hash and file validation;
- `temporal_stage_state.json` — resume identity.

Each explicit group has its own `<temporal_group_id>/` directory:

- `temporal_summary.md` — primary readable hottest/coolest/range report;
- `tables/per_capture_statistics.csv` — per-capture temperature and ΔT stats;
- `tables/capture_compatibility.csv` — strata and exact eligibility;
- `tables/peak_to_trough_statistics.csv` — temperature ranges;
- `tables/delta_t_peak_to_trough_statistics.csv` — ΔT ranges;
- `tables/sampling_coverage.csv` — window, gaps, and coverage limits;
- `tables/submitted_captures.csv` — requested membership;
- `qa/exclusions.csv` and `qa/temporal_group_qa.md` — exact exclusions and QA;
- `figures/target_temperature_vs_local_time.*` when a series is available;
- `figures/target_delta_t_vs_local_time.*` when compatible ΔT is available;
- range/coverage figures and, only when registered, pixelwise figures.

This per-group structure replaces the older misleading model in which one
directory-wide capture table and generic source-stratified figures could appear
to be an automatically inferred temporal series.
