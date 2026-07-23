# Part D Temperature Extraction

Part D extracts pixel-level temperature matrices from the accepted pilot DJI thermal `_T.JPG` images with per-image TAT3 report parameters and checks alignment with the Part C thermal-grid masks.

## Dependency Rule

Do not copy DJI Thermal SDK binaries into this repository. Install or unzip the SDK outside the repo, for example under `D:\DJI_Thermal_SDK`, and point the project to it with an ignored local config file.

Tracked template:

```powershell
config\part_d_sdk.template.json
```

Ignored local config used on this machine:

```powershell
config\part_d_sdk.local.json
```

The script also accepts `--sdk-root`, `--irp-exe`, `DJI_THERMAL_SDK_ROOT`, or `DJI_IRP_EXE`.

## TAT3 Parameter Requirement

Before extracting temperature matrices, parse exported TAT3 reports:

```powershell
.\.venv\Scripts\python.exe scripts\part_d\03_parse_tat3_ambient_temperature_reports.py
```

The extraction script requires `outputs/part_d/qa/tat3_parameter_audit/part_d_tat3_pilot_parameters.csv` and fails before SDK extraction if any accepted pilot image lacks a corresponding TAT3 parameter row.

Required SDK-driving fields:

- distance_m
- emissivity
- ambient_temperature_c
- reflected_temperature_c

`humidity_percent` is passed to the SDK for reproducibility because it is part of the TAT3/embedded parameter set, but it is not interpreted as reliable field humidity for analysis.

## Current Tool Check

- DJI Thermal SDK status: `available`
- DJI Thermal SDK root: `external DJI Thermal SDK path from ignored local config`
- `dji_irp.exe`: `external DJI Thermal SDK path from ignored local config`
- ExifTool: not found on PATH or known local paths during this run

## Extraction Command

```powershell
.\.venv\Scripts\python.exe scripts\part_d\01_extract_temperature_matrices.py
```

The script calls DJI `dji_irp.exe` with `-a measure --measurefmt float32` and per-image TAT3 parameters, reads the raw float32 output, reshapes it to the thermal grid from `data/metadata/part_b_pilot_pairs.xlsx`, and saves Celsius matrices.

The deprecated placeholder/default-parameter path is not used. In particular, the old `ambient_temperature_c = 25 C` and `reflected_temperature_c = 23 C` settings are no longer part of the active extraction logic.

## Outputs

- Temperature matrices: `data/processed/part_d/temperature_matrices/`
- Preview PNGs: `outputs/part_d/previews/`
- QA tables: `outputs/part_d/qa/`
- Summaries: `outputs/part_d/summaries/`

For each successful pilot image, the workflow writes `.npy`, optional matrix `.csv`, preview `.png`, and extraction metadata `.json` files.

## QA Checks

- Matrix shape matches the expected thermal grid.
- Part C physical surface-cover mask shape matches the temperature matrix.
- Part C `shadow_flag` mask shape matches the temperature matrix.
- Temperature values are finite, non-constant, non-zero, and within a broad Celsius plausibility range.
- Values outside a typical surface-temperature review range, such as below 0 C or above 80 C, are flagged for manual QA.
- Integer-like 0 to 255 preview values are flagged as suspicious.

The class and shadow summaries are QA statistics only. They are not final delta T analysis.

## Current Run

- Successful matrices: 5/5
- Summary: `outputs/part_d/summaries/part_d_tat3_parameter_temperature_extraction_summary.md`
- Summary CSV: `outputs/part_d/summaries/part_d_tat3_parameter_temperature_extraction_summary.csv`
- TAT3 pilot parameter table: `outputs/part_d/qa/tat3_parameter_audit/part_d_tat3_pilot_parameters.csv`

## Limitations

- Thermal extraction depends on DJI R-JPEG radiometric support in the external SDK.
- The SDK readme for this installed version lists several supported cameras but also includes M4T sample data; pilot M4T extraction is accepted only if `dji_irp.exe` succeeds and QA values are plausible.
- TAT3-derived humidity is retained for SDK reproducibility but is not treated as reliable field humidity.
- No delta T, statistical modeling, or prediction modeling is performed by this extraction script.

<!-- PART_D_TAT3_PARAMETER_SUBZERO_QA:START -->
## TAT3-Parameter Sub-Zero Spatial QA

This QA locates and documents extracted temperature pixels below 0 deg C after the canonical TAT3-parameter extraction. It does not calculate delta T.

Confirmed for the current TAT3-parameter matrices:

- Extraction succeeded for all five pilot images.
- Temperature matrices are `512x640` and structurally compatible with the Part C physical-cover and shadow masks.
- Sub-zero pixels were located, quantified, and visualized.
- QA statuses: warn=5, fail=0.
- Summary: `outputs/part_d/summaries/part_d_tat3_parameter_subzero_spatial_qa_summary.md`

Still requiring review before delta T:

- physical plausibility of apparent temperatures
- suitability for final delta T analysis

The old placeholder/default-parameter extraction is deprecated and should not be used for downstream analysis.
<!-- PART_D_TAT3_PARAMETER_SUBZERO_QA:END -->

## Version 0.1 canonical adapter

Temperature extraction is now separable from label availability. The existing
TAT3-parameter DJI SDK route is reused for new R-JPEGs, while explicit NPY and
verified pilot matrices are supported adapters. Native dimensions are derived
from the matrix; surface-cover and shadow masks are optional layers with strict
shape checks. Unknown labels are never invented, and a Part C* result does not
require a shadow mask. Full matrix CSV output is disabled unless explicitly
requested.
# Version 0.2 shared implementation

The numbered batch script and persistent workflow call
`scripts/workflow/temperature_extraction.py` for the preserved DJI
`measure/float32` command and QA. TAT3 distance, humidity, emissivity, ambient,
and reflection parameters remain unchanged. NPY overrides require native shape
compatibility. Missing ambient retains temperature but disables delta-T; failed
QA never enters the successful index or Part E.
