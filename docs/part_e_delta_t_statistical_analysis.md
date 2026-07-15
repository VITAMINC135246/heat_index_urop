# Part E Delta-T Statistical Analysis And Visualization

Part E is the provisional pilot stage for delta-T calculation, descriptive
statistical analysis, and visualization. It is not a prediction-modeling stage.

> This is a provisional pilot delta-T analysis using temperature matrices that
> have completed structural extraction QA but have not yet completed full
> radiometric parameter validation.

## Analysis Units

The primary analysis unit is a thermal image by LUHK-aligned 10 m cell
observation:

```text
image_id + cell_id
```

The secondary analysis unit is a thermal image by LUHK-aligned 10 m cell by
physical surface-cover class observation:

```text
image_id + cell_id + physical_surface_cover_class
```

Individual thermal pixels are not treated as independent statistical
observations. Pixels are aggregated before delta-T is calculated.

## Delta-T Formula

For thermal image `i` and LUHK-aligned cell `c`:

```text
mean_surface_temperature_c(i, c) = mean of valid thermal pixels inside that cell
delta_t_c(i, c) = mean_surface_temperature_c(i, c) - ambient_temperature_c(i)
```

For physical surface-cover class `s` inside cell `c`:

```text
mean_surface_temperature_c(i, c, s) =
  mean of valid thermal pixels classified as surface-cover s inside that cell

delta_t_c(i, c, s) =
  mean_surface_temperature_c(i, c, s) - ambient_temperature_c(i)
```

The ambient temperature is a single scalar assigned to the acquisition time of
each thermal image. All cells and surface-cover observations from the same
thermal image use that same image-level ambient temperature.

## Data Layers

- LUHK official land-use context: existing LUHK-aligned 10 m cell IDs and
  official LUHK raster classes.
- Physical surface-cover classification: reviewed Part C thermal-grid masks.
- Shadow state: separate binary `shadow_flag`, where `1 = shadow` and
  `0 = non-shadow`.
- Surface temperature: extracted Part D temperature matrix values.
- Ambient temperature: external or recorded image-level scalar value.
- Delta-T: aggregated surface temperature minus image-level ambient
  temperature.

## Ambient-Temperature Requirement

Part E cannot calculate real delta-T until every pilot image has exactly one
documented ambient-temperature value. The current accepted source for the five
pilot images is the TAT3 parameter ingest table:

```text
outputs/part_d/qa/tat3_parameter_audit/part_d_tat3_pilot_parameters.csv
```

The older Part D placeholder SDK setting `ambient_temperature_c = 25 C` is
deprecated and is not used by the active extraction workflow. If a later
project-approved source, such as an on-site sensor or weather-station
observation, supersedes the TAT3 ambient values, that replacement must be
documented before Part E is rerun.

Input template:

```text
data/metadata/part_e_pilot_ambient_temperature_manifest_template.csv
```

Copy or derive the TAT3 ambient values into
`data/metadata/part_e_pilot_ambient_temperature_manifest.csv` for a local run.
The populated working manifest and all generated `outputs/part_e/` products
remain ignored while Part E is exploratory.

## Current Shadow Limitation

The Part E code keeps shadow structurally available through cell-level and
surface-cover-level shadow fractions. The current five pilot shadow masks
contain no `shadow_flag = 1` pixels, so the current pilot cannot estimate a
shadow effect and should not include shadow comparison figures.

## Reproducibility

```powershell
.\.venv\Scripts\python.exe scripts\part_e\00_create_ambient_temperature_manifest_template.py
.\.venv\Scripts\python.exe scripts\part_e\01_build_cell_delta_t_dataset.py
.\.venv\Scripts\python.exe scripts\part_e\02_build_surface_cover_delta_t_dataset.py
.\.venv\Scripts\python.exe scripts\part_e\03_generate_summary_tables.py
.\.venv\Scripts\python.exe scripts\part_e\04_run_exploratory_statistics.py
.\.venv\Scripts\python.exe scripts\part_e\05_create_figures.py
```

The dataset, summary, statistics, and figure commands intentionally stop until
the ambient manifest contains one documented numeric ambient value per pilot
image.
