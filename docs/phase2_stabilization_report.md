# Phase 2 stabilization report

Date: 2026-09-23 (Asia/Hong_Kong). This report records the implemented stabilization and the evidence still needed for owner acceptance. It does not replace the earlier [Mac architecture/regression audit](mac_phase2_architecture_regression_audit.md).

## Source and branch boundary

- Scientific reference: `main` at `06c61b499e9c3e2f30daaeddc29fa4e98d61066e`; its accepted production-code ancestor and run-scoped evidence are recorded in the [Phase 1 baseline](baseline/phase_1_accepted_baseline.md).
- Candidate starting tip: `phase-2-safety-net` at `8eb389c6fac5fb4c410282f81b5d8c5145543c94`.
- Stabilization branch: `stabilize/phase2-final`, created from that candidate tip. Audit checkpoint `6898eba`, source migration checkpoint `e5b1c9f`, and test/CI checkpoint `35eebed` are separate commits. The commit containing this report is the final branch tip; obtain its full ID with `git rev-parse HEAD`.
- `main` and `phase-2-safety-net` were left intact. No push, merge, force-push, or history rewrite was performed. No tracked `data/` or `outputs/` file changed from the Phase 2 starting tip.

## What changed

The reusable Python implementation now lives in `heat_index/`, grouped by configuration, I/O, provenance, spatial work, classification, thermal work, analysis, visualization, reporting, and orchestration. Sixty-two former implementation files in `scripts/` and `scripts/workflow/` now act as thin compatibility command/import shims. [The migration map](phase2_module_migration.json) lists every old-to-new file. The old A–E names remain valid research and CLI language; internal imports and orchestration use responsibility modules. The historical dynamic loader stays only as compatibility for old callers/tests; active package modules do not use it. Shared data-path resolution, table-value coercion, and file hashing remove repeated core helpers without changing scientific formulas.

`heat_index.config.paths` defaults to `<repository>/data`, accepts ignored `config/paths.local.json` or `HEAT_INDEX_DATA_ROOT` (environment wins), and maps only logical `data/...` paths to a physical override. Source modules no longer embed local Windows SDK/ExifTool drive paths or Windows font paths. Real DJI extraction fails deliberately outside Windows; the Mac can load precomputed artifacts. `.gitignore` now keeps raw, external, intermediate, large derived data and the optional accepted-real payload local. All 45 previously tracked small research data files remain tracked; none was deleted or rewritten.

The thermal handoff now has a versioned float32 NPY matrix and JSON provenance sidecar in [artifact.py](../heat_index/thermal/artifact.py). Its reader verifies SHA-256, shape/dtype, image ID, source-image identity/hash when supplied, cache version, and a fingerprint of all five available radiometric settings. A mismatched or incomplete pair fails closed. The pilot adapter recovers historical temperature definition/unit and TAT3 parameter/ambient source from tracked Part D rows; a historical NPY without a verifiable sidecar remains explicitly `legacy_unverified`. Explicit new TAT3 inputs bypass an old pilot cache, and SDK output is written as a run-scoped bound artifact. Unknown parameters are not inferred.

The tracked pilot parameter CSV and Part D summary preserve five per-image rows: distance 5 m, relative humidity 50%, emissivity 0.95, and the image-specific ambient/reflected settings shown there. Git history traces the TAT3 parameter workflow to `3a426e0`; it contains old QA outputs but no missing actual thermal matrices, per-image metadata JSON, raw TAT3 DOCX exports, or accepted run snapshots. Those remain Windows recovery tasks. The report must not be read as proof that the copied Mac repository contains the complete original provenance.

## Verification performed here

| Check | Result and limit |
|---|---|
| Mac CI-equivalent pytest, CPython 3.12.13 / pytest 9.1.1, `-m 'not local_integration and not windows_dji'` | **123 passed, 2 skipped, 6 deselected in 62.45 s**. One skip is the absent accepted-real fixture; one is Windows Tcl bootstrap. The six deselections require local ignored inputs. |
| Final synthetic formal Part E replay against the preserved `main` run | **97/97 exact**: 24 NPY arrays, 22 CSV tables, 10 Parquet tables, and 41 PNG pixel arrays. [Machine-readable comparison](phase2_synthetic_regression_result.json) has `all_equal=true`, no differences. This fixture is synthetic, not accepted raw-pilot certification. |
| Thermal/path tests and compatibility | New artifact tests cover metadata tampering, wrong source/parameter, paired transfer, legacy labeling, explicit TAT3 cache bypass, and Mac SDK boundary. Old script entry points and formal Part E subprocess stages executed in the suite. |
| Static checks | `compileall` and `git diff --check` passed; workflow YAML parses into two jobs. No repository scientific data/output file changed. |
| CI hosted execution | **Not run**. The invalid job-level `runner.temp` expression was removed; Mac and Windows jobs now select portable tests, with real proprietary DJI integration left for the Windows workstation. Since this branch was not pushed, GitHub has not demonstrated that the jobs schedule and finish. |

