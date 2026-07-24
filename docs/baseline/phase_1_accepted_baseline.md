# Phase 1 Accepted Baseline

## Status and authority

Phase 1 protects the accepted baseline. The accepted scientific baseline is the
pre-Phase-1 `HEAD` plus artifacts explicitly recorded as accepted before this
phase. These Phase 1 records describe that baseline; they do not redefine it.

No production code, configuration value, schema, CLI, review gate, routing
rule, scientific method, temporal behavior, version, tag, or release state was
changed. No Phase 2 work has begun.

The machine-readable evidence is in
`docs/baseline/phase_1_baseline_manifest.json`. The checksum file protects the
two baseline records after final generation.

## Git identity

- Repository root: `.`
- Branch: `main`
- Commit: `953e97408689736296b4f05198932f54cfea667f`
- Commit timestamp: `2026-07-23T23:29:25+08:00`
- Commit subject: `Merge v0.3.2 LUHK and temporal workflow`
- Tags at `HEAD`: none
- Existing prior validation tag: `pre-e2e-validation-2026-07-15` at
  `90a10d605d19bb3221dfca4353c8df9111f1dc5a`
- Local `main` matched the already configured `origin/main` tracking ref at the
  same SHA. No fetch or pull was performed.

The initial tree had no tracked or staged changes. It had 57 user-owned
untracked entries: 55 under `commit_code_exports/` and two under
`outputs/presentations/`. They were excluded from baseline selection and left
unchanged. Phase 1 created only the three files listed in the rollback section.

## Project boundaries inspected

The ordinary-user entry point remains `scripts/run_user_workflow.py`.
Developer entry points include `scripts/run_analysis.py`,
`scripts/run_tat3_manual_analysis.py`, `scripts/run_temporal_analysis.py`, and
the numbered Part A through Part E scripts. Canonical schema remains `0.2.0`;
processing version remains `heat-index-urop-0.3.2`.

Production and acceptance configurations, scientific mappings, camera
profiles, pairing records, local-tool resolution, result-index behavior,
canonical stores, Part D and Part E locations, run-scoped outputs, and temporal
outputs were inspected. The ignored local configuration and data rules in
`.gitignore` were preserved.

## Reference environment

- Windows 11 build `10.0.22631`, AMD64
- CPython `3.12.13`, MSC v.1944, normalized executable
  `.venv/Scripts/python.exe`
- pip `26.1.2`
- pytest `9.1.1`
- GDAL `3.12.1`, PROJ `9.5.1`, GEOS `3.13.1`, OpenCV `5.0.0`
- Normalized sorted package inventory SHA-256:
  `dde29788964ea1fb90f0773bd5be21b3f1db69e57fcf0062fc5d1422a5237da4`

The full exact package inventory and normalization rule are in the JSON
manifest. This is an observation of the reference environment, not a lock file.

## External tools

- DJI Thermal SDK `dji_irp.exe`: available, x64, safe `--version` output
  `APP version: V1.7`, SHA-256
  `58e693879f8cf504738ed9f9ced8769dd0d1c81a532b0e6683f2c4f2d8654372`.
  Accepted metadata confirms native float32 measure output and the distance,
  humidity, emissivity, ambient, and reflection parameters.
- ExifTool: local 64-bit Windows distribution identity `13.59`, SHA-256
  `68c079c32fdae0d6c7130e9a5fb73f8ac9dabdf9ab8da312da4f6c549d6d3385`.
  Its installed `-k` wrapper is interactive, so it was not launched merely to
  obtain a version.
- TAT3: no standalone version was invented and no GUI was opened. Identity is
  limited to accepted report metadata and local hashes. The selected pilot and
  football-field reports are recorded by normalized labels and hashes in the
  manifest; their contents were not copied.
- Microsoft Excel: installed x64 product version `16.0.20131.20154`, identified
  from executable metadata and hash only. Excel was not launched or automated.
- Node.js `v22.18.0` and Windows PowerShell `5.1.22621.5624` were identified
  non-interactively.

No proprietary binary, report, license, sensitive path, or secret was added.

## Configuration evidence

The manifest records byte hashes and sizes for:

- `config/workflow_v0_3.json`
- `config/workflow_v0_3_acceptance.json`
- `config/part_d_sdk.template.json`
- `config/part_e_delta_t_analysis.json`
- `config/part_e_delta_t_analysis.template.json`
- both tracked v0.3 football acceptance templates
- LUHK, surface-cover, shadow, and camera mappings
- the pilot ambient manifest and Part B pair table

