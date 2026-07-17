# Version 0.3 temporal-analysis methodology

## Scientific unit

One image/capture time is one temporal observation. Thermal pixels, polygon
pixels, TAT3 clicked points, and TAT3 regions are within-image spatial
measurements. They are summarized before any cross-time comparison and never
used as independent time replicates.

Per compatible capture/source/target stratum, the output reports capture time,
timezone assumption, total/finite/eligible counts, target coverage,
known/unknown counts, source/provenance/QA state, and temperature/ΔT min, max,
mean, median, q01, q95, and q99. Missing ambient retains temperature statistics
and removes ΔT statistics; no value is imputed.

## Compatibility

Temperature comparison strata include measurement type, temperature source and
definition, source method, cover/LUHK provenance, stable target linkage, and QA.
ΔT strata additionally include ambient source and definition. Different
pixels/points/regions, sources, definitions, targets, or provenance are not
silently pooled.

An explicit `target_id` is required to link a target across captures. Missing
IDs remain single-capture/unlinked. One polygon's coordinates are never reused
on another image automatically.

## Time QA

Naive timestamps use recorded capture timezone; if absent, the required CLI or
runner timezone is recorded as an assumption. Times are converted to UTC for
deterministic sorting. Invalid/ambiguous times, duplicate image/pixel grids,
duplicate timestamps inside a compatibility stratum, ambiguous ambient values,
and inconsistent names for one target ID are diagnosed and excluded from the
affected trend.

Irregular intervals are retained and listed. Default interpolation is disabled.
One compatible capture receives `single_capture_descriptive_no_trend`; two or
more receive `multi_capture_descriptive_exploratory`.

## Aggregation and figures

Cross-time summaries average capture-level statistics with equal capture
weight, so images with more pixels/clicks cannot dominate. Figures show
chronological mean/median and descriptive within-image q01–q99 bands, plus
source-stratified capture-level panels. These bands are not confidence
intervals. No generalizable temporal claim is allowed from one capture, and all
multi-capture inference is exploratory.

Outputs are under `tables/`, `figures/`, `qa/`, and `summaries/`. Cache identity
includes canonical SHA-256, the temporal implementation SHA-256, timezone,
temporal unit, aggregation, interpolation, and statistic definitions.
