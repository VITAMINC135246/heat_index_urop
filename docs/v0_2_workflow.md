# Version 0.2 persistent A–E workflow

Version 0.2 connects the verified numbered Part A–E implementations through
`scripts/run_analysis.py`. The scientific baselines were modularized and
parameterized; they were not replaced. The original numbered entry points
remain usable as compatibility wrappers.

## Supported entry points

Persistent canonical processing:

```powershell
.\.venv\Scripts\python.exe scripts\run_analysis.py --help
.\.venv\Scripts\python.exe scripts\run_analysis.py selected --group V.JPG T.JPG
.\.venv\Scripts\python.exe scripts\run_analysis.py dataset --dataset-root data\raw\HKUST
```

Separate temporary manual TAT3 processing:

```powershell
.\.venv\Scripts\python.exe scripts\run_tat3_manual_analysis.py --help
```

The persistent workflow writes per-run Part A, B0, and B records under the
ignored `outputs/runs/` tree. Successful canonical results use NPY and Parquet;
full-pixel CSV and Excel remain opt-in.

## Route state machine

Each group is isolated from failures in other groups.

1. Check the local result index for a successful, non-failed-QA schema-0.2
   result with matching raw, configuration, decision, annotation, LUHK,
   temperature, TAT3, SDK, and tool fingerprints.
2. On a miss, Part A validates the thermal input first. Fatal thermal errors
   fail the group. A valid thermal image with unusable visible input enters
   Part C*.
3. A usable pair enters Part B0. `content_mismatch_candidate` enters Part C*.
   `needs_manual_review` pauses as `awaiting_part_b0_review` unless explicitly
   accepted or rejected. `content_match_candidate` is candidate evidence only.
4. An accepted B0 match runs the preserved full Part B crop search, candidate
   scoring, optional GCP refinement, transform persistence, and review package.
5. Only a final manual acceptance with
   `thermal_fully_supported_by_visible` enters normal Part C. Rejection may
   enter Part C*. Cancellation and unreviewed/indeterminate evidence never
   silently enter normal Part C.
6. Normal Part C runs the preserved reviewed SLIC workflow. Part C* requires an
   accepted native-grid thermal polygon, target, physical cover, LUHK category,
   and independently recorded LUHK provenance.
7. Temperature extraction is independent of label availability. Failed QA is
   retained as failed and is never indexed or admitted to Part E.
8. Successful normal and polygon routes write the same schema-0.2 contract,
   then Min/Max/q01/median/q95/q99 tables and location figures.
9. Part E receives only compatible successful manifests. The run summary keeps
   success, cache-hit, failed, cancelled, awaiting-review, excluded, and
   incomplete groups for the inclusion/exclusion report.

## Part A

`scripts/workflow/input_validation.py` reuses the repository filename pairing,
metadata fields, table conventions, and camera-profile assumptions. Its atomic
per-group record distinguishes fatal thermal errors from visible-only errors
and pairing uncertainty. It records paths, roles, IDs, timestamps/session,
dimensions, native temperature-grid compatibility, camera/focal/profile,
altitude, GPS, metadata source, warnings, and errors. A supplied Part B decision
cannot bypass fatal Part A validation.

## Part B0 and full Part B

Part B0 is explainable triage, not alignment acceptance. It evaluates a grid of
plausible non-centred visible crops at several scales and positions using the
preserved cross-modal structural scoring utilities, edge overlap, normalized
mutual-information-like evidence, and phase response. Configurable score,
margin, texture, and edge thresholds produce match, mismatch, or manual-review
states. The initial thresholds are not claimed to be generally calibrated from
five pilot images.

Full Part B calls the existing `b05_refine_vt_alignment` candidate search and
GCP functions and the `b06_generate_alignment_refinement_review` package
generator. Filename/time pairing, B0 correspondence, spatial overlap, coverage,
automatic candidate, GCP evidence, manual review, final alignment, and routing
remain separate fields.

## Normal Part C and the superpixel GUI

The adapter calls the original SLIC and segment-summary functions, retains
prefill suggestions as suggestions only, and calls the extracted final reviewed
thermal-grid mask generator after acceptance. A bare label NPY is rejected; a
compatibility override needs a companion accepted review manifest with identity,
dimensions, mapping, reviewer/source, and artifact hash.

The Matplotlib GUI displays the reviewed visible ROI with superpixel boundaries
and an optional thermal panel. Its headless controller supports multi-selection,
physical-cover assignment, unknown/unclear marking, a separate shadow layer,
clear, undo/redo, notes, reviewer/confidence, draft save/resume, validation,
accept, and cancel. Unreviewed segments remain explicit and block acceptance.
See `docs/v0_2_gui_and_tat3.md` for the smoke-test checklist.

## Thermal-polygon Part C*

Inside an accepted polygon, target, surface-cover-known, and LUHK-known are true
and finite pixels are target eligible. Outside, target is false, both target
contexts remain unknown, and pixels are excluded from target analysis. The
full temperature matrix is retained. `target_mask.npy` is independent of the
surface-cover and LUHK known masks.

`official_luhk_lookup` means an actual spatial lookup. Choosing a category from
the controlled vocabulary is `user_supplied_luhk`; vocabulary membership alone
does not make it official. Displayed thermal dimensions and the supplied or
extracted native matrix must match exactly; no polygon is silently rescaled or
clipped.

## Shared Part D and QA isolation

`scripts/workflow/temperature_extraction.py` is the active DJI/TAT3
implementation. The numbered Part D batch script calls it. It preserves TAT3
distance, humidity, emissivity, ambient and reflected temperature, the DJI
`measure/float32` command, native dimensions, and the existing QA rules. NPY
overrides retain temperature without fabricating missing ambient; such rows are
excluded from formal delta-temperature sampling while other images continue.

## Formal Part E and source policy

The schema-0.2 runner accepts a manifest list, a run summary, or a compatible
combined Parquet. It calls the preserved deterministic spatial thinning,
exploratory statistics, effect sizes, 21-seed stability analysis, SciPy KDE,
PNG/PDF spectra, QA, resume, and report stages under `scripts/part_e/`.
Optional LUHK, shadow, and ambient families are reported as unavailable rather
than imputed. The five-image pilot remains supported through the adapter.

Primary outputs retain image/time, measurement type, temperature source,
source method, surface-cover provenance, LUHK provenance, target, and QA
strata. Cross-source dashboards use image-level means so images with more
pixels do not dominate. Pixels, points, and regions are within-image spatial
observations; image/capture time is the temporal unit. No pooled inferential
result is produced by default. The optional pooled sensitivity file is
explicitly named, reports composition, and never replaces source-stratified
results.

## Extreme-temperature outputs

Every successful persistent image receives CSV summaries and coordinate tables
for minimum, maximum, q01, median, q95, q99, delta extremes, counts, ties, and
QA flags. Row-major order selects a deterministic representative tied minimum
and maximum. q99 is stored and drawn as a threshold/exceedance region, not
misrepresented as one unique point. Polygon figures draw the accepted boundary.

## Known limitations

- B0 thresholds are initial triage thresholds, not a trained or generally
  calibrated cross-modal classifier.
- Automatic Part B and GCP evidence still require human final review.
- GUI interaction is local and blocking; headless tests cover the controller,
  not every desktop backend.
- A real DJI SDK executable is intentionally not required by the default tests.
- Pixel-level statistical results remain exploratory because spatial
  autocorrelation persists after thinning.
- Temporary TAT3 export layouts not represented by the parser fail with a clear
  diagnostic and retain the source evidence for a future adapter.
