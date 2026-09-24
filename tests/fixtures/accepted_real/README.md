# Accepted real-data replay fixture

The active `manifest.json` and case directories are absent from this clone. They
must come from the owner-reviewed `main`/Windows run, not from the Phase 2
candidate. The template records the exact target for the first normal pilot:

```text
tests/fixtures/accepted_real/
  manifest.json
  DJI_20260107143259_0005/accepted/
    manifest.json
    temperature.npy
    surface_cover_labels.npy
    surface_cover_known_mask.npy
    target_mask.npy
    luhk_labels.npy
    luhk_known_mask.npy
    pixels.parquet
    shadow_mask.npy              # include when present in the accepted run
```

Copy the accepted canonical output directory as a unit. Copy the matching
Windows-produced Part D input matrix to the path listed for that image in
`outputs/part_d/summaries/part_d_tat3_parameter_temperature_extraction_summary.csv`
(normally `data/processed/part_d/temperature_matrices/`). Preserve its original
sidecar and TAT3 report separately. Fill the active manifest from
`manifest.template.json`: identify the reviewed run, compute SHA-256 of each
accepted file, and list every scientific provenance field that must remain
stable. Add a checksum entry for `shadow_mask.npy` when it is present. Restore
the run-scoped Part A, B0, and B review JSON records to their original
`outputs/runs/...` paths and put their paths and hashes in `review_records`.
The replay checks those reviewed inputs against the accepted manifest before
passing them to the pilot adapter.

The test generates a fresh Phase 2 canonical result from those pilot inputs in
a temporary directory and compares it with the immutable `main` snapshot. It
checks IDs, dimensions, V/T filenames, alignment metadata, masks, the thermal
matrix, ambient and extraction provenance, every accepted pixel-table column,
per-pixel ΔT, and grouped cover counts and mean ΔT. Categorical data must be
exact. Existing float32 pilot temperature assertions use an absolute bound of
`2e-6 °C`; grouped float64 means use `1e-6 °C`. The test skips only when the
active manifest is absent. An incomplete active fixture fails.
