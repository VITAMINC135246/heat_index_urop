# Phase 2 owner acceptance procedure

Use this after the stabilization branch has been committed. Run the Mac and Windows sections independently; record the commit ID, Python version, command output, date, and any artifact hashes. A **thermal artifact** means a two-dimensional temperature matrix plus the metadata needed to identify its source and radiometric settings. **Provenance** means that source and processing history. **ΔT** is surface temperature minus the stated ambient value. The reference scientific output is the explicitly accepted `main` run described in [phase_1_accepted_baseline.md](baseline/phase_1_accepted_baseline.md), not a later shared cache.

An **automated test** checks code behavior; a **scientific regression test** compares measured outputs with an accepted reference result. A **fixture** is the fixed input and expected result used for that comparison. **CI** (continuous integration) is the GitHub Actions test run on a code change. `local_integration` tests need files in the original local project; a `windows_dji` test needs a real Windows DJI environment. A skipped test is not a pass for the real scientific gate.

## Mac acceptance

Run these commands from a fresh checkout of the repository, in a Terminal at its root. The commands use a local `.venv` and a temporary Matplotlib cache so they do not alter accepted outputs.

### 1. Verify the source and clean checkout

**What I do**

```sh
git switch stabilize/phase2-final
git rev-parse HEAD
git status --short
git log -1 --oneline
```

**Success looks like:** the branch is `stabilize/phase2-final`, the commit matches the stabilization report, and `git status --short` prints nothing. `main` and `phase-2-safety-net` still exist. **Failure means:** a different commit or local edits make the result difficult to attribute; record and resolve the difference before comparing science.

### 2. Build the Python environment