The optional [accepted-real fixture](../tests/fixtures/accepted_real/manifest.template.json) requires an active ignored `manifest.json` and the original `main` snapshots; an absent manifest skips, while an incomplete active fixture fails. It currently replays the normal pilot route only. The accepted polygon route and full six-image run require their original Windows artifacts and separate owner comparison. No golden scientific result was generated from the Phase 2 candidate.

## Definition-of-done gates

| Gate | Status | Evidence | Owner action needed |
|---|---|---|---|
| 1 — Architecture | **PASS** | Responsibility packages, old-entry compatibility, migration map and [architecture](architecture.md); central path/coercion/hash helpers. | Review the module boundaries during Mac acceptance. |
| 2 — Tests and CI | **PENDING** | Local Mac selection passed; workflow has Mac/Windows jobs and parses. Hosted jobs have not started from this unpushed branch. | After an authorized push or PR, confirm both GitHub jobs actually schedule and complete. |
| 3 — Synthetic scientific regression | **PASS** | Exact comparison of 97 scientific/figure outputs to `main`. | Rerun the documented Mac command on the final commit. |
| 4 — Real accepted scientific regression | **BLOCKED** | The original accepted thermal NPY, TAT3 reports, raw pairs and frozen canonical/run artifacts are absent here; optional real test skips. Normal-only fixture cannot certify polygon/six-image behavior. | Recover and hash the selected Windows `main` artifacts; run normal and full-run comparisons. |
| 5 — Thermal provenance | **PASS for code contract** | TAT3 values/definitions recovered from tracked summaries; versioned sidecar verifies matrix/source/parameter binding; legacy unbound cache is labeled; mismatch tests pass. | Supply original matrices/reports to confirm historical file-level provenance on Windows. |
| 6 — Data portability | **PASS** | Default local `data/`, one override resolver and tests; inappropriate absolute machine paths removed from shared source. | Check the original full data tree through `HEAT_INDEX_DATA_ROOT` on Windows. |
| 7 — Git/data boundary | **PASS** | `.gitignore` distinguishes large local payloads, optional recovered fixture, and intentionally tracked small files; 45 tracked data files retained unchanged. | Review any selected recovered fixture before adding it to Git. |
| 8 — Mac downstream readiness | **PASS for local development** | Portable suite and formal Part E synthetic workflow pass without DJI. | Independently run [Mac acceptance](phase2_owner_acceptance.md). |
| 9 — Windows DJI readiness | **PASS for procedure; execution pending** | SDK calls are Windows-only; [Windows acceptance](phase2_owner_acceptance.md) specifies extraction, TAT3 comparison, and cross-machine transfer. | Perform the genuine Windows extraction and acceptance. |
| 10 — Shadow integration readiness | **PASS** | [Shadow roadmap](post_phase2_shadow_roadmap.md) defines independent state/validity, future integration points and research gates. No Shadow algorithm was added. | Do not start feature integration until the remaining Phase 2 acceptance gates close. |

The remaining blockers are external evidence and hosted execution, not a failing local test. The minimum recovery list with exact destinations and Git treatment is in [windows_artifact_recovery.md](windows_artifact_recovery.md). In particular, retrieve the accepted run `run_20260722T055625Z`, the selected normal/polygon raw images and frozen canonical outputs, five original Part D matrices with their metadata, and the source TAT3 DOCX reports. Do not substitute the later shared polygon cache, which has 21,748 target pixels, for the 21,047-pixel accepted snapshot.

## Decision and next actions

**Overall Phase 2 status: NOT COMPLETE.** The implementation and local code safety net are stabilized, but Gate 2 lacks hosted CI execution and Gate 4 lacks real accepted evidence. This is a deliberately narrower claim than full scientific certification. The exact owner sequence is: verify the final branch commit and run the [Mac acceptance procedure](phase2_owner_acceptance.md); recover only the selected original Windows artifacts using the [recovery checklist](windows_artifact_recovery.md); run the Windows extraction, original-run comparison and cross-machine artifact replay; then, after a push is separately authorized, verify both hosted CI jobs. Record the resulting hashes, outputs and review decisions before promoting the development baseline or starting the Shadow research branch.

| Required final status | Value |
|---|---|
| PHASE 2 CODE STABILIZATION | **COMPLETE** |
| MAC ACCEPTANCE | **NOT YET RUN** (independent owner procedure; local developer tests passed) |
| WINDOWS ACCEPTANCE | **NOT YET RUN** |
| FULL SCIENTIFIC CERTIFICATION | **BLOCKED** |
| READY TO START SHADOW RESEARCH WORKSTREAM | **NO** |
