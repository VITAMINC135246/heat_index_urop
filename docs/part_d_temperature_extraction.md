# Part D Temperature Extraction

Part D extracts pixel-level temperature matrices from the accepted pilot DJI thermal `_T.JPG` images and checks alignment with the Part C thermal-grid masks.

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

## Current Tool Check

- DJI Thermal SDK status: `available`
- DJI Thermal SDK root: `external DJI Thermal SDK path from ignored local config`
- `dji_irp.exe`: `external DJI Thermal SDK path from ignored local config`
- ExifTool: not found on PATH or known local paths during this run

## Extraction Command

```powershell
.\.venv\Scripts\python.exe scripts\part_d\01_extract_temperature_matrices.py
```

The script calls DJI `dji_irp.exe` with `-a measure --measurefmt float32`, reads the raw float32 output, reshapes it to the thermal grid from `data/metadata/part_b_pilot_pairs.xlsx`, and saves Celsius matrices.

Default measurement parameters are explicit in the config template:

- distance: 5.0 m
- relative humidity: 70 percent
- emissivity: 1.0
- ambient temperature: 25 C
- reflected temperature: 23 C

These defaults should be reviewed before final analysis. Existing metadata inspection did not provide reliable per-image emissivity, object distance, reflected temperature, humidity, or temperature unit values for the pilot images.

## Outputs

- Temperature matrices: `data/processed/part_d/temperature_matrices/`
- Preview PNGs: `outputs/part_d/previews/`
- QA tables: `outputs/part_d/qa/`
- Round 1 summaries: `outputs/part_d/summaries/`

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
- Summary: `outputs/part_d/summaries/part_d_round1_temperature_extraction_summary.md`
- Summary CSV: `outputs/part_d/summaries/part_d_round1_temperature_extraction_summary.csv`

## Limitations

- Thermal extraction depends on DJI R-JPEG radiometric support in the external SDK.
- The SDK readme for this installed version lists several supported cameras but also includes M4T sample data; pilot M4T extraction is accepted only if `dji_irp.exe` succeeds and QA values are plausible.
- Measurement parameters may materially affect temperature values and should be confirmed for final work.
- No delta T, statistical modeling, or prediction modeling is performed in Part D Round 1.

<!-- PART_D_ROUND_1_1_SUBZERO_QA:START -->
## Round 1.1 Sub-Zero Spatial QA

Round 1.1 locates and documents extracted temperature pixels below 0 deg C. It does not validate radiometric parameters and does not calculate delta T.

Confirmed in Round 1 / Round 1.1:

- Extraction succeeded for all five pilot images.
- Temperature matrices are `512x640` and structurally compatible with the Part C physical-cover and shadow masks.
- Sub-zero pixels were located, quantified, and visualized.
- QA statuses from Round 1.1: warn=5, fail=0.
- Summary: `outputs/part_d/summaries/part_d_round1_1_subzero_spatial_qa_summary.md`

Not yet validated:

- emissivity
- reflected apparent temperature
- atmospheric temperature
- relative humidity
- object distance
- SDK default versus embedded parameters
- physical plausibility of apparent temperatures
- whether any matrices must be re-extracted
- suitability for final delta T analysis

Full radiometric and parameter validation is deferred to Part D Round 2.
<!-- PART_D_ROUND_1_1_SUBZERO_QA:END -->
