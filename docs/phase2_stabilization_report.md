# Phase 2 stabilization and acceptance report

Date: 2026-09-24 (Asia/Shanghai). This report supersedes the pre-acceptance status recorded on 2026-09-23 and incorporates the completed Mac owner acceptance, Windows owner acceptance, real scientific regression, and hosted CI evidence. It does not claim that the required Windows-to-Mac replay has occurred.

## Decision summary

- **Phase 2 code stabilization: COMPLETE.** The responsibility-based package, compatibility entry points, portable configuration, provenance contract, test safety net, and CI workflow are stabilized.
- **Mac owner acceptance: PASS.** The accepted normal fixture executed on Mac with 1 pass and no fixture skip; see [the Mac record](phase2_mac_acceptance_20260924.md).
- **Windows owner acceptance: PASS.** All available local automated checks passed after a local fixture-path correction, the real five-pilot DJI extraction was byte-identical to the accepted matrices, and real downstream results reproduced the accepted run.
- **Real scientific regression: PASS.** Five normal-route images and the immutable six-image aggregate, including the accepted 21,047-pixel polygon result, agree within existing repository tolerances.
- **Hosted CI: PASS.** GitHub Actions run [35965519283](https://github.com/VITAMINC135246/heat_index_urop/actions/runs/35965519283) created and completed both the macOS and Windows jobs successfully.
- **Cross-machine replay: BLOCKED.** A verified Windows-produced transfer pair and replay package exist, but no Mac execution host was accessible during this Windows acceptance. The required Mac result for this new artifact is therefore not inferred from the earlier accepted-fixture test.
- **Full scientific certification: BLOCKED.** Cross-machine replay is a mandatory owner gate. Shadow implementation must not begin until the packaged artifact has been replayed on Mac and its result recorded.

The compact machine-readable Windows record is [phase2_windows_acceptance_20260924.json](phase2_windows_acceptance_20260924.json).

## Source and branch boundary

- Scientific reference: `main` at `06c61b499e9c3e2f30daaeddc29fa4e98d61066e`, with accepted run `run_20260722T055625Z` and accepted aggregate SHA-256 `aa2c3fefa1dd64620d43d2180af05958b35cefdfd93fe59957260cfe76f79a1b`.
- Candidate origin: `phase-2-safety-net` at `8eb389c6fac5fb4c410282f81b5d8c5145543c94`.
- Windows fetched stabilization commit: `4c3af875c83cbda70f027a3d9619a2e617d8027f` on `stabilize/phase2-final`.
- Windows work used a separate managed worktree. The old validated checkout, its accepted output tree, `main`, and `phase-2-safety-net` were not overwritten, reset, merged, or rebased.
- Local configuration, recovered fixtures, source data, generated matrices, replay outputs, and transfer artifacts remained ignored or outside the repository. Only documentation evidence is intended for the final commit.

## Implemented stabilization

The reusable implementation lives in `heat_index/`, grouped by configuration, I/O, provenance, spatial work, classification, thermal work, analysis, visualization, reporting, and orchestration. Historical Part A–E scripts remain compatibility entry points. The [migration map](phase2_module_migration.json) and [architecture document](architecture.md) record the boundary.

`heat_index.config.paths` defaults to `<repository>/data`, accepts ignored `config/paths.local.json` or `HEAT_INDEX_DATA_ROOT`, and gives the environment override precedence. The thermal handoff is a float32 NPY plus a `thermal-artifact-v1` JSON sidecar. The reader verifies matrix hash, shape, dtype, image identity, source identity, cache version, and the five-parameter fingerprint, and rejects mismatched pairs. Historical unbound caches remain explicitly `legacy_unverified`; no scientific value or tolerance was changed during acceptance.

## Windows environment and automated checks

- OS/host: the original Windows data host; isolated Phase 2 worktree.
- Python: CPython 3.12.10; pip 26.2.1; pytest 9.1.1; Tk 8.6; `pip check` reported no broken requirements.
- DJI CLI: `dji_irp.exe` reported `APP version : V1.7`; executable SHA-256 `58e693879f8cf504738ed9f9ced8769dd0d1c81a532b0e6683f2c4f2d8654372`.
- TAT3: installed executable file version `0.2.6`. The accepted DOCX does not embed an independently verifiable application release identifier, so this file version is recorded without reinterpreting it as report provenance.
- Full data root: an ignored local path configuration resolved to the preserved Windows `data` tree. An environment override took precedence, while repository configuration paths stayed inside the checkout.

| Check | Result |
|---|---|
| Portable Windows selection, `-m "not local_integration and not windows_dji"` | **123 passed, 2 skipped, 6 deselected** in 221.47 s. The accepted-real test executed and passed. The two skips were the documented platform boundary checks, not missing science. |
| Formal synthetic Part E test | **1 passed** in 40.98 s. The preserved cross-branch result remains **97/97 exact** in [phase2_synthetic_regression_result.json](phase2_synthetic_regression_result.json). |
| Local integration marker | Initial run: 1 failed, 3 passed, 2 skipped because the isolated worktree had no local payload at its own ignored `data` path. After copying the minimum verified local inputs into that ignored path: **6 passed, 125 deselected** in 21.31 s. This was a fixture-placement correction, not a scientific change. |
| Explicit accepted-real regression | **1 passed** in 12.70 s; no missing-fixture skip. |
| `windows_dji` marker | No test is currently registered under this marker: **0 selected, 131 deselected**. This is not counted as DJI evidence; the controlled real extraction below supplies that evidence. |
| Import, CLI, path and dependency checks | Responsibility packages imported; both documented CLI `--help` commands ran; Tk and dependency checks passed. |

## Real Windows thermal extraction and TAT3 comparison

The controlled extraction wrote new outputs outside the repository and did not overwrite the accepted matrices. The actual accepted normal pilot list is `0005`, `0007`, `0008`, `0009`, and `0011`; the older prompt examples `0010` and `0016` are not in the recovered accepted manifest.

| Image | Ambient/reflected °C | New and accepted matrix SHA-256 | Matrix result | Eligible mean ΔT °C |
|---|---:|---|---|---:|
| `DJI_20260107143259_0005` | 11.0 | `814ef8337c79ab6646c7ccc3be6c1fd14b3323079a3c984bcba647d87627b80a` | exact | 3.2802686942042785 |
| `DJI_20260107143320_0007` | 10.6 | `290fa171ebc43b65e4c67170cc5cf85a1ea8993192efc5542146bdce0f6dd126` | exact | 5.711844619949988 |
| `DJI_20260107143328_0008` | 10.5 | `bbb9e0501ace98872ae797542a95e08c0abe3d1029e5775356982dc1aa8c6790` | exact | 5.5528450844140025 |
| `DJI_20260107143344_0009` | 9.9 | `afec29c5aa82911c0052d638935b4b23b9e15666aa9f89fb2bb874906da243fb` | exact | 6.205943341540115 |
| `DJI_20260107143401_0011` | 9.9 | `7d4799b4688159d7fad5c9fc282d20db9d144c93aa2ec1350a9d931ee97cd88d` | exact | 6.139098531256605 |

Every matrix was 512×640 float32 with no NaNs. Exact byte equality held, maximum and mean absolute pixel differences were 0.0 °C, and zero pixels exceeded the existing `rtol=0`, `atol=2e-6 °C` limit. Each new sidecar reported `thermal-artifact-v1`, `provenance_binding=verified`, unit `degC`, and definition `per-pixel radiometric surface temperature`. Deliberately mismatching a sidecar and changing ambient metadata without updating its fingerprint were both rejected.

The accepted TAT3 report SHA-256 is `50fa623f2650e37fea5ccf992abb40532b00ceea37ed36d3959fffb4c2a86023`. For all five images, distance 5 m, exported humidity 50%, emissivity 0.95, and image-specific ambient/reflected temperatures matched exactly at zero tolerance. The report contains zero manual point or region measurements, so no point value or location was invented: validation used all report parameters plus the exact full-matrix comparison produced with those parameters. Exported humidity remains labeled `not_used_unreliable_tat3_export` and is not treated as meteorological field RH.

## Real downstream and full-run regression

For each of the five newly extracted normal images, the pilot adapter produced 327,680 rows. Image ID, pixel coordinates, eligibility, surface-cover classes and counts, masks, ambient stratum, temperature, ΔT, and grouped results matched the accepted immutable aggregate exactly; numeric maximum absolute difference was 0.0 °C. The five images contributed 1,638,400 verified rows.

The immutable six-image aggregate contained 1,966,080 rows and included polygon image `DJI_20260202091128_0058`. Its accepted target and eligible counts were both **21,047**; the later mutable 21,748-pixel cache was excluded. A downstream replay from that aggregate reproduced 17 scientific tables/samples exactly and 56/56 common PNGs pixel-for-pixel. The 22 common source-summary columns differed only by historical float32 versus current float64 reduction, with maximum absolute difference `1.4511962440622028e-6 °C`, below the existing `2e-6 °C` limit. Spatial output completed for all six units with no exclusions; temporal output was correctly a clean skip because it was not requested.

The separate accepted polygon canonical array bundle was not recovered, so the polygon route cannot be regenerated independently from raw/canonical arrays. This does not invalidate the comparison that was possible against the frozen accepted aggregate, but it remains a documented evidence limitation rather than a fabricated golden input.

## Cross-machine replay

Windows produced a complete v1 pair for `DJI_20260107143259_0005`:

- matrix SHA-256: `814ef8337c79ab6646c7ccc3be6c1fd14b3323079a3c984bcba647d87627b80a`;
- sidecar SHA-256: `f45e95f28f33fa8af66bce6370cc254c2124f0f99760b65c82ea360364a4f57a`;
- Windows replay: 327,680 native and eligible rows, accepted cover counts, ambient 11.0 °C, verified provenance, and pandas float32-reduction mean ΔT `3.280268430709839 °C`;
- difference from the accepted float64-reduction mean `3.2802686942042785 °C`: about `2.635e-7 °C`, within the existing `1e-6 °C` grouped-mean tolerance.

The transfer archive is `phase2_windows_to_mac_cross_machine_20260924.zip`, SHA-256 `8267448505297939bfc9a7af72a18f71121f76aac4f8da78a8d9872bb0c94a35`. It contains both artifact files, internal checksums, Windows metrics, a manifest, exact instructions, and a replay script that verifies hashes and comparison rules before writing `cross_machine_mac_metrics.json`.

No Mac host was connected to this Windows task, so the archive has not been executed there. Earlier Mac accepted-fixture success proves the historical normal route, but it does not prove consumption of this new Windows sidecar. Cross-machine acceptance therefore remains **BLOCKED**, not failed and not inferred.

## Hosted CI

GitHub Actions run [35965519283](https://github.com/VITAMINC135246/heat_index_urop/actions/runs/35965519283) at source commit `4c3af875c83cbda70f027a3d9619a2e617d8027f` completed successfully:

- [Windows Python 3.12 portable and platform regression](https://github.com/VITAMINC135246/heat_index_urop/actions/runs/35965519283/job/107523116757): all setup and test steps succeeded.
- [macOS Python 3.12 portable and scientific regression](https://github.com/VITAMINC135246/heat_index_urop/actions/runs/35965519283/job/107523116923): all setup and test steps succeeded.

The jobs were actually created and executed; this is not the former `No jobs were run` condition. Proprietary DJI/TAT3 extraction remains correctly outside generic hosted runners and was performed on the real Windows host.

## Final definition-of-done gates

| Gate | Status | Evidence |
|---|---|---|
| Architecture | **PASS** | Responsibility packages, compatibility shims, migration map, architecture audit, and preserved Part A–E research language. |
| Mac acceptance | **PASS** | Mac owner acceptance plus accepted-real Step 6: 1 passed, no fixture skip. |
| Windows tests | **PASS** | Portable 123 passed; local integration 6 passed after local fixture placement; accepted-real 1 passed; dependencies and CLIs passed. |
| Synthetic regression | **PASS** | Formal test passed and preserved 97/97 cross-branch outputs are exact. |
| Real thermal regression | **PASS** | Five real DJI matrices are byte-identical to accepted references; 0.0 °C maximum difference. |
| TAT3 validation | **PASS** | All five recorded parameters per image match exactly; full accepted matrices match; no nonexistent manual point was invented. |
| Real downstream regression | **PASS** | Five normal routes exact; accepted six-image/21,047-pixel polygon aggregate replayed with 17 exact tables/samples and 56 exact PNGs. |
| Thermal provenance | **PASS** | Source/report/tool hashes and v1 parameter fingerprints verified; tampered pairs rejected; humidity limitation preserved. |
| Cross-machine replay | **BLOCKED** | Verified package prepared, but the same new Windows-produced pair has not yet run on a Mac host. |
| Hosted CI | **PASS** | Both macOS and Windows jobs ran and succeeded in Actions run 35965519283. |
| Data-root portability | **PASS** | Default and environment override behavior passed against the full preserved Windows data tree. |
| Git/data boundary | **PASS** | Historical data remained intact; recovered and generated payloads stayed ignored or outside Git; no Shadow code was added. |

## Closure decision and next action

The code baseline, independent Mac acceptance, Windows acceptance, hosted CI, and all scientifically available real regressions are complete. The missing polygon canonical bundle does not block the immutable-aggregate comparison and is not the reason certification remains open. The sole mandatory unresolved gate is execution of the packaged new Windows artifact on Mac.

**Overall Phase 2 status: NOT COMPLETE. Full scientific certification: BLOCKED.** Transfer the archive to the already accepted Mac checkout, run its replay script and `tests/test_accepted_real_regression.py`, verify the two file hashes and returned metrics, and append the Mac result. If that gate passes, freeze/tag the Phase 2 baseline and create a separate Shadow research branch from that certified commit. Do not implement Shadow on the stabilization branch.