**What I do**

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -c constraints/windows-py312-reference.txt
python -m pip check
python --version
python -c 'import tkinter; print("Tk", tkinter.TkVersion)'
```

**Success looks like:** CPython 3.12 with Tk support, dependency installation, and `pip check` all succeed. The portable suite imports the desktop workflow module, even though it does not open a window; it needs a Tk-enabled interpreter. The headless tests do not need DJI. **Failure means:** first resolve Python/native-package installation or Tk interpreter issues before interpreting a test failure as a scientific change.

### 3. Verify data-root resolution and portability

**What I do**

```sh
python -c 'from heat_index.config.paths import project_paths; p=project_paths(); print(p.data_root); print(p.resolve("data/metadata/part_b_pilot_pairs.xlsx"))'
HEAT_INDEX_DATA_ROOT="$(mktemp -d)" python -c 'from heat_index.config.paths import project_paths; p=project_paths(); print(p.data_root); print(p.resolve("data/metadata/example.csv")); print(p.resolve("config/workflow_v0_3.json"))'
```

For a permanent override, copy `config/paths.local.template.json` to ignored `config/paths.local.json` and put the actual physical `data_root` there; the environment variable takes precedence. Do not move or rewrite tracked data for this check.

**Success looks like:** without an override, `data_root` is `<repository>/data`; with the environment variable, only logical `data/...` paths move to the temporary root and `config/...` stays under the checkout. No shared source path needs a Windows drive letter. **Failure means:** the path resolver or a caller still depends on a machine path or the current working directory.

### 4. Run the Mac-compatible suite and synthetic downstream path

**What I do**

```sh
MPLBACKEND=Agg MPLCONFIGDIR="$(mktemp -d)" python -m pytest -ra -p no:cacheprovider --basetemp "$(mktemp -d)" -m 'not windows_dji and not local_integration'
MPLBACKEND=Agg MPLCONFIGDIR="$(mktemp -d)" python -m pytest -ra -p no:cacheprovider --basetemp "$(mktemp -d)" tests/test_v02_part_e_formal.py
```

The first command is the portable CI selection. The second deliberately exercises a synthetic multi-component Part E path: canonical images, native-grid pixels, sampling, statistics, figures, QA, and resume. Review [phase2_synthetic_regression_result.json](phase2_synthetic_regression_result.json): the stabilization replay versus `main` recorded exact equality for 24 NPY arrays, 22 CSV and 10 Parquet tables, and 41 PNG pixel arrays (97 outputs). Running the test locally checks execution; that JSON is the recorded cross-branch comparison.

**Success looks like:** zero failed/errors, with skips limited to documented optional local inputs. The formal Part E test passes; the recorded 97-output comparison has `all_equal=true`. **Failure means:** an ordinary test failure needs diagnosis; a numerical/categorical difference from the reference is a scientific-regression blocker, and its tolerance must not be widened merely to pass.

### 5. Check the architecture and thermal handoff

**What I do**

```sh
python -c 'import heat_index.config.paths, heat_index.io.canonical, heat_index.spatial.alignment, heat_index.classification.surface_cover, heat_index.thermal.extraction, heat_index.analysis.pixels, heat_index.pipeline.workflow; print("responsibility imports OK")'
python scripts/run_analysis.py --help
python scripts/part_e/run_part_e_pipeline.py --help
```

Read [architecture.md](architecture.md), then inspect `scripts/run_analysis.py` and one numbered Part E script. They should be compatibility entry points to `heat_index.pipeline` and `heat_index.analysis`/visualization/reporting, while the historical command names still work. If a recovered complete thermal artifact is present, run its reader and the accepted-real test described next; opening a bare NPY file alone does not verify its provenance.

**Success looks like:** imports and `--help` work without TAT3/DJI, reusable logic lives in the responsibility packages, and a supplied artifact loads with matching source/parameter metadata. **Failure means:** a broken compatibility command, import dependency, or detached matrix/metadata boundary remains.

### 6. Run the real accepted fixture when recovered

**What I do:** use [windows_artifact_recovery.md](windows_artifact_recovery.md) to copy the smallest accepted run-scoped fixture. Fill `tests/fixtures/accepted_real/manifest.json` from [manifest.template.json](../tests/fixtures/accepted_real/manifest.template.json), using original `main`/Windows evidence. Put each case's accepted arrays, manifest, and Parquet table under the `accepted_dir` named there, then run:

```sh
MPLBACKEND=Agg MPLCONFIGDIR="$(mktemp -d)" python -m pytest -ra -p no:cacheprovider --basetemp "$(mktemp -d)" tests/test_accepted_real_regression.py
```

Do not create expected values with Phase 2. If only the tracked template exists, pytest skips this case; record the gate as **BLOCKED: accepted fixture absent**, never as a pass. An active but incomplete `manifest.json` must fail so missing inputs are visible.

**Success looks like:** the real test executes without a missing-fixture skip and checks image IDs, native dimensions, masks/eligibility, matrix identity, radiometric and ambient provenance, pixel rows, ΔT, counts, and grouped summaries for the **normal pilot route**. Its current adapter cannot replay the accepted Part C* polygon route or certify the full six-image run. The original procedure required a separate route-specific polygon replay for full certification; the owner acceptance decision below supersedes that requirement after the accepted frozen six-image aggregate regression passed. **Failure means:** investigate the first differing input or definition; an incomplete fixture is a recovery task, while a completed fixture with different scientific values is a regression requiring review.

## Windows acceptance

Use a separate stabilization checkout on the original Windows machine. It may point `HEAT_INDEX_DATA_ROOT` at the existing data tree; preserve the original project and accepted run directory.

### 1. Verify checkout, Python and full-data path

**What I do**

```powershell
git switch stabilize/phase2-final
git rev-parse HEAD
git status --short
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -c constraints/windows-py312-reference.txt
.\.venv\Scripts\python.exe -m pip check
$env:HEAT_INDEX_DATA_ROOT = 'E:\path\to\existing\data'
.\.venv\Scripts\python.exe -c "from heat_index.config.paths import project_paths; p=project_paths(); print(p.data_root); print(p.resolve('data/raw/HKUST'))"
```

Replace only the example path with the existing physical data directory. **Success looks like:** same stabilization commit as Mac, clean checkout, Python 3.12 and valid dependencies, and logical `data/raw/HKUST` resolving under that Windows data root. **Failure means:** a checkout/environment difference or wrong root would invalidate later comparisons.

### 2. Recover and verify the historical sources

**What I do:** follow [windows_artifact_recovery.md](windows_artifact_recovery.md). Locate the original TAT3 batch reports, original/local Part D parameter config, five pilot matrices and sidecars, raw selected V/T pairs, and immutable accepted run `run_20260722T055625Z`. Hash selected files with `Get-FileHash -Algorithm SHA256 -LiteralPath <path>` and compare recorded hashes in [phase_1_baseline_manifest.json](baseline/phase_1_baseline_manifest.json). Check the parsed per-image parameter row against the TAT3 report and the tracked Part D summary. Preserve the stated provisional ambient definition.

**Success looks like:** each chosen image has its own report/parameter source, original thermal matrix and source identity; accepted-run files match recorded hashes where a hash exists. **Failure means:** a different run or mutable cache may have been selected, or provenance is missing. Do not infer a missing DJI/TAT3 setting from a nearby image.

### 3. Run portable and Windows-specific tests

**What I do**

```powershell
$env:MPLBACKEND = 'Agg'
$env:MPLCONFIGDIR = Join-Path $env:TEMP 'heat-index-owner-mpl'
.\.venv\Scripts\python.exe -m pytest -ra -p no:cacheprovider --basetemp (Join-Path $env:TEMP 'heat-index-owner-pytest') -m 'not local_integration and not windows_dji'
.\.venv\Scripts\python.exe -m pytest -ra -p no:cacheprovider --basetemp (Join-Path $env:TEMP 'heat-index-owner-win') -m 'windows_dji'
```

After the recovered files are in place, run `-m local_integration` and `tests/test_accepted_real_regression.py` explicitly with the same `python -m pytest -ra -p no:cacheprovider` pattern. **Success looks like:** zero failures/errors; tests requiring recovered assets execute rather than skip. A `windows_dji` selection with zero collected tests is **not** evidence of real DJI acceptance; complete the extraction check below. **Failure means:** separate a test setup problem from a scientific result mismatch. The GitHub Windows runner need not have proprietary DJI installed.

### 4. Perform one controlled real extraction and TAT3 comparison

**What I do:** select the accepted normal pilot `DJI_20260107143259_0005` and its original `_T.JPG`. Set `DJI_IRP_EXE` to the installed binary and a scratch destination. The following script reads the tracked Part D row, verifies the five SDK parameters against its original TAT3 DOCX, runs a single extraction, compares the native matrix with the recovered original, and writes a versioned `.npy` + `.json` artifact for transfer. It does not overwrite the accepted matrix.

```powershell
$env:DJI_IRP_EXE = 'E:\path\to\dji_irp.exe'
$env:HEAT_INDEX_ACCEPTANCE_ARTIFACT_DIR = Join-Path $env:TEMP 'heat-index-phase2-cross-machine'
@'
import os
import tempfile
from pathlib import Path
import numpy as np
import pandas as pd
from heat_index.config.paths import project_paths
from heat_index.thermal.artifact import load_thermal_artifact, write_thermal_artifact
from heat_index.thermal.extraction import (
    extract_temperature, load_parameter_row, load_report_parameter_row, resolve_irp_exe,
)