The ignored `config/part_d_sdk.local.json` was not copied or hashed as a file.
Only its non-path scalar values were normalized. Their SHA-256 is
`a8b841bba3d5a80998b275966c4baefd4571c89d5088ad60cd171ea703ac12b1`.
Those local defaults are explicitly not treated as the accepted per-image
effective radiometric settings; the accepted output records preserve the
TAT3-derived effective values.

## Test evidence

Inspection showed that tests use temporary directories, synthetic fixtures,
mock SDK calls, and a headless Matplotlib backend. One
`local_integration` test reads ignored TAT3 reports without modifying them.
Tests do not need Excel, an interactive GUI, or a real DJI extraction.

Collection command:

```text
.venv/Scripts/python.exe -m pytest --collect-only -q -p no:cacheprovider
```

It collected 117 tests in 4.23 seconds.

Successful test command:

```text
PYTHONDONTWRITEBYTECODE=1
MPLBACKEND=Agg
MPLCONFIGDIR=<OS_TEMP>/heat_index_phase1_tests_<random>/mpl
TEMP=<OS_TEMP>/heat_index_phase1_tests_<random>/temp
.venv/Scripts/python.exe -m pytest -ra -p no:cacheprovider
```

The run started `2026-07-24T02:52:03.2881831+08:00` and ended
`2026-07-24T02:55:10.4162365+08:00`. Result: 117 passed, zero failed,
zero skipped, zero xfail, and zero errors in 186.21 seconds (187.128 seconds
observed wall time). Repository status was unchanged.

The first launch attempt was terminated by the command wrapper before pytest
produced results. It left no Python process and only its exact isolated
temporary directory, which was removed before the successful run. It is not a
test result.

## Representative accepted scientific evidence

### Selection

The accepted six-image workflow run is
`outputs/runs/v0_3_user_acceptance/workflow_runs/run_20260722T055625Z/`.
Its matching immutable Part E snapshot is
`outputs/runs/v0_3_user_acceptance/part_e/schema_0_2/run_20260722T055625Z/`.
Committed acceptance documentation explicitly identifies this pair as the
accepted run containing five normal Part C routes and one Part C* route.

`DJI_20260107143259_0005` is the compact normal-route representative. It covers
Part A validation and time resolution, B0 triage, final manual Part B
correspondence/full-support acceptance, visible-review surface cover, official
LUHK context, a complete native thermal grid, Part D temperature, canonical
schema `0.2.0`, and Part E.

`DJI_20260202091128_0058` is the Part C* representative. It covers the
pairing-warning and rejected-correspondence fallback, accepted polygon,
target-scoped surface-cover and user-supplied LUHK context, retained full
native temperature grid, outside-polygon unknown/ineligible behavior,
canonical/Part E stratification, and a single-capture no-trend result.

The explicitly accepted temporal run
`run_20260722T053855Z` covers three independently accepted captures at one
confirmed location and comparable target. `run_20260722T064301Z` supplies a
clean temporal-not-requested record.

### Immutable versus scientific-equivalence policy

Production configurations, mapping tables, workflow review JSON, run summaries,
and stage-state records use byte-level SHA-256 identity. NPY, Parquet, CSV,
PNG/PDF, Markdown summaries, and temporal outputs use scientific-equivalence
metrics plus file hashes. A byte mismatch in an immutable record requires
review; it does not by itself prove a scientific regression. Serialization,
container, path, timestamp, and rendering-only differences in
scientific-equivalence outputs may be acceptable only when all recorded
scientific and structural metrics remain equivalent.

### Normal route

The representative canonical result has 327,680 unique native coordinates on a
512 by 640 grid, no duplicates, 327,680 finite float32 temperatures, and all
pixels known, target-true, LUHK-known, and analysis-eligible. Temperature
minimum/mean/maximum are -17.5691280365 / 14.2802686941 / 45.5172042847 degC.
The accepted ambient parameter is 11.0 degC with provisional TAT3 provenance;
eligible mean Delta-T is 3.2802686942 degC.

It preserves four surface-cover classes and three official LUHK categories.
The manifest, arrays, Parquet file, normalized row checksum, exact quantiles,
class counts, and provenance strata are in the JSON manifest.

### Polygon route and accepted run scope

The accepted run-scoped canonical aggregate has SHA-256
`aa2c3fefa1dd64620d43d2180af05958b35cefdfd93fe59957260cfe76f79a1b`,
1,966,080 rows, six image IDs, 80 columns, and no duplicate native coordinates.

