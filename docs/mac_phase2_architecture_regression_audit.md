# macOS / Phase 2 architecture and scientific regression audit

Audit date: 2026-09-23 (Asia/Hong_Kong). Repository: [VITAMINC135246/heat_index_urop](https://github.com/VITAMINC135246/heat_index_urop).

## 1. Executive summary

**Recommend a dedicated stabilization branch based on `phase-2-safety-net`, after this report is reviewed; do not begin Shadow feature work yet. Keep `main` as the scientific reference.** This is **Case B, partially healthy**, with an important qualification: Phase 2 is not a large architectural refactor. Most responsibility-oriented modules already exist on `main`. Its useful additions are an environment/CI boundary, a shared pilot temperature entrance, and desktop workflow conveniences; the shared temperature entrance also introduces an observed provenance regression and an unsafe artifact-reuse risk.

Confidence is **high in the scope of the branch comparison and identified blockers, moderate in the stabilization recommendation, and insufficient to certify complete real-data scientific equivalence**. No evidence justifies discarding Phase 2 or rebuilding the shared architecture. Conversely, neither cleaner naming nor passing synthetic tests would certify it.

Principal evidence:

- Phase 2 is three commits ahead, zero behind `main`; 17 changed files, 1,172 insertions and 17 deletions, plus a binary report. There are no removed scientific modules.
- All **289 common tracked data, configuration, and output files are byte-identical** between branches. This is artifact preservation, not proof of regeneration.
- Regenerating native-grid LUHK from tracked spatial tables gives exact cross-branch results for all five pilots. The normal representative's LUHK and cover counts exactly match the accepted Phase 1 manifest.
- A separately executed synthetic formal Part E replay gives exact equality for **24 arrays, 31 tables, one empty table, and 41 PNG pixel arrays**, including a 36,864-row, 80-column aggregate. This does not replay raw imagery or the new pilot temperature entrance.
- A controlled pilot-entrance probe finds unchanged numerical pixels but a **lost temperature definition and changed unit string** in Phase 2's runtime route. These fields participate in downstream source stratification.
- Current Phase 2's CI-selected tests on macOS with pinned packages and a normalized temporary path: **113 passed, 1 failed, 1 skipped, 6 deselected**. The remaining failure is a non-hermetic Windows launcher test, not a measured temperature regression.
- GitHub rejects the workflow before creating jobs: invalid `runner.temp` expression in job-level `env`.
- Accepted real thermal matrices, raw V/T images, TAT3 reports and accepted run snapshots are missing locally. Full real-data equivalence remains unverified.
- Separate cover and shadow layers already exist on both branches. All five tracked pilot thermal shadow masks are zero everywhere. Real shaded/unshaded validation is missing.

Only audit documentation/evidence was added. No scientific source, test, configuration, algorithm, workflow, branch tip, or accepted artifact was edited. No development branch was created, merged, renamed, deleted or pushed.

## 2. Repository and environment state

### Discovery and scope

The initial working directory was `/Volumes/My Passport for Mac/Projects/HEAT_INDEX_ESTIMATION_UROP_2627FALL`. It was **empty**, with no `.git`, source or data. Git initially returned “not a git repository.” The saved alternative project path `/Users/vitaminc-macbook/heat_index_urop` did not exist. The connected GitHub account contained one matching repository, with both requested branches. A fresh clone was inspected in `/tmp/heat-index-baseline-audit-20260923`, then copied into the empty selected workspace. This report therefore audits the remote repository, not an undiscovered Windows working copy or uncommitted research data.

The workspace now holds `main`; the initial clone and both detached audit worktrees were clean before testing. There were no user modifications to preserve in the initially empty workspace. Final workspace changes should consist only of this report and its evidence directory. No `AGENTS.md` was found in the repository tree.

| Item | Observed state |
|---|---|
| Local branch | `main`, tracking `origin/main` |
| Remote | `origin`: `https://github.com/VITAMINC135246/heat_index_urop.git`, fetch and push |
| Remote branch inventory | `origin/main`, `origin/phase-2-safety-net`; symbolic `origin/HEAD -> origin/main` |
| `main` HEAD | `06c61b499e9c3e2f30daaeddc29fa4e98d61066e` |
| Phase 2 HEAD | `8eb389c6fac5fb4c410282f81b5d8c5145543c94` |
| Divergence | `git rev-list --left-right --count main...origin/phase-2-safety-net` → `0 3` |
| Accepted production-code reference | `953e97408689736296b4f05198932f54cfea667f`, July 23, merge v0.3.2 |
| Prior checkpoint tag | `pre-e2e-validation-2026-07-15` → `90a10d605d19bb3221dfca4353c8df9111f1dc5a`; explicitly **pre-validation** |
| Main's latest change | July 24, `06c61b4`: three baseline documentation files only |
| Host | macOS Darwin 24.6.0, Apple Silicon arm64 |
| Default Python | CPython 3.12.5 via pyenv; no `_tkinter` |
| Controlled audit Python | CPython 3.12.13, conda-forge, isolated `/tmp/heat-index-audit-py312-tk`, Tk 8.6 |
| Dependency method | unpinned `requirements.txt`; Phase 2 adds `constraints/windows-py312-reference.txt`; no pyproject/setup package or hash lock |
| Intended Python | documented 3.12, accepted patch 3.12.13; no machine-enforced `requires-python` |
| Tests | pytest collecting unittest-style test classes; 23 test modules, temporary/synthetic fixtures inline |
| CI | none on `main`; one GitHub Actions YAML on Phase 2 |

Reference pins installed successfully on this Apple Silicon host. `pip check` passed. Native versions in that environment: GDAL 3.12.1, PROJ 9.5.1, GEOS 3.13.1, OpenCV 5.0.0. Matching version strings do not guarantee identical Windows native binaries. Installed inventories are in [the evidence directory](audit_evidence/mac_phase2_20260923/).

### Useful repository tree

```text
config/                  13 workflow, acceptance and Part D/E JSON files
constraints/             Phase 2 Windows/Python reference pins only
scripts/
  01_...05_*.py           Part A pairing, metadata, footprints, grids, land use
  part_b/                3 alignment/review scripts
  part_c/                3 segmentation, annotation and mask scripts
  part_d/                3 extraction, thermal QA and TAT3 parsing scripts
  part_e/                17 pipeline/statistics/plot/workbook/support files
  workflow/              24 domain, model, adapter and orchestration modules
  deprecated/            retained historical scripts plus README
  run_*.py               user, analysis, TAT3 and temporal entry points
  workflow_gui.py        Phase 2 desktop wrapper
  build_urop_report_*.py Phase 2 report generator
  table_io.py, camera_profiles.py, benchmark_*.py
tests/                   23 test modules plus __init__.py
 docs/                   research, schema, acceptance and benchmark documents
   baseline/             accepted manifest, narrative and checksums
 data/                   45 tracked files: mappings, annotations, metadata, spatial tables
 outputs/                tracked masks, summaries, figures, workbooks, geodata
 .github/workflows/      Phase 2 scientific-regression.yml
 launch_workflow_gui.cmd Phase 2 Windows launcher
```

Large raw/source datasets and accepted runtime caches are absent from this clean clone.

## 3. `main` architecture assessment

`main` is a **hybrid of historical research stages and responsibility-oriented modules**, not an entirely unstructured script collection. Keep the research-stage entry points because they are documented and connected to accepted workflows.

| Responsibility | Actual implementation and boundary |
|---|---|
| Workflow/configuration | `scripts/run_user_workflow.py` constructs CLI commands; `run_analysis.py` loads workflow JSON, routes review, resolves temperatures, writes canonical results and invokes Part E/temporal work. Config resolves relative to repository root. |
| Pairing and validation | Part A numbered scripts; `workflow/input_validation.py`, `capture_time.py`, `camera_profiles.py`; explicit filename/time warnings and fatal thermal checks. |
| Spatial/alignment | `workflow/part_b_correspondence.py`, `part_b_adapter.py`, `part_b_review.py`; adapter calls preserved `part_b/b05_refine_vt_alignment.py` and `b06_generate_alignment_refinement_review.py`. Automatic alignment is candidate evidence; review controls acceptance. |
| Classification/masks | `part_c_adapter.py`, `part_c_review_gui.py`, `polygon_annotation.py`; legacy SLIC and reviewed mask construction reused through dynamic loading. Cover, known, target and shadow are distinct arrays. |
| Land-use context | `workflow/luhk_context.py` shared by adapters and legacy Part E; official/user-supplied provenance is separate from cover. Native LUHK remains approximate map context, not improved georegistration from image-space alignment. |
| Thermal | `workflow/temperature_extraction.py`: `TemperatureResult`, NPY loader, parameter readers, QA and DJI command/runner. Legacy `part_d/01_extract_temperature_matrices.py` retains its own discovery, command and QA routines. |
| Data I/O | `table_io.py` for XLSX; `canonical_result.py` for NPY/Parquet/manifest; `part_e_pixel_common.py` for legacy/configured tables; direct pandas/NumPy reads throughout. No single configurable data-root boundary. |
| Analysis | `part_e_adapter.py` normalizes/aggregates canonical pixels; `part_e_runner.py` invokes preserved numbered stages; `temporal_analysis.py` manages capture-level comparisons and gates. |
| Visualization | Part B/C review figures and GUI; Part E numbered spectrum/spatial scripts; temporal module also writes figures and reports. |
| Provenance | `models.py` schema/typed records, `result_index.py` source/config hashes and cache checks, canonical artifact hashes, run-scoped bundles, Part E method fingerprints; accepted baseline JSON and checksums. |
| Tests/docs | Version-named tests mix unit, integration and saved-artifact assertions. Documentation retains Parts A–E and v0.1–v0.3.2 history and acceptance policies. |

Strengths: canonical native thermal coordinates, explicit review/eligibility masks, independent surface cover and LUHK provenance, atomic artifact writes, cache fingerprints, source-aware statistics, and temporal safeguards already exist. The accepted baseline records 117 passing Windows tests and six-image/run-scoped acceptance; this audit treats those as historical records, not newly reproduced outcomes.

Concrete debt shared with Phase 2:

- `run_analysis.py` is 1,266 lines, combining CLI, review interaction, data access, temperature choice, persistence, reporting and orchestration. `temporal_analysis.py` is 2,682 lines. Legacy Part C preparation is 1,198 lines; alignment 1,083; extraction 1,063. They are broad modules, but size alone does not justify a rewrite.
- `part_b_adapter.py:14` mutates `sys.path` to import stage scripts. `legacy_loader.py:15` caches dynamic imports, mutates `sys.path` and `sys.modules`, and Part C/TAT3 adapters depend on it. This preserves algorithms but leaves import order and aliasing risks.
- Dependency direction crosses stage/domain boundaries: `part_e_runner -> numbered Part E -> part_e_pixel_common -> workflow.luhk_context`; `part_c_adapter -> legacy_loader -> numbered Part C`. Static AST inspection found **no cycles among resolved project-module imports**, but does not rule out dynamic-loader or short-name alias cycles.
- Exact duplicated function bodies include `resolve_project_path` in seven B/C/D files; `as_float`/`as_int`; three Part E `sha256_file` implementations; two `_atomic_text` helpers; thumbnail/export helpers. DJI command assembly exists twice. These are specific consolidation candidates after characterization.
- Import-time `PROJECT_ROOT`, fixed pilot table locations, globally cached legacy modules, explicit Matplotlib backend setup and environment modifications are hidden process state. Most paths are anchored to `__file__`, which is safer than cwd, but prevents moving all data through one setting.
- Cache identities include absolute paths (`part_e_runner._dependency_hash`, `result_index.source_hashes`); relocating a checkout can invalidate otherwise unchanged results. That is a reproducibility/portability concern, not proof of numerical drift.

## 4. Phase 2 architecture assessment and reconstruction

Phase 2 preserves the above architecture. It has 67 Python source files versus 65 on `main`; the workflow package still has 24 modules. No package migration or domain-layer rewrite occurred on this branch.

| Commit | What actually happened | Implication |
|---|---|---|
| `5bc4b68`, Aug 22 | Added reference constraints, workflow, Phase 2 guide; marked six controlled-local tests | Production code unchanged. This explains the historical 117 − 6 = 111 selected tests. |
| `9d69b6b`, Aug 22 | Added 307-line report generator and 2.82 MB DOCX | Research reporting, not pipeline architecture; Windows fonts and undeclared `python-docx` dependency. |
| `8eb389c`, Aug 23 | Added 442-line Tk GUI/Windows launcher, resume Part C option, console Python selection, common pilot thermal route, runtime result input to pilot adapter, hard-coded ExifTool fallback, four tests | Useful usability and temperature-entry consolidation; also scientific metadata/cache and portability risks. |

`docs/phase_2_environment_and_ci.md` accurately describes the **first** Phase 2 commit, but its “does not change production code” scope no longer describes HEAD. It contains no completed Mac-port or domain-refactor plan. The Git history and accepted Phase 1 inventory are a better source of status than that stale scope statement.

The architectural gain is **narrow**: pilot and general routes can now call `temperature_for_group`, and `adapt_pilot_image` can accept a `TemperatureResult`. This is a useful seam for a portable artifact provider. However, the orchestrator also writes a legacy matrix itself, and the adapter still requires fixed pilot summary tables. That is incomplete isolation, not a finished thermal-provider architecture.

## 5. Branch diff and concrete technical-debt comparison

| Area | `main` | Phase 2 HEAD |
|---|---|---|
| Scientific modules/configs | Accepted reference implementation | Core spatial/classification/Part E/temporal modules and all configs unchanged |
| Pilot temperature entrance | Adapter loads accepted matrix directly | Common resolver selects override, legacy matrix or SDK, then passes runtime result |
| Temperature persistence | Established Part D artifact path | `run_analysis.py:853–869` writes missing matrix into legacy Part D path without a companion updated extraction record |
| Scientific metadata | Adapter explicitly records temperature definition and legacy units | Runtime metadata takes precedence; observed blank definition and changed unit label |
| Dependency management | Unpinned requirements | Same requirements plus tested reference constraints; no artifact hashes or Mac CI |
| CI | None | Useful intent but invalid YAML expression prevents all jobs |
| UI | CLI plus existing Part B/C/polygon review GUIs | Adds desktop wrapper; result-opening uses Linux `xdg-open` on every non-Windows host |
| Test inventory | 117 collected | 121 collected; six local-only markers; new launcher test is machine-dependent |
| Data boundary | Repository-root paths and partial ignores | Unchanged, including missing ignores for v0.3 canonical outputs/index |
| Shadow support | Separate masks/columns/review buttons/Part E analysis | Identical support; no added shadow algorithm |

No basis exists for “Phase 2 is a cleaner complete refactor.” There is a small useful continuation whose outstanding defects are localized enough to stabilize.

## 6. Test suite execution and failure classification

Tests ran in disposable checkouts/worktrees; no test-generated payloads were substituted for missing real data. Full suites were run before choosing exclusions. No test or scientific code was edited to obtain these results.

Environments:

- **A:** Python 3.12.5, fresh venv, unconstrained `requirements.txt`; e.g. NumPy 2.5.3, pandas 3.0.6, SciPy 1.18.1, Matplotlib 3.11.2, statsmodels 0.15.0. No Tk. Useful environment-discovery result, not the accepted dependency reference.
- **B:** Python 3.12.13 + Tk 8.6; pip 26.1.2; `pip install -r requirements.txt -c constraints/windows-py312-reference.txt`. Package versions satisfy those pins on macOS. Platform-specific transitive packages need not all be installed merely because a constraint mentions them. Both environments passed `pip check`.

Common command in each root:

```sh
PYTHONDONTWRITEBYTECODE=1 MPLBACKEND=Agg MPLCONFIGDIR=<unique-temp-mpl> \
  <environment>/bin/python -m pytest -ra -p no:cacheprovider \
  --basetemp <unique-pytest-temp> --junitxml=<evidence-file>
```

| Run / environment | Passed | Failed | Errors | Skipped | Deselected | Seconds |
|---|---:|---:|---:|---:|---:|---:|
| `main`, full, A | 109 | 3 | 2 | 3 | 0 | 108.73 |
| Phase 2, full attempt, A | 0 | 0 | 1 collection | 0 | 0 | 27.88 |
| `main`, full, B | 109 | 3 | 2 | 3 | 0 | 114.94 |
| Phase 2, full, B | 112 | 4 | 2 | 3 | 0 | 114.96 |
| Initial Phase 2 `5bc4b68`, B, `-m 'not local_integration'` | 109 | 1 | 0 | 1 | 6 | 114.87 |
| Current Phase 2, B, same marker selection, `TMPDIR=/private/tmp` | 113 | 1 | 0 | 1 | 6 | 55.16 |
| `main`, isolated path assertion, B, `TMPDIR=/private/tmp` | 1 | 0 | 0 | 0 | 0 | 0.66 |

The latest CI-selected command was the common command above plus `TMPDIR=/private/tmp` and `-m 'not local_integration'`. Full log filenames identify branch/environment; [test-results.json](audit_evidence/mac_phase2_20260923/test-results.json) records detailed failing/skipped nodes. JUnit counts include unittest subtests and therefore differ from collected pytest item totals; use the pytest terminal summaries for the table above.

| Failure/skip | Classification and evidence |
|---|---|
| Pilot adapter test and temperature numeric test fail; two LUHK pilot setup errors | **Missing local artifacts:** first missing `data/processed/part_d/temperature_matrices/DJI_20260107143259_0005_temperature_celsius.npy`. Not measured scientific drift. |
| Real Part E Parquet and named TAT3-report tests skip | **Missing local data**, not inherently Windows-only. They can run on Mac with appropriate artifacts. |
| Tk import stops Phase 2 collection in A | **Environment/import coupling:** `test_v03_user_workflow.py` imports `workflow_gui`, which imports Tk unconditionally. Resolved by selecting a Tk-enabled interpreter, without changing code. |
| `test_dataset_discovery_pairs_unique_adjacent_dji_timestamps` | **Portable test defect:** returned resolved `/private/var/...` path is compared against unresolved `/var/...`. Pairing itself returns the correct image. Isolated test passes with a canonical temp root; normalize expected paths in a future test fix. |
| `test_gui_pythonw_launcher_uses_console_python_for_child_logs` | **New non-hermetic test:** patches shared `os.name` to `nt`, causing `pathlib.WindowsPath` on Mac and `NotImplementedError`; it also assumes `<repo>/.venv/Scripts/python.exe` exists without creating/mocking that file. Windows CI's setup-python is not a repo-local `.venv` either. |
| Windows Tcl bootstrap test skips | **Intentional platform-specific check.** Do not force it to run on macOS. |

No warnings section appeared in the completed pytest summaries. The separate formal replays emitted the same Matplotlib tight-layout warning at `04_generate_pixel_delta_t_spectra.py:607`. Exact PNG equality does not certify publication layout quality. No interactive GUI, Excel automation or genuine SDK execution was attempted.

The historical **111 passed, 6 deselected** is consistent with the first safety-net commit: 117 existing items minus six local integrations. This audit did not reproduce that exact Windows result. On Mac the original selected suite has one intentionally skipped Windows check and one path assertion failure; the latter was independently resolved by temp-path normalization. Phase 2 HEAD adds four items, so 111 is no longer its full selected count. A literal historical console log was not recovered from tracked history; the 117 baseline and six-marker boundary are documented evidence.

## 7. Scientific regression methodology and tolerances

Separate five kinds of evidence:

1. **Reference identity:** `953e974` production code is unchanged by `06c61b4`; validate the two baseline-record SHA-256 entries, which both pass.
2. **Preserved artifacts:** compare Git blob identities for every common tracked config/data/output. Inspect NPY shape, dtype and values. Identity proves preservation only.
3. **Recomputed real spatial inputs:** run `load_native_luhk_result` on each branch using tracked grid/footprint tables for the five pilot IDs; compare native labels/counts, and compare the representative's counts to the accepted manifest.
4. **Generated synthetic output parity:** execute the existing `FormalPartEV02IntegrationTests._write_results` fixture and actual `run_formal_part_e` on each branch, retaining outputs. Four 96×96 cases cover normal, polygon, absent ambient, and zero eligible cover. Compare every NPY, CSV, Parquet and PNG encountered. This exercises canonical aggregation, sampling, grouped statistics, spectra and spatial figures, without proprietary tools.
5. **Changed-entrance characterization:** use an explicitly synthetic 16×20 matrix (`linspace(-10, 40, 320, float32)`) and cropped tracked masks in an audit-only fixture root. Compare `main` pilot adaptation, Phase 2 legacy adaptation, and Phase 2 adaptation of `legacy_temperature()`'s `TemperatureResult`. This detects changed metadata independently of actual DJI output.

Tolerances are not interchangeable:

| Comparison | Policy and reason |
|---|---|
| Git records, categorical IDs, masks, counts, shape/dtype, metadata strings | Exact identity/equality; no scientific reason to soften discrete differences. |
| Same-environment generated arrays/tables | **Zero numerical tolerance** in this audit; exact DataFrame/array equality, colocated NaNs treated as equal. Shared code/data/versions permit this stronger check. |
| Frozen reviewed cover masks | Existing test uses exact SHA-256 for all five thermal-grid masks. |
| Existing real thermal numeric baseline | `rtol=0`, `atol=2e-6 °C` for min/max/mean/q99/ambient. This is inherited, not newly loosened. It is around one float32 ULP at 16–32°C (and below one ULP above 32°C), vastly below measurement precision. Full justification for cross-platform reductions still requires replaying the missing matrices. Do not enlarge it if it fails. |
| Existing saved ΔT/group means | `assertAlmostEqual(..., places=8)`, approximately half of `1e-8 °C` under decimal rounding. Appropriate for the fixed stored decimal summaries; not a blanket SDK or scientific-uncertainty tolerance. |
| PNGs | Decoded pixel equality observed for this synthetic run. Normally numerical figure inputs and dimensions are the primary gate, since fonts/renderers may vary across platforms. PDF metadata/bytes were not used as a scientific gate. |
| Future real artifact replay | Prefer exact array identity for reuse of the same float32 NPY payload. Compare float64 aggregates first exactly, then investigate any reduction differences; approve an operation/dtype-specific bound before use. No untested blanket tolerance is authorized here. |

Scripts and structured results are under `docs/audit_evidence/mac_phase2_20260923/`. `setup_controlled_pilot.py` clearly labels its output synthetic; never place it in a real project's Part D directory. `replay_probe.py BRANCH_ROOT OUTPUT_DIRECTORY formal|pilot` reproduces the retained probes; `tracked_spatial_probe.py BRANCH_ROOT OUTPUT_JSON` reproduces the tracked-spatial check. Temporary worktree/probe paths appear in logs to make each command traceable.

## 8. Scientific regression results

| Requested scientific dimension | Evidence/result | Limit |
|---|---|---|
| Selected image IDs | Five pilot IDs and six-image accepted scope preserved; tracked artifact contract tests pass | Raw dataset discovery not replayed on absent originals |
| V/T pairing | Tracked pair table identical; synthetic discovery tests run; one path-spelling assertion classified above | Original image content/timestamps not re-extracted |
| Dimensions | All five tracked thermal cover/shadow masks are 512×640; synthetic canonical grids retain native shape | Raw JPEG dimensions unverified locally |
| ROI/alignment | Saved reviewed evidence/summary bytes identical; synthetic B0/full-B/manual gate tests pass | No original-image re-alignment/review replay |
| Cover masks | Five existing frozen SHA baselines pass; all 20 tracked cover/shadow NPY files preserved | No re-segmentation from real visible originals |
| LUHK/context | Five recomputed spatial results identical; representative counts match accepted record exactly | Approximate north-up footprint context remains approximate |
| Thermal matrices | Synthetic matrices/NPY handoff identical where compared | Five actual matrices and licensed extraction absent |
| Ambient | Tracked values 11.0, 10.6, 10.5, 9.9, 9.9°C preserved; synthetic missing-ambient behavior identical | These are provisional TAT3 parameters, not independently validated air temperature |
| Inclusion/acceptance | Synthetic target/known/QA gates and all compared outputs identical | Accepted six-image snapshot absent |
| Pixel ΔT | Exact in synthetic replay and controlled pilot probe; saved means pass existing assertions | No new real-pixel ΔT recomputation |
| Row counts | Saved pilot summaries preserve 1,638,400 rows; synthetic aggregate 36,864 rows/80 columns | Actual legacy Parquet and accepted 1,966,080-row aggregate absent |
| Cover assignments | Tracked mask identity plus regenerated counts; synthetic canonical classes exact | No fresh manual classification acceptance |
| Per-image/group stats | Saved baseline assertions pass; all 31 generated tables compare exactly | Saved real summaries are read, not regenerated |
| Figures/numerical inputs | 41 synthetic PNGs exactly equal; spectra, spatial and table outputs generated | Historical real figures preserved only; no real rerender or PDF byte gate |
| Temporal safeguards | Existing synthetic single/multi-capture and registration-gate tests pass | Accepted real three-capture temporal bundle absent |
| New Phase 2 pilot route | Numerical columns exact in controlled probe; **metadata regression confirmed** | SDK fallback and persistence lifecycle need separate characterization |

Normal representative `DJI_20260107143259_0005`: LUHK counts recomputed as 222,592 `gic_open_space`, 200 `other_urban_built_up`, 104,888 `woodland_shrubland_grassland_wetland`, all 327,680 known. Cover counts: IDs 1/2/4/5 → 30,014 / 20,871 / 262,255 / 14,540. These exactly match `docs/baseline/phase_1_baseline_manifest.json`.

The formal synthetic aggregate has 26,896 analysis-eligible pixels and 27,648 finite ΔT values. Missing ambient can leave temperature-analysis eligibility true while ΔT is unavailable; downstream ΔT gates are tested separately. Do not confuse finite ΔT outside a polygon with eligibility to include it.

**Confirmed Phase 2 regression:** `run_analysis.legacy_temperature` calls `load_temperature_override` with only ambient metadata; that loader supplies an empty `temperature_definition` and `degC` default. Phase 2 passes that runtime record to `pilot_adapter`, replacing the explicit legacy definition (`per-pixel radiometric surface temperature`) and legacy unit (`Celsius interpreted from SDK measure output`). Both changed columns are recorded in `pilot-probe-results.json`; no other pixel columns differ in that probe. `part_e_runner.SOURCE_COLUMNS` and `part_e_adapter` use these fields, so this is a scientific-provenance/stratification regression, even though no numeric change was observed.

**Static lifecycle risk, not a claimed reproduced real numerical failure:** Phase 2 saves a newly resolved matrix into the legacy Part D path if absent, but does not save corresponding updated extraction/ambient/provenance metadata. A later `legacy_temperature` read trusts the old tracked CSV row. Different supplied radiometric/ambient settings can therefore become detached from the persisted matrix on a later run. The adapter also labels ambient source as TAT3 even when a supplied runtime override may have a different source. These paths need controlled lifecycle tests before accepted data are processed.

Overall verdict: **partial scientific preservation demonstrated; full preservation not established; one metadata regression established.**

## 9. Missing coverage and the smallest useful fixture set

The manifest references 29 artifact paths encountered by the inventory walker: 13 exist and 16 do not. More payload paths are described indirectly; this count is not an exhaustive input manifest. The accepted run is `run_20260722T055625Z`, not whichever mutable canonical cache happens to exist. The accepted football polygon contains **21,047** eligible pixels; a later mutable cache recorded **21,748**. Never regenerate expectations from the latter.

Minimum staged fixture recovery:

1. **Downstream two-route gate:** accepted normal `DJI_20260107143259_0005` and polygon `DJI_20260202091128_0058`; actual float32 NPY temperatures, reviewed cover/known/target/shadow arrays, compact LUHK codes and mapping, capture/ambient/radiometric sidecars, accepted manifests/review records, golden pixel columns and summaries. Two temperature grids occupy about 2.5 MiB before compression. Preserve exact orientation, dtype, units and hashes; do not infer temperatures from saved means.
2. **Existing five-pilot tests:** restore the five named `*_temperature_celsius.npy` files (about 6.25 MiB total), their extraction metadata and any referenced validated tables. Restore the real legacy Part E Parquet only to exercise its physical row-count check. That Parquet is not required for all downstream replay if the pipeline can rebuild it from the small fixture.
3. **Accepted six-image gate:** recover the immutable six-image canonical aggregate (manifest size 8,854,137 bytes, about 8.44 MiB), selected manifests/review states and corresponding per-image thermal/label inputs. This verifies accepted six-image summaries/sampling and protects the exact polygon scope. Golden outputs alone do not prove regeneration.
4. **Pairing/alignment/classification gate:** one representative original V/T pair, reviewed transform/ROI or GCP evidence, superpixel labels and review JSON; add the polygon-route source pair as needed. A cropped display image alone cannot verify original alignment/camera dimensions. Reuse tracked LUHK grid/footprint tables where sufficient; only include a clipped official raster if testing raster lookup itself.
5. **Positive shadow gate:** an explicitly reviewed same-cover scene containing both shadow and non-shadow pixels, with independent shadow-known/review information. Existing all-zero real masks cannot supply this comparison. Synthetic positive shadow controller/spatial tests already exist but do not validate scientific shadow detection.

Named TAT3 parsing coverage separately needs the three report files expected by `test_v02_tat3_manual.py`; the historical assertion expects 185 entries. A sanitized representative report fixture may support a smaller parser test, but must not be described as satisfying that original exact-data test. Real SDK integration needs a Windows runner/workstation with licensed runtime, a raw thermal R-JPEG, parameter row and expected output/hash. No Mac execution of the Windows binary is required.

Use a small, access-appropriate fixture manifest and explicit artifact locations. Track small schemas/checksums/provenance; distribute restricted inputs separately. Do not require the full ~40 GB dataset to run the downstream regression gate.

## 10. CI diagnosis

The latest [failed workflow run](https://github.com/VITAMINC135246/heat_index_urop/actions/runs/32623845092), at Phase 2 HEAD, has **zero jobs** by GitHub API. Its published annotation is:

> (Line: 21, Col: 21): Unrecognized named-value: 'runner'. Located at position 1 within expression: runner.temp

The offending line is job-level `env.MPLCONFIGDIR: ${{ runner.temp }}\matplotlib`. This is a workflow-expression validation failure before runner allocation. It is not a test failure, dependency installation failure, timeout, missing artifact, or proof of scientific divergence. `gh run view` independently reports a likely workflow-file issue. Two earlier Phase 2 pushes also have failed records; they share this unchanged workflow.

Trigger/boundary inspection:

- `pull_request`: no branch/path filters.
- `push`: **only `main`**; a valid workflow would not run ordinary Phase 2 branch pushes.
- `workflow_dispatch`: present; availability/branch selection must be verified after a valid workflow is accessible to GitHub.
- One Windows-latest job; no matrix, `needs`, job/step `if`, path filters, downloaded artifacts, services or secrets.
- Setup selects Python 3.12.13 x64, installs pins, runs `pip check`, then `pytest -m 'not local_integration'` under PowerShell.
- No Mac/Linux coverage and no actual accepted-run replay or genuine DJI execution.
- Once validation is fixed, the new launcher test's nonexistent repo-local `.venv` assumption is an additional likely clean-Windows-CI failure; no Windows run was fabricated to confirm it.

Minimum future repair: set Matplotlib cache location in a permitted step context or through `$env:RUNNER_TEMP`/`GITHUB_ENV`; validate the workflow, make launcher tests hermetic, choose explicit stabilization push/PR coverage, and add a Mac job with a declared GUI-test boundary. Separate artifact-backed scientific replay from synthetic tests and Windows SDK integration. No CI file was modified during this audit.

## 11. macOS portability findings

| Finding | Scope and action |
|---|---|
| Hard-coded drives | Both branches: `scripts/02_extract_dji_metadata.py:310`, legacy Part D SDK default `D:\DJI_Thermal_SDK`, SDK template. Phase 2 additionally adds `D:\exiftool-13.59_64\exiftool.exe` to Part D and `C:\Windows\Fonts\arial*.ttf` in report generator. Treat tool/font paths as configurable. |
| Path construction | Most scientific paths use `pathlib`, not concatenated Windows separators. CMD, PowerShell and SDK `windows/release_x64` paths are explicitly platform-bound. No broad production `E:\...` path dependency was found in the source/config search. |
| Filesystem assumptions | Test expects unresolved temp-path spelling. No tracked case-fold filename collisions found. Lowercase global image ignore patterns leave uppercase extensions unprotected on case-sensitive systems outside ignored raw directories. |
| SDK resolver | Searches `.exe` paths on Mac and raises `FileNotFoundError` if absent; if a Windows binary is present, subprocess execution can fail at OS level. No explicit platform boundary/error. |
| Desktop wrapper | `workflow_gui.py:402` invokes `xdg-open` on Mac. Needs Darwin `open` dispatch. Tk import requires a Tk-enabled Python; headless analysis should not import GUI dependencies unnecessarily. |
| Legacy exports | `08_finalize_excel_workbooks.ps1` uses Excel COM; exporter and pipeline invoke PowerShell. Optional legacy Excel stages should be Windows-only. Current canonical Part E does not need Excel for its normal numerical/figure pipeline. |
| Workbook build | `excel_workbook_common.py` requires Node and `@oai/artifact-tool` at an ignored local path; this is external-runtime coupling, not declared Python dependency management. No junction/symlink was created. |
| Report generator | Windows fonts; `python-docx` absent from requirements. Non-core reporting dependency, not failure of thermal analysis. |
| Subprocess behavior | Primary scientific subprocesses use argument lists, explicit cwd, timeouts where relevant, and often UTF-8. This handles spaces in the mounted workspace path. No production shell-emulation fix is needed. |
| Environment/encoding | `DJI_IRP_EXE`, `DJI_THERMAL_SDK_ROOT`, local JSON already supported; GUI uses `PYTHONUTF8`/unbuffered output; most JSON writes specify UTF-8 and tables sometimes UTF-8-SIG. Windows PowerShell/console encoding remains a separate integration concern. |
| Current-directory coupling | Most entry points anchor to source location; direct user calls with relative SDK/thermal paths can still interact with a changed subprocess cwd. Config source paths may be absolute; the main issue is project-root coupling rather than universal cwd reliance. |
| Native dependencies | NumPy/SciPy/Pandas/PyArrow/OpenCV/Rasterio/PyProj/Pyogrio/Shapely installed as arm64-compatible packages here. No demonstrated Apple Silicon blocker in those pinned versions. Availability on other macOS/Python versions is not implied. |

Mac readiness: **headless downstream development is feasible now with a documented environment and supplied thermal artifacts; a clean supported Mac development/GUI workflow is not yet established.**

## 12. Windows-only boundary findings

The useful starting seam already exists on both branches:

```text
Windows raw thermal R-JPEG + explicit radiometric parameters
  -> DJI/TAT3 extraction
  -> temperature artifact + provenance + QA
  -> Mac/Windows/Linux NPY loader
  -> canonical pixels -> Part E/temporal analysis
```

`TemperatureResult(matrix, metadata, qa_status, qa_flags)` and `load_temperature_override` allow downstream work without launching DJI. `extract_temperature` accepts an injected runner, which supports platform-independent command/readout tests. No need to move the entire thermal module behind Windows imports or emulate DJI.

The boundary is incomplete: loading and execution live together; `resolve_irp_exe` has no OS gate; old/new command assembly is duplicated; an NPY can be supplied with insufficient units/definition/provenance; Phase 2 persists it through the legacy summary's identity. Standardize the artifact contract before extending this route.

Minimum contract: native shape/orientation, float32 Celsius temperature payload and checksum, input image identity/checksum, SDK/runtime identity, distance/humidity/emissivity/ambient/reflection values, extraction timestamp, QA flags and version, plus **separate ambient source/definition/validation**. A radiometric ambient parameter is not automatically meteorological ambient air temperature.

Windows-only by design: genuine DJI/TAT3 execution and legacy Excel COM. Cross-platform: thermal artifact loading/QA, parser tests using supplied reports, spatial/mask processing, tables, ΔT, statistics, plots and most review logic. Configurable: paths, data root, tool locations, fonts and optional output roots. Mac exclusions should cover only real Windows integration, not every test requiring precomputed data.

Future real-execution calls on unsupported hosts should fail explicitly, e.g. “DJI thermal extraction requires Windows and the DJI thermal runtime,” while precomputed-artifact paths continue to work. No Wine/emulation was attempted.

## 13. Data layout and Git boundary

Keeping `<PROJECT_ROOT>/data/` is appropriate and is retained. The present tracked hierarchy is not yet `raw/external/interim/processed/meta`; it contains `LUHK2024_SC.xlsx`, `annotations/`, `metadata/` and `processed/{footprints,grids}`. Code also expects ignored `raw/`, `luhk/`, `local_external/`, `interim/`, Part D matrices and canonical caches. Much derived content lives in `outputs/` for historical reporting/review.

| Existing location/content | Logical category | Recommendation |
|---|---|---|
| `data/raw/HKUST` originals | raw | Keep immutable/ignored; absent in this clone |
| LUHK mapping/raster, orthophotos, source TAT3 reports | external | Map logically to external; preserve existing references until explicit migration |
| `data/interim`, B alignment/SLIC previews | interim | Reproducible, normally untracked except selected frozen fixtures |
| Part D matrices, canonical stores, Part E pixel tables | processed | Artifact manifest and configured physical root; do not silently regenerate accepted data |
| `data/metadata`, reviewed annotation/mapping XLSX, baseline manifests | meta | Track reproducibility-critical small metadata deliberately; human-reviewed annotations are authoritative inputs, not disposable generated clutter |
| `outputs/part_e/figures`, summary tables, historical reports | reporting/processed artifacts | Keep accepted evidence intentionally; distinguish frozen records from new runtime outputs |

Git observations at Phase 2 HEAD:

- 425 tracked files; tracked blobs total about 132.8 MB decimal. `data/` accounts for 5,947,667 bytes/45 files; `outputs/` 125,009,439 bytes/232 files. Git pack is 59.83 MiB.
- Largest file: `outputs/geodata/pilot_10m_grid_cells.geojson` **34,251,094 bytes**. Other substantial tracked artifacts: old visible overlay PNG 5,664,008 bytes; example grid GeoJSON 4,285,495; Part E workbook 4,241,634; thermal footprints GeoJSON 2,887,920; new report DOCX 2,820,699; multiple visible-resolution mask arrays around 2.59 MB each.
- No tracked original JPG/JPEG/R-JPEG, `.raw`, SDK `.exe`/DLL, machine-local `*.local.*` config or `.gitattributes`/LFS setup was found at the audited tips. Do not infer that the tracked scientific masks and figures were accidental: `.gitignore` explicitly preserves historical/reporting evidence.
- Ignore rules correctly cover raw/source downloads, local configs, Part D matrices/sidecars, several Part E payloads, `outputs/runs/`, caches and venvs.
- **Gap:** production `config/workflow_v0_3.json` writes `data/processed/images_v0_3/`, `data/processed/part_e_v0_3/`, `data/metadata/canonical_result_index_v0_3.json`, and `outputs/part_e/v0_3/`. These version-specific paths are not covered by the older v0.1/v0.2 canonical ignores. `git check-ignore` confirms the canonical v0.3 array and index are unignored.
- Global image patterns are lowercase. Under `git -c core.ignorecase=false`, `data/test.JPG` is not ignored whereas `data/test.jpg` is; `data/raw/` still protects originals stored in the intended raw location.
- Extracted `*_temperature_metadata.json` files are wholly ignored. Some sanitized small extraction provenance should be preserved in the fixture manifest even when bulk payloads remain outside Git.
- Annotation backups are tracked. Retain until their role/history is established; do not delete them as a cosmetic cleanup.

There is **no unified `data_root` setting**. `dataset_root` and configurable output paths can point elsewhere, but pilot adapters, mapping readers, capture metadata and legacy scripts still resolve `PROJECT_ROOT/data/...`. Introduce one small path/config resolver with `data_root` defaulting to `<PROJECT_ROOT>/data`; route legacy logical paths through it incrementally. Keep code/config roots distinct from data/output roots and record logical identities independently of physical drive paths. No data was relocated and no symlink was created.

Before changing Git tracking, designate the small frozen regression set, add missing ignore rules, and archive bulky historical outputs deliberately if desired. No history rewrite is warranted by this audit.

## 14. Shadow readiness and minimum target architecture

**The proposed independent shadow attribute already exists.** Both branches have:

- `data/annotations/part_c/shadow_flag_mapping.xlsx` and separate physical cover mapping;
- reviewed `shadow_flag_*_grid.npy` and visible ROI masks;
- `part_c_review_gui.ReviewState.shadow`, Shadow/No shadow buttons, `generate_masks`;
- `canonical_result` optional `shadow_mask.npy`, pixel `shadow_flag` and `shadow_valid` separate from cover;
- Part E `surface_cover_shadow` sampling/grouping and cover × shadow summary/figure routes;
- tests for shadow review state, positive synthetic masks and unavailable shadow behavior.

Remaining scientific-model problem: omitted segment shadow labels default to `False`; canonical writing casts any provided shadow array to `bool`, and pixel construction treats a present mask as valid for every pixel. Thus **unobserved/uncertain and confirmed non-shadow are not fully distinguished within one mask**. Categorical values such as an unknown sentinel would be silently converted to True if passed through the existing bool cast. This must be designed explicitly before adopting categorical shadow states. All-zero historical masks cannot establish that every pixel was positively reviewed as sunlit.

Minimum architecture, using existing boundaries rather than renaming everything:

```text
source paths/config -> input validation and capture identity
 visible + thermal preview -> Part B accepted alignment
 aligned visible -> Part C reviewed cover + cover-known
 aligned visible -> future shadow method/review + shadow-known/QA
 Windows extraction OR portable thermal artifact -> TemperatureResult
 ambient source/definition + LUHK context + native grid attributes
 -> canonical_result -> part_e_adapter/runner -> cover × shadow statistics/plots
```

| Future change | Natural home | Preconditions |
|---|---|---|
| Shadow generation | responsibility-focused module beside `workflow/part_c_adapter.py`, invoked by existing workflow | Operate on accepted alignment/native-grid mapping; separate from physical cover classifier |
| Shadow storage | `canonical_result.py` artifacts and `models.py` manifest references | Explicit binary/categorical schema and per-pixel validity, method/version/provenance |
| Shadow QA/review | existing Part C review/controller and spatial figures | Distinguish missing, uncertain, reviewed shadow and reviewed non-shadow; validate alignment/resampling |
| Pixel schema | existing `pixel_frame`, compatibility normalization in `part_e_adapter.py` | Version/compatibility decision for validity and categorical states; no replacement of surface cover |
| Cover × shadow analysis | `part_e_pixel_common.family_eligible_and_group` and numbered statistics stage | Filter shadow-known observations; protect acceptance/target/source rules and no-default-pooling policy |
| Stratified figures | existing spectra and spatial scripts | Use the same filtered numerical tables; do not invent contrast for all-zero/no-positive-shadow data |

The minimum pre-Shadow work is artifact/provenance stabilization, environment/CI support, explicit shadow validity semantics and a reviewed positive fixture. A wholesale package move, replacing stage names, or extracting every utility is unnecessary. Preserve numbered CLIs as adapters; centralize duplicated code only when the new work touches it and regression coverage protects it.

## 15. Risk register

| Priority | Risk | Evidence/status | Release gate |
|---|---|---|---|
| High | Loss of temperature definition/unit identity | Reproduced in Phase 2 runtime probe | Exact provenance parity or explicitly approved schema normalization |
| High | Matrix reused with stale extraction/ambient metadata | Static Phase 2 persistence path; not exercised on real inputs | Versioned artifact + sidecar written/read together; lifecycle characterization |
| High | Accepted real behavior falsely inferred from green unit tests | Accepted matrices/run snapshots absent | Immutable small real-data regression fixture |
| High | Shadow absence treated as reviewed no-shadow | Default false, bool cast, blanket shadow-valid; real pilot masks all zero | Explicit validity/review semantics and positive reviewed fixture |
| Medium | CI provides no actual safety net | Confirmed invalid expression/zero jobs | Valid workflow and successful clean runners |
| Medium | Clean Mac/Windows test setup fails | Tk coupling, temp aliases, launcher `.venv` assumption | Hermetic tests, declared GUI boundary, OS jobs |
| Medium | Untracked data becomes accidentally staged | Missing v0.3 ignore paths | Config-aware Git boundary checks |
| Medium | User mistakes TAT3 ambient for measured air temperature | Existing baseline explicitly calls it provisional | Preserve source/definition in every table and stratification |
| Medium | Apparent spatial precision exceeds actual georegistration | LUHK explicitly uses approximate north-up footprint | Retain uncertainty metadata; do not claim alignment fixes map position |

## 16. Recommended baseline decision

**Case B: stabilize from `phase-2-safety-net` (`8eb389c`) while treating `main` (`06c61b4`, production code `953e974`) as the scientific oracle.** This is a recommendation for the parent of future stabilization work, not certification of HEAD as a development baseline ready for Shadow.

Case A is ruled out by broken CI, a confirmed scientific metadata change, environment/test defects, and unavailable accepted artifacts. Case C is not supported: the branch has no major missing pipeline functionality, most science is unchanged, extensive synthetic parity is exact, and the additions are localized. Selective recovery onto `main` would duplicate stabilization bookkeeping without evidence that it is safer. The first Phase 2 commit `5bc4b68` remains a valuable production-identical checkpoint if isolating the last commit's regressions.

The user's two-part standard is not yet fully satisfied: Phase 2 offers a useful but modest architectural improvement; complete preservation of accepted scientific behavior is still an open gate. Promote it only after the exact next steps below succeed. Do not merge either direction automatically. The current workspace remains on `main`; no stabilization or feature branch was created.

## 17. Exact next implementation steps and acceptance gates

1. **Establish an executable safety net on a new stabilization branch based on the recorded Phase 2 SHA.** After this audit decision, create that branch when proceeding with stabilization; retain both existing tips. Fix the job-level environment expression, choose branch/PR triggers, document Python/Tk/headless setup, normalize path assertions, and make the launcher test create/mock its files without globally impersonating the host OS. Gate: clean Mac and Windows synthetic suites pass, with only explicit platform/local-artifact exclusions; record counts and versions.
2. **Recover and freeze the smallest real fixture.** Start with accepted normal + polygon artifacts and restore the five matrices for existing pilot checks. Use the immutable accepted run, not a later cache. Preserve a manifest of inputs, methods, hashes, exact labels/row counts and justified float bounds. Gate: both branch baselines replay the same selected real artifacts; report every numerical/provenance difference without regenerating golden expectations automatically.
3. **Repair the thermal handoff without changing scientific formulas.** Preserve/validate definition, unit and ambient provenance; stop persisting bare matrices under an old extraction record; use a complete versioned artifact identity; separate genuine Windows execution from portable loading with an explicit unsupported-platform error. Characterize cache miss/hit, changed parameters, explicit NPY overrides and missing ambient. Gate: main-reference numerical and categorical/provenance parity, plus deterministic lifecycle behavior. Windows-only real SDK integration remains separately identified.
4. **Make data and Git boundaries explicit.** Add a minimal configurable `data_root` resolver while preserving the default `data/` location and existing logical mapping; cover v0.3 generated paths and uppercase imagery in ignores; retain small fixture provenance. Gate: identical regression output from an alternate physical data root, no generated payload staged, no missing tracked reproducibility metadata. Do not relocate raw data or introduce symlinks as a side effect.
5. **Define Shadow extension against the existing model, then open the feature effort.** Specify independent cover/shadow validity, treatment of historical default-zero masks, QA/reviewer/method provenance, native-grid alignment and cover × shadow grouping. Add a reviewed positive fixture and protect no-shadow/unavailable cases. Gate: approve the stabilized baseline only when steps 1–4 pass and the scientific schema decision is explicit; then begin `feature/shadow` work without changing accepted old outputs silently.

A concise machine-readable checklist is saved alongside this report as `audit_evidence/mac_phase2_20260923/stabilization-checklist.json`. The original scientific algorithms and validated research entry points remain unchanged.