image_id = "DJI_20260107143259_0005"
paths = project_paths()
summary = pd.read_csv(paths.project_root / "outputs/part_d/summaries/part_d_tat3_parameter_temperature_extraction_summary.csv", keep_default_na=False)
row = summary.loc[summary.image_id.eq(image_id)].iloc[0]
thermal_path = paths.resolve(row["t_path"])
matrix_path = paths.resolve(row["npy_path"])
report_path = paths.resolve(row["tat3_parameter_source_report"])
parameter_path = paths.project_root / "outputs/part_d/qa/tat3_parameter_audit/part_d_tat3_pilot_parameters.csv"
parameters = load_parameter_row(parameter_path, image_id)
report_parameters = load_report_parameter_row(report_path, image_id)
for key in ("distance_m", "relative_humidity_percent", "emissivity", "ambient_temperature_c", "reflected_temperature_c"):
    assert parameters[key] == report_parameters[key], (key, parameters[key], report_parameters[key])
with tempfile.TemporaryDirectory() as scratch:
    result = extract_temperature(
        thermal_path=thermal_path, image_id=image_id, parameters=parameters,
        work_directory=Path(scratch), irp_exe=resolve_irp_exe(),
    )
assert result.matrix.dtype == np.dtype("float32") and result.matrix.shape == (512, 640)
reference = np.load(matrix_path, allow_pickle=False)
np.testing.assert_allclose(result.matrix, reference, rtol=0, atol=2e-6)
out = Path(os.environ["HEAT_INDEX_ACCEPTANCE_ARTIFACT_DIR"])
out_path = out / f"{image_id}_temperature_celsius.npy"
sidecar = write_thermal_artifact(out_path, result, image_id=image_id)
load_thermal_artifact(out_path, image_id=image_id, native_shape=(512, 640), expected_parameters=parameters, source_image_path=thermal_path)
print("QA:", result.qa_status, result.qa_flags)
print("accepted mean Celsius:", float(np.mean(reference, dtype=np.float64)))
print("artifact:", out_path, sidecar)
'@ | .\.venv\Scripts\python.exe -
```

The single-extraction comparison is stricter than the historical summary-statistic assertion; if it differs, inspect the exact source, report, SDK version and parameter values before deciding whether any difference is acceptable. `Get-FileHash -Algorithm SHA256` on both written files records the artifact identity.

**Success looks like:** native 512×640 float32 Celsius output, original source identity, recorded parameter values, and accepted/TAT3 agreement within predeclared bounds. **Failure means:** first check source file, orientation, report row, SDK binary and parameters. Do not loosen a bound merely to pass. A warning for the previously recorded subzero review range is not automatically a new failure if the values/QA match the accepted record.

### 5. Check the accepted result and cache identity

**What I do:** run the real accepted fixture test with the Windows copy of its fixed manifest and payloads. Inspect each thermal matrix/metadata pair and deliberately try a copied matrix with a mismatched metadata sidecar or changed parameter fingerprint in a scratch folder. Confirm the loader rejects it or marks it unusable; then restore the pair. Inspect the generated pixel-table image IDs, row counts, source/ambient strata, and ΔT against the immutable run. Do not use the later shared football cache to redefine the accepted polygon count.

**Success looks like:** the optional normal-pilot real regression passes; altered or mismatched cache metadata cannot be silently reused; a separate review of the immutable full six-image run confirms the polygon has 21,047 eligible target pixels, not the later cache's 21,748. The optional normal-pilot test alone does not certify that full run. **Failure means:** an artifact-consistency defect or real scientific difference remains. Report exact affected image/field/hash.

## Cross-machine acceptance

Use the same stabilization commit, same selected source records, and the **Windows-produced complete thermal artifact pair** from step 4 for `DJI_20260107143259_0005`. Copy its matrix and metadata together to the Mac under the corresponding configured data root, along with the selected original V/T pair and reviewed mask/context records needed by `adapt_pilot_image`. Record SHA-256 for both files on Windows with `Get-FileHash -Algorithm SHA256`, and on Mac with `shasum -a 256`; hashes must match exactly. Do not rerun DJI on Mac.

On both machines, set `HEAT_INDEX_ACCEPTANCE_ARTIFACT_DIR` to the folder containing that pair and run this identical Python source (PowerShell: put the source in a here-string and pipe it to `python -`; Mac: use a shell heredoc with `python -`). It verifies the sidecar, passes the loaded `TemperatureResult` through the pilot adapter, and prints comparable downstream metrics:

```python
import json
import os
import tempfile
from pathlib import Path
import pandas as pd
from heat_index.io.pilot import adapt_pilot_image
from heat_index.thermal.artifact import load_thermal_artifact