Within that accepted snapshot, image `DJI_20260202091128_0058` retains all
327,680 native thermal pixels. Exactly 21,047 are target-true, known,
LUHK-known, and analysis-eligible; 306,633 exterior pixels are target-false,
unknown, LUHK-unknown, and ineligible. Direct cross-checks found zero exterior
pixels incorrectly marked known, LUHK-known, or eligible.

Eligible target temperature minimum/mean/maximum are
19.1476383209 / 23.2071127685 / 25.9487247467 degC. Eligible mean Delta-T is
12.4071125777 degC using a 10.8 degC TAT3 exported ambient parameter with the
recorded provisional definition. Exact quantiles and hashes are in the JSON
manifest.

### Mutable-cache divergence

The shared persistent football-field canonical cache was replaced after the
accepted six-image run. Its current manifest contains 21,748 target pixels,
whereas the explicitly accepted run-scoped snapshot contains 21,047. The
current cache manifest SHA-256 is
`467c688c3944992c3174fc264060af8dc627ad38e730fb7b568e57259604cbdd`.

This is not used to redefine the accepted `run_20260722T055625Z` baseline.
Future regression work must select an explicit run scope and must not assume a
mutable shared cache is identical to an earlier accepted Part E bundle.

### Part E and figures

The accepted Part E evidence includes:

- six-row source/inclusion summaries;
- a 93-row deterministic sampling manifest with seed `20260715` and 8-pixel
  spatial tiles;
- 90 statistical-test rows;
- 86 effect-size rows;
- a complete spatial validation record;
- the readable QA handoff and run summary.

A representative football-field temperature PNG is nonempty, 1674 by 1069,
and linked to the accepted aggregate and spatial validation hashes. Numerical
tables, not rendered bytes, are the primary scientific gate. Current run-scoped
v0.3 Part E does not publish an XLSX artifact; the tracked legacy workbook was
therefore not selected as current accepted run evidence.

### Temporal safeguards

- Not requested: `run_20260722T064301Z` is complete with zero groups, no
  series, no peak-to-trough result, and no pixelwise result.
- Single capture: `run_20260722T055625Z` is
  `single_capture_descriptive_no_trend`; no peak-to-trough result or temporal
  figure is claimed.
- Multi-capture: `run_20260722T053855Z` has three submitted and eligible
  captures with stable location/target IDs, explicit same-location and
  comparable-ROI confirmation, and `multi_capture_observed_series` status.
  The primary temperature range is 20.3629687595 degC and provisional Delta-T
  range is 24.3629696899 degC.
- The multi-capture sampling status is `partial_observation_window`, not a full
  day. Pixelwise temporal analysis is unavailable because cross-capture
  registration was not confirmed.

## Characterization coverage

No test was added. The existing 117-test suite materially protects the named
accepted behavior, including fatal thermal validation, B0 and final Part B
review gates, the rule that automatic evidence is not final acceptance,
Save/Cancel/window-close semantics, normal and polygon routing, known/unknown
and target masks, native-grid preservation, outside-polygon ineligibility,
temperature and Delta-T provenance, schema `0.2.0`, Part E target scope and
sampling, explicit temporal opt-in, single-capture no-trend behavior,
same-location/comparable-ROI gates, and registration-gated pixelwise outputs.
Adding another test without a demonstrated gap would not be justified.

## Privacy, validation, and limitations

All committed paths are repository-relative or normalized labels. No
user-profile, SDK installation, raw-image, report, Excel, or credential-bearing
absolute path is included. No proprietary binary or report was copied.

The JSON manifest must parse, every selected path must exist, every recorded
hash must recompute, canonical schema must remain `0.2.0`, and the polygon
outside-target invariants must remain zero. Final validation also checks UTF-8,
ASCII-only generated content, absence of sensitive absolute paths, and the Git
delta.

The principal limitation is the mutable-cache divergence described above.
It is safely bounded because the accepted run-scoped aggregate, stage-state
hash, workflow records, Part E tables, and temporal records still exist and are
explicitly identified. TAT3 standalone version identity remains unavailable.
ExifTool identity is distribution-based rather than live wrapper output.

## Rollback

These paths did not exist before Phase 1:

- `docs/baseline/phase_1_accepted_baseline.md`
- `docs/baseline/phase_1_baseline_manifest.json`
- `docs/baseline/phase_1_baseline_checksums.sha256`

Rollback is to confirm these exact files are still the Phase 1-created files,
then remove only these three paths. Do not use `git reset`, `git restore`,
`git checkout`, `git clean`, or recursive directory deletion. The user-owned
untracked files must remain untouched.

Phase 1 is complete when final metadata and repository validation pass. No
Phase 2 work has begun.
