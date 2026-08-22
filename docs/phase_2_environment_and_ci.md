# Phase 2 Environment and CI Safety Net

## Scope

Phase 2 adds a reproducible automated-test environment and one minimum CI
check. It does not change production code, scientific behavior, schemas,
versions, command-line interfaces, configuration meanings, or accepted
artifacts.

The accepted Phase 1 environment remains the scientific reference. The
environment described here reproduces the automated test boundary; it is not a
universal cross-platform support promise.

## Reference environment specification

The human-maintained dependency declaration remains `requirements.txt`.
Install it with the exact Windows CPython 3.12 reference constraints:

```powershell
py -3.12 -m venv <isolated-environment>
<isolated-environment>\Scripts\python.exe -m pip install "pip==26.1.2"
<isolated-environment>\Scripts\python.exe -m pip install -r requirements.txt -c constraints/windows-py312-reference.txt
<isolated-environment>\Scripts\python.exe -m pip check
```

The intended interpreter line is CPython 3.12. The accepted Phase 1 reference
used CPython 3.12.13 on 64-bit Windows, and CI selects that exact patch. The
constraints pin every Python package in the accepted Phase 1 inventory except
`pip`. Installer tooling is bootstrapped separately so the constraints describe
the environment installed from `requirements.txt`.

The exact pins preserve the accepted dependency set without upgrades. They
include runtime, test, optional GIS, and transitive packages because omitting
transitive versions would not reproduce the observed environment. External
tools are not Python dependencies and are intentionally absent: DJI Thermal
SDK, TAT3, ExifTool, and Microsoft Excel.

The GIS and image stack includes native wheels, notably Rasterio, PyProj,
Pyogrio, Shapely, OpenCV, SciPy, and PyArrow. The reference specification is
validated for 64-bit Windows and does not promise that identical wheels or
native-library builds exist on other operating systems. Exact versions without
artifact hashes also leave package-index and supply-chain identity outside this
minimum lock.

## Automated CI boundary

GitHub Actions is used because `origin` is a GitHub repository and no existing
CI configuration is authoritative. The workflow is
`.github/workflows/scientific-regression.yml`.

The check runs on pull requests, pushes to `main`, and manual dispatch. It uses
a Windows runner, CPython 3.12.13, read-only repository contents permission, a
30-minute timeout, a headless Matplotlib backend, disabled Python bytecode, a
temporary Matplotlib directory, a temporary pytest base directory, and no
pytest cache.

The blocking command is:

```powershell
python -m pytest -ra -p no:cacheprovider --basetemp "$env:RUNNER_TEMP\pytest" -m "not local_integration"
```

Tracked or synthetic scientific and workflow tests remain blocking, including
numeric mask and summary baselines, routing, review gates, controller behavior
that does not open an interactive GUI, subprocess entry-point tests, canonical
schema and eligibility, Part E, spatial, and temporal behavior.

## Controlled local acceptance

The `local_integration` marker excludes only six checks that require ignored
controlled-local inputs:

- `test_named_local_ambient_reports_have_185_entries_and_no_manual_measurements`
  requires three named ignored TAT3 reports;
- `test_existing_part_e_row_count_when_local_parquet_is_available` requires the
  ignored real Part E Parquet container and preserves its physical row-count
  assertion for controlled local acceptance;
- `test_part_d_temperature_numeric_baseline` requires five ignored Part D
  temperature matrices produced by the licensed DJI SDK extraction workflow;
- `test_normal_part_c_pilot_adapter_builds_versioned_manifest` requires one of
  those ignored Part D temperature matrices;
- the two methods in `V032PilotLUHKWiringTests` require the same ignored matrix
  during their shared pilot-adapter setup.

These tests keep their original scientific assertions and remain runnable in
the accepted reference environment:

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:MPLBACKEND = "Agg"
$env:MPLCONFIGDIR = "<unique-os-temporary-directory>\mpl"
.\.venv\Scripts\python.exe -m pytest -ra -p no:cacheprovider --basetemp "<unique-os-temporary-directory>\pytest"
```

Real DJI SDK extraction, TAT3 operation, interactive GUI acceptance, Excel
automation and rendered-workbook review, licensed or private real-data
execution, the full Part A through Part E production workflow, manual alignment
and surface-cover review, and comparison against the Phase 1 run-scoped
accepted artifacts remain controlled local acceptance. CI does not invoke or
upload any of those tools, inputs, reports, binaries, or outputs.

The Phase 1 record reports the controlled-local full suite as 117 passed. CI
does not replace that acceptance procedure; it provides the clean-clone safety
net that can run without private or proprietary inputs.

CI protects the same Part E row-count baseline through the tracked summary test
`test_pilot_part_e_row_counts_and_selected_numeric_summaries`. It verifies five
pilot images, 512 by 640 pixels per image, 1,638,400 total rows, and the
existing numerical summaries. Controlled local acceptance separately verifies
that the physical real Part E Parquet container has the same row count.