image_id = "DJI_20260107143259_0005"
matrix = Path(os.environ["HEAT_INDEX_ACCEPTANCE_ARTIFACT_DIR"]) / f"{image_id}_temperature_celsius.npy"
temperature = load_thermal_artifact(matrix, image_id=image_id, native_shape=(512, 640))
with tempfile.TemporaryDirectory() as scratch:
    _manifest, manifest_path = adapt_pilot_image(
        Path.cwd(), image_id, output_root=Path(scratch), temperature_result=temperature,
    )
    pixels = pd.read_parquet(manifest_path.parent / "pixels.parquet")
    selected = pixels.loc[pixels.analysis_eligible.astype(bool)]
    result = {
        "image_id": image_id,
        "native_rows": len(pixels),
        "accepted_rows": len(selected),
        "cover_counts": {str(k): int(v) for k, v in selected.surface_cover_class.value_counts().sort_index().items()},
        "ambient_c": float(selected.ambient_temperature_c.iloc[0]),
        "mean_delta_t_c": float(selected.delta_t_c.mean()),
        "temperature_definition": temperature.metadata["temperature_definition"],
        "provenance_binding": temperature.metadata["provenance_binding"],
    }
print(json.dumps(result, sort_keys=True, indent=2))
```

Run `tests/test_accepted_real_regression.py` on both machines as well, using the same fixed fixture. Compare image ID, 512×640 orientation, matrix hash, parameter/source metadata, 327,680 native pixel coordinates, mask/eligibility counts, ambient 11.0 °C with its provisional TAT3 definition, and eligible mean ΔT against the accepted reference (3.2802686942 °C for this normal image). Exact categorical/count/identity fields must agree; floating values use only the test's stated precision. The accepted-real test must actually execute on both machines, with no missing-fixture skip.

**Success looks like:** unchanged artifact bytes load on Mac, yield the same downstream pixel-table and ΔT results as Windows, and agree with the original accepted `main` reference. **Failure means:** identify whether the divergence starts at byte transfer, sidecar identity, path resolution, native-grid mapping, dependency numeric behavior, or downstream calculation. This is a required owner gate; a green synthetic test alone does not satisfy it.

Keep the command logs and hashes with the acceptance record. Only the owner can mark Mac and Windows acceptance complete after these checks; if the real payloads are still unavailable, full scientific certification remains blocked.

## Windows execution record — 2026-09-24

This section records the actual Windows execution of the procedure above. The detailed closure narrative is in [phase2_stabilization_report.md](phase2_stabilization_report.md), and the compact evidence is in [phase2_windows_acceptance_20260924.json](phase2_windows_acceptance_20260924.json).

### Source, isolation, environment and data root

- Fetched branch: `stabilize/phase2-final`; source commit `4c3af875c83cbda70f027a3d9619a2e617d8027f`.
- Execution used an isolated Windows worktree. The old validated checkout and accepted run were retained as read-only scientific references.
- CPython 3.12.10, pip 26.2.1, pytest 9.1.1, and Tk 8.6 were available; `pip check` passed.
- Ignored `config/paths.local.json` and `config/part_d_sdk.local.json` selected the preserved external data tree and DJI executable. `HEAT_INDEX_DATA_ROOT` correctly overrode the file setting without moving repository configuration outside the checkout.
- `dji_irp.exe` reported `APP version : V1.7` and had SHA-256 `58e693879f8cf504738ed9f9ced8769dd0d1c81a532b0e6683f2c4f2d8654372`. The installed TAT3 executable had file version `0.2.6`; the accepted DOCX does not independently bind itself to that installed file version.

### Test execution

| Selection | Final result | Acceptance interpretation |
|---|---|---|
| `python -m pytest -ra -p no:cacheprovider --basetemp <scratch> -m "not local_integration and not windows_dji"` | **123 passed, 2 skipped, 6 deselected** | Pass. The accepted-real case executed. The two skips were documented platform-boundary checks. |
| `python -m pytest -ra -p no:cacheprovider --basetemp <scratch> tests/test_v02_part_e_formal.py` | **1 passed** | Pass; the preserved synthetic comparison is 97/97 exact outputs. |
| `python -m pytest -ra -p no:cacheprovider --basetemp <scratch> -m local_integration` | **6 passed, 125 deselected** | Pass after placing the required verified payload in the isolated worktree's ignored local data paths. The first failure/skip set was classified as fixture placement, not science. |
| `python -m pytest -ra -p no:cacheprovider --basetemp <scratch> tests/test_accepted_real_regression.py` | **1 passed** | Pass; no missing-fixture skip. |
| `python -m pytest -ra -p no:cacheprovider --basetemp <scratch> -m windows_dji` | **0 selected, 131 deselected** | Not evidence and not counted as a pass. The real controlled SDK extraction below supplied the DJI acceptance evidence. |

### Real extraction, TAT3 and downstream evidence

The recovered manifest identified the accepted normal pilots as `DJI_20260107143259_0005`, `DJI_20260107143320_0007`, `DJI_20260107143328_0008`, `DJI_20260107143344_0009`, and `DJI_20260107143401_0011`. New Phase 2 SDK outputs were written to a separate acceptance directory. All five 512×640 float32 NPY files were byte-identical to their old accepted matrices; the maximum absolute temperature difference was 0.0 °C and zero pixels exceeded `rtol=0`, `atol=2e-6 °C`.

All 25 recovered TAT3 parameter comparisons were exact: distance 5 m, exported humidity 50%, emissivity 0.95, and the per-image ambient/reflected values. Accepted TAT3 report SHA-256: `50fa623f2650e37fea5ccf992abb40532b00ceea37ed36d3959fffb4c2a86023`. The report contains no manual point or region values, so none were invented; validation combined the complete parameter record with full accepted-matrix equality. Exported humidity remains explicitly non-meteorological.

Each normal route reproduced 327,680 rows and its accepted pixel coordinates, masks, surface-cover classes, ambient stratum, temperatures, ΔT, cover counts, and grouped summaries, with 0.0 °C maximum numeric difference. The immutable accepted six-image aggregate had SHA-256 `aa2c3fefa1dd64620d43d2180af05958b35cefdfd93fe59957260cfe76f79a1b`, 1,966,080 rows, and exactly 21,047 accepted polygon pixels. Aggregate replay produced 17 exact scientific tables/samples and 56/56 pixel-exact PNGs. A float32-versus-float64 reduction difference of `1.4511962440622028e-6 °C` in the common source-summary fields remained below the existing `2e-6 °C` tolerance.

Two deliberate cache-integrity attacks were rejected: a matrix paired with a different sidecar, and ambient metadata changed without recomputing its parameter fingerprint. This verifies that the accepted result was not obtained through silent stale-cache reuse.

### Cross-machine package and hosted CI

Windows replay of the new v1 pair for `DJI_20260107143259_0005` produced 327,680 native/eligible rows, the accepted cover counts, ambient 11.0 °C, `provenance_binding=verified`, and mean ΔT `3.280268430709839 °C`. Its difference from the accepted float64-reduction mean `3.2802686942042785 °C` is below the existing `1e-6 °C` grouped-mean limit.

The exact pair was packaged as `phase2_windows_to_mac_cross_machine_20260924.zip` with SHA-256 `8267448505297939bfc9a7af72a18f71121f76aac4f8da78a8d9872bb0c94a35`. Matrix SHA-256 is `814ef8337c79ab6646c7ccc3be6c1fd14b3323079a3c984bcba647d87627b80a`; sidecar SHA-256 is `f45e95f28f33fa8af66bce6370cc254c2124f0f99760b65c82ea360364a4f57a`. The package contains a manifest, internal checksums, Windows metrics, instructions, and a Mac replay script. No Mac execution host was available to this Windows task, so the required result from the same new pair remains **BLOCKED** pending transfer and execution. Do not substitute the earlier Mac fixture result for this gate.

GitHub Actions run [35965519283](https://github.com/VITAMINC135246/heat_index_urop/actions/runs/35965519283) actually created and completed both configured jobs: [Windows](https://github.com/VITAMINC135246/heat_index_urop/actions/runs/35965519283/job/107523116757) and [macOS](https://github.com/VITAMINC135246/heat_index_urop/actions/runs/35965519283/job/107523116923) both succeeded. Proprietary SDK extraction remained a local Windows owner check as intended.

### Owner gate outcome

- Windows acceptance: **PASS**.
- Real scientific regression: **PASS**.
- Hosted CI: **PASS**.
- Cross-machine replay of the new Windows-produced pair: **BLOCKED** because no Mac host was accessible.
- Full scientific certification and Phase 2 closure: **BLOCKED / NOT COMPLETE** until that replay succeeds and its Mac hashes, metrics, and accepted-real test output are appended here.

The missing standalone polygon canonical bundle limits independent polygon-route regeneration, but it does not block the completed immutable-aggregate comparison. It is not the reason the final certification is blocked.

## Owner polygon acceptance decision — 2026-09-24

The owner explicitly accepts the frozen six-image aggregate regression as sufficient Phase 2 polygon-path evidence. The earlier Step 6 requirement for a separate route-specific polygon replay is superseded for Phase 2 closure. **Route-specific polygon replay was waived by owner acceptance decision because the accepted frozen aggregate regression is considered sufficient for Phase 2 closure.** No route-specific replay is claimed to have occurred. The standalone historical polygon canonical array bundle remains unrecovered and is a documented non-blocking limitation. The required Windows-to-Mac replay of the new v1 thermal artifact was a separate gate and is closed by the Mac execution below.

## Mac cross-machine execution record — 2026-09-24

The Windows outcome above describes the state when the Windows record was written. The later Mac execution closed its remaining cross-machine gate. The transferred `phase2_windows_to_mac_cross_machine_20260924.zip` was found in Mac Downloads and had the expected SHA-256 `8267448505297939bfc9a7af72a18f71121f76aac4f8da78a8d9872bb0c94a35`. All six internal file hashes passed after removing carriage returns from the Windows-format checksum list for the check; the package files themselves were not changed. Its complete v1 pair was installed under the ignored configured data root at `data/local_external/phase2_cross_machine_20260924/`, separate from the historical accepted fixture. The matrix and sidecar SHA-256 values remained `814ef8337c79ab6646c7ccc3be6c1fd14b3323079a3c984bcba647d87627b80a` and `f45e95f28f33fa8af66bce6370cc254c2124f0f99760b65c82ea360364a4f57a`. The original Mac `_T.JPG` matched the sidecar's source SHA-256 `f879183623281c77df24d773bb5d7ebf64569661c89b25284ea3a7001cadcdb9`.

Mac ran CPython 3.12.5 and pytest 9.1.1. The exact successful replay command, from the checkout root with the project virtual environment active, was:

```sh
PYTHONPATH="$PWD" python data/local_external/phase2_cross_machine_20260924/run_mac_replay.py
```

Launching the same script without `PYTHONPATH` first failed at import, before any scientific processing, because Python added the script's ignored data directory rather than the checkout to its import path. The successful command changed only that launch path. It did not change the matrix, sidecar, expected result, or tolerance.

The replay returned **PASS**. Windows and Mac matched exactly for image identity, `327,680` native and eligible rows, four cover counts (`20,871` concrete pavement, `14,540` low vegetation, `30,014` roof, `262,255` tree), temperature definition, verified provenance, ambient `11.0 °C`, and mean ΔT `3.280268430709839 °C`. Observed Windows-to-Mac numeric difference was `0.0 °C`. The mean differed from the accepted float64 reference `3.2802686942042785 °C` by `2.6349443960071994e-7 °C`, under the existing `1e-6 °C` grouped-mean tolerance. Mac metrics SHA-256 was `3c4b16c3649db80dd8c17e216bea5a875e3171d11df009e2fd7ca032d12cec69`.

An additional comparison against the fixed accepted fixture found all seven arrays element-exact and all `327,680` rows' temperature, ambient, and ΔT values exact. Fifty of 51 accepted pixel-table columns matched exactly. The sole wording difference was the v1 unit token `degC` versus the historical description `Celsius interpreted from SDK measure output`; both denote Celsius. No numeric, mask, identity, count, or other provenance field differed. The Windows package did not contain a full Windows pixel-table hash, so this extra full-table comparison is to the immutable accepted fixture, while the package's defined Windows-to-Mac metrics comparison is exact. No golden value was edited.

The explicit accepted-real command from Mac Step 6 above executed with **1 passed, 0 skipped**. The formal synthetic Part E command from Mac Step 4 passed. The portable Mac selection from Mac Step 4 finished with **124 passed, 1 skipped, 6 deselected**; the skip was the documented Windows Tcl bootstrap. The complete machine-readable Mac replay record is [phase2_cross_machine_mac_acceptance_20260924.json](phase2_cross_machine_mac_acceptance_20260924.json). **Cross-machine replay: PASS.** The historical polygon bundle and unknown standalone accepted TAT3 application version remain documented non-blocking limitations.
