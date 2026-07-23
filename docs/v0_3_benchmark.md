# Version 0.3.2 benchmark notes

## Current interpretation

The ordinary-user launcher is:

```powershell
.\.venv\Scripts\python.exe scripts\run_user_workflow.py
```

Temporal analysis now defaults to No and is benchmarked only when an explicit
same-location, comparable-ROI group is submitted. A directory-wide capture
summary or generic source-stratified temporal figure is not evidence that a
valid temporal series was formed.

Current temporal output size and wall time scale with:

- the number of explicitly submitted groups;
- compatible captures per group;
- temperature versus ΔT compatibility;
- whether target-level figures are available;
- whether confirmed pixel registration enables pixelwise maps.

Normal single-image Part E, spectrum, spatial figures, and statistics do not
depend on opting into temporal analysis. A default-No run writes small temporal
control/validation records and no trend figures.

Spatial memory scales with one native image/source unit at a time plus the
loaded canonical frame. Temporal computation reduces target-eligible pixels to
one summary per compatible capture before cross-time comparison; it does not
construct a pixel × time matrix unless the separately gated registered
pixelwise branch is enabled.

Resume timing is only comparable when the canonical hash, sampling/statistical/
spatial implementation signatures, official LUHK dependencies, explicit
temporal plan, confirmation fields, registration declaration, and every listed
artifact still match.

Formal Part E is run-scoped in v0.3.2. A launcher invocation with run ID
`<run_id>` writes its analysis under
`outputs/runs/v0_3_user_acceptance/part_e/schema_0_2/<run_id>/`; the persistent
canonical image store is an input/cache, not a mutable "latest Part E" result.
Benchmark or acceptance evidence must therefore name both the workflow run and
its matching Part E root.

## Verified v0.3.2 real-data evidence (2026-07-22)

The ordinary workflow completed a positive three-capture football-field run at:

- workflow: `outputs/runs/v0_3_user_acceptance/workflow_runs/run_20260722T053855Z/`;
- Part E: `outputs/runs/v0_3_user_acceptance/part_e/schema_0_2/run_20260722T053855Z/`;
- temporal group: `hkust-football-field-20260202`.

All three captures were accepted independently and their EXIF times were
09:11:28, 14:08:15, and 17:04:53 `+08:00`. The temporal validation is complete,
with `temporal_series_available=true` and
`trend_status=multi_capture_observed_series`. It generated 24 spatial PNGs
(eight families for each capture) and eight spectrum PNG/PDF pairs.

| Target-level statistic | Verified value |
|---|---:|
| Maximum ROI mean | 38.792465 degC |
| Minimum ROI mean | 18.429496 degC |
| ROI-mean observed range | 20.362969 degC |
| ROI-median observed range | 20.549437 degC |
| ROI-q95 observed range | 22.708586 degC |
| Range of capture-level ROI maxima | 24.340452 degC |
| Absolute observed pixel minimum to maximum | 4.0655761 to 44.443596 degC |
| Absolute observed pixel range | 40.37802 degC |
| ROI-mean delta-T observed range | 24.36297 degC |

The ROI status is `user_confirmed_varying_roi_target_level_only`. Consequently,
the capture-level target series is available, but pixelwise temporal analysis
is unavailable with reason `cross_capture_registration_not_confirmed`. The
window is `partial_observation_window`, not a full-day sample. Delta-T uses
provisional TAT3 exported ambient parameters that are not independently
validated meteorological air temperature. These results therefore do not prove
same-pixel change, a true daily range, statistical independence of pixels, or
an exact reproduction of the earlier informal approximately +26 degC claim.

A real desktop normal-Part-C GUI lifecycle check also exercised both terminal
actions: Cancel returned a non-accepted result and did not create a successful
canonical result; Accept returned an accepted result and allowed canonical
creation. This verifies control-flow and persistence behavior, not the
scientific correctness of any particular human label.

The newer combined run
`outputs/runs/v0_3_user_acceptance/workflow_runs/run_20260722T055625Z/` has
completed six image routes successfully (five normal Part C pilots and one
football-field Part C* capture). Its matching run-scoped Part E root is
`outputs/runs/v0_3_user_acceptance/part_e/schema_0_2/run_20260722T055625Z/`.
Part E validation and `USER_RESULTS.md` are complete: the run contains exactly
the six requested image IDs, 8 spectrum PNG/PDF pairs, and 48 spatial PNG/PDF
pairs. Each pilot has 327,680 official-LUHK-known pixels; the football target
has 21,047 target/LUHK-known pixels (coverage 0.0642303467). Its single-capture
temporal result reports 19.148--25.949 degC (mean 23.207 degC, median 23.180
degC) and explicitly marks trend, peak-to-trough, and pixelwise temporal change
unavailable; no empty temporal figure is generated.

The v0.3.2 stability sampler now prepares seed-invariant spatial strata and
quotas once per analysis family. On 491,520 pixels across three deterministic
seeds, the established sampler took 4.681 s; the equivalent fast path took
1.952 s to prepare once and 0.098 s for all three seeds. Sampling-only speedup
was 47.82x, and every selected `pixel_uid` matched the established algorithm.
The benefit increases across the configured 21-seed stability run; these are
component timings on the local acceptance machine, not whole-workflow SLAs.

## Historical pre-redesign evidence

The following observations are retained as engineering history, not as the
v0.3.2 acceptance target:

- pre-v0.3.2 suite: `60 passed in 102.07s`;
- five-pilot numeric regression: `6 passed in 2.03s`;
- historical synthetic benchmark root:
  `outputs/runs/benchmark_v0_3_20260717T180758Z/`;
- 5,120 synthetic canonical rows, one normal plus three polygon images;
- canonical spatial generation: 21.01 s for four units and 64 PNG/PDF files;
- old temporal generation: 1.61 s; old resume cache hit: 0.012 s;
- historical benchmark output size: 6,779,714 bytes;
- historical formal run: 38.2 s; resume plus old formal QA: 4.8 s.

Those temporal measurements came from the superseded automatic/generic output
structure. They must not be used to claim current explicit grouping, current
per-group hottest/coolest/range tables, or current registration gating has been
benchmarked.

The real local TAT3 ambient-only parsing observation remains useful: image
0058, 2026-02-02 09:11:28, ambient/reflected 10.8°C, distance 5 m, emissivity
0.95, reported humidity 50%, zero manual measurements, and no persistent-index
mutation. It does not itself establish a temporal group or a +26°C result.

All timings are machine-specific observations, not service-level guarantees.
Real DJI SDK throughput depends on the local environment. No SDK binary, local
SDK configuration, raw imagery, or generated canonical export is committed.
