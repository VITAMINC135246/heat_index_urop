# Phase 2 environment and CI boundary

This page describes the stabilized Phase 2 code, which moved reusable implementation into responsibility-based `heat_index/` modules and kept `scripts/` as compatibility entry points. The package map and data flow are in [architecture.md](architecture.md); owner-run checks are in [phase2_owner_acceptance.md](phase2_owner_acceptance.md). `main` remains the scientific reference until real accepted artifacts are recovered and owner acceptance is complete.

`requirements.txt` is the human-maintained dependency declaration. `constraints/windows-py312-reference.txt` pins the observed Python 3.12 reference environment; the Phase 1 Windows machine used CPython 3.12.13 and pip 26.1.2. The constraints do not package external DJI/TAT3, ExifTool, or Excel tools. Matching package versions across operating systems do not establish identical native GIS/vision binaries or real scientific equivalence.

On Windows, the local setup is:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install "pip==26.1.2"
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -c constraints/windows-py312-reference.txt
.\.venv\Scripts\python.exe -m pip check
```

On macOS, use a CPython 3.12 interpreter with Tk support for the full portable suite and the review UI, create `.venv`, and install the same requirements with the constraints. The tests import the desktop workflow module without opening a window. Portable headless work consumes a complete precomputed thermal artifact; genuine DJI extraction remains a controlled Windows operation. `HEAT_INDEX_DATA_ROOT` or ignored `config/paths.local.json` selects a machine's physical data directory while the logical default remains `<repository>/data`.

## GitHub Actions

[scientific-regression.yml](../.github/workflows/scientific-regression.yml) is triggered for pull requests, pushes to `main`, `phase-2-safety-net`, and `stabilize/**`, and manual dispatch. It has separate macOS and Windows Python 3.12 jobs, read-only repository permissions, a 40-minute job limit, headless Matplotlib, isolated temporary plot/pytest directories, and no pytest cache. The previous job-level `runner.temp` expression was invalid before runner allocation; the current workflow sets `MPLCONFIGDIR` in a runner step using `RUNNER_TEMP` and `GITHUB_ENV`. A valid workflow file is necessary but is not itself proof that a remote job has run successfully; inspect the actual Actions run for the final commit.

Both generic runners use:

```text
python -m pytest -ra -p no:cacheprovider --basetemp <runner-temp>/pytest -m "not local_integration and not windows_dji"
```

The Mac job uses a conda-forge Python/Tk environment; the Windows job uses `actions/setup-python`. Neither generic runner needs a local DJI installation or private source data. The workflow includes portable unit, integration, ordinary regression, synthetic scientific regression, tracked masks/summaries, routing/review, canonical/Part E and temporal checks. The test markers are declared in `pytest.ini`: `unit`, `integration`, `regression`, `scientific_regression`, `windows_dji`, and `local_integration`.

The latest local Mac CI-equivalent run (Python 3.12.13, pytest 9.1.1) reported **123 passed, 2 skipped, 6 deselected in 57.48 s**. The skips were the absent accepted-real fixture and a Windows Tcl bootstrap; the six deselections require ignored controlled-local assets. The workflow YAML parses with two jobs and without the invalid job-level expression. Hosted GitHub jobs remain unrun while the branch is local and unpushed.

`local_integration` covers checks needing ignored TAT3 reports, five real pilot matrices, a real Part E Parquet file, or related local records. Those tests are retained for the original Windows machine and for a Mac with the needed precomputed files. A selected accepted-real test reads `tests/fixtures/accepted_real/manifest.json` and case payloads when they have been recovered; the tracked [manifest.template.json](../tests/fixtures/accepted_real/manifest.template.json) does not count as a fixture. The test skips when the active manifest is absent and fails when an active fixture is incomplete. A CI run with that skip demonstrates only the portable safety net; the accepted-real scientific gate remains blocked.

`windows_dji` is for genuine TAT3/DJI work in the original Windows environment. A generic Windows GitHub runner does not certify licensed extraction. The owner must recover original parameter reports and accepted run snapshots, execute a controlled extraction, compare it with TAT3 and the accepted `main` result, then verify the complete artifact transfers unchanged to Mac. See [windows_artifact_recovery.md](windows_artifact_recovery.md) and [phase2_owner_acceptance.md](phase2_owner_acceptance.md).
