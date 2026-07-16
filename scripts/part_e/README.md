# Part E implementation map

`run_part_e_pipeline.py` is the only supported orchestration entry point. The
numbered files below are the current formal implementation, ordered by their
first use in the end-to-end workflow:

| Stage | File | Purpose |
|---:|---|---|
| 00 | `00_audit_part_e_inputs.py` | Audit source matrices, masks, ambient values, orientation, and script namespace. |
| 01 | `01_build_pixel_delta_t_dataset.py` | Build the canonical full-pixel delta-T Parquet and compact image summary. |
| 02 | `02_build_pixel_analysis_samples.py` | Build deterministic spatially thinned pixel samples and coverage manifests. |
| 03 | `03_run_pixel_statistical_analysis.py` | Produce grouped summaries, exploratory tests, effect sizes, stability checks, and supporting figures. |
| 04 | `04_generate_pixel_delta_t_spectra.py` | Produce the formal numbered pixel-spectrum figure family and its source table. |
| 05 | `05_generate_pixel_spatial_figures.py` | Produce per-image spatial QA maps and panels. |
| 06 | `06_build_per_image_pixel_workbooks.py` | Build optional per-image Excel workbooks. |
| 07 | `07_build_main_excel_workbook.py` | Build the main compact statistical workbook. |
| 08 | `08_finalize_excel_workbooks.ps1` | Optionally finalize workbooks and native charts through Excel COM. |
| 09 | `09_export_excel_charts.py` | Invoke the Excel chart export step. |
| 10 | `10_validate_part_e_outputs.py` | Validate inputs, pixel artifacts, formal outputs, documentation, and namespace cleanliness. |
| 11 | `11_generate_part_e_report.py` | Generate the final spectrum-first Part E summary. |

Unnumbered files are shared implementation helpers:

- `part_e_pixel_common.py`: configuration, input loading, pixel labels,
  sampling, provenance, and output utilities.
- `excel_workbook_common.py` and `build_part_e_workbooks.mjs`: optional Excel
  construction helpers.

The superseded LUHK-cell aggregation workflow is not present in this directory.
It remains recoverable from Git history and the
`pre-e2e-validation-2026-07-15` tag.

## Storage boundary

- Reusable machine-readable pixel datasets and samples belong in
  `data/processed/part_e/`.
- The ambient manifest belongs in `data/metadata/`.
- Tables, QA, summaries, figures, and workbooks belong in `outputs/part_e/`.
- Large reproducible Parquets, per-image workbooks, and workbook previews stay
  local through `.gitignore`; compact formal deliverables are tracked.
