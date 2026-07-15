# Part D TAT3-Parameter Sub-Zero Spatial QA Summary

## Scope

- Located and quantified valid pixels with extracted temperature below 0 deg C, below -5 deg C, and below -10 deg C.
- Checked matrix, thermal JPG, physical surface-cover mask, and shadow mask shape compatibility.
- Generated spatial QA images for the current TAT3-parameter temperature matrices.
- Did not run delta T analysis, 10 m aggregation, or modeling.

## Definitions

- Expected matrix shape: `512x640` rows x columns.
- Near image edge: within `5` pixels of any image border.
- Connected components: 8-connected components on valid temperature pixels below 0 deg C.
- Shadow state is interpreted only as `0 = non-shadow`, `1 = shadow`.

## Per-Image Findings

| image_id | QA | <0 px (%) | <-5 px (%) | <-10 px (%) | min C | pattern | dominant <0 class | edge fraction | shadow fraction | orientation/alignment |
|---|---:|---:|---:|---:|---:|---|---|---:|---:|---|
| DJI_20260107143259_0005 | warn | 95 (0.029%) | 41 (0.013%) | 30 (0.009%) | -17.569128 | mixed | roof | 0.000 | 0.000 | none_detected_by_shape_and_JPG_intensity_diagnostic |
| DJI_20260107143320_0007 | warn | 130 (0.040%) | 105 (0.032%) | 80 (0.024%) | -22.298025 | mixed | roof | 0.000 | 0.000 | none_detected_by_shape_and_JPG_intensity_diagnostic |
| DJI_20260107143328_0008 | warn | 222 (0.068%) | 168 (0.051%) | 108 (0.033%) | -24.257025 | mixed | roof | 0.000 | 0.000 | none_detected_by_shape_and_JPG_intensity_diagnostic |
| DJI_20260107143344_0009 | warn | 713 (0.218%) | 505 (0.154%) | 345 (0.105%) | -23.785177 | mixed | roof | 0.000 | 0.000 | none_detected_by_shape_and_JPG_intensity_diagnostic |
| DJI_20260107143401_0011 | warn | 4665 (1.424%) | 3501 (1.068%) | 2524 (0.770%) | -29.153143 | mixed | roof | 0.026 | 0.000 | none_detected_by_shape_and_JPG_intensity_diagnostic |

## Overall Result

- QA statuses: pass=0, warn=5, fail=0.
- Total valid pixels: 1638400.
- Total below 0 deg C pixels: 5825 (0.355530% of valid).
- Total below -5 deg C pixels: 4320 (0.263672% of valid).
- Total below -10 deg C pixels: 3087 (0.188416% of valid).
- Coordinates below 0 deg C in all five images: 0.
- Coordinates below 0 deg C in exactly two images: 18.

## Structural QA

- No obvious shape, transpose, flip, image-size, or mask-compatibility failure was detected by this QA.

## Baseline QA Status

- TAT3-parameter matrices are structurally acceptable for the next review step.
- Rationale: all five matrices are readable, `512x640`, structurally aligned with Part C masks, and no obvious flip, transpose, corruption, or unit-scale failure was detected.
- Remaining sub-zero extrema are documented for physical plausibility review before delta T analysis.

## Outputs

- Summary CSV: `outputs/part_d/qa/subzero_spatial_qa/summary/part_d_tat3_parameter_subzero_spatial_qa_summary.csv`
- Summary XLSX: `outputs/part_d/qa/subzero_spatial_qa/summary/part_d_tat3_parameter_subzero_spatial_qa_summary.xlsx`
- Physical class breakdown: `outputs/part_d/qa/subzero_spatial_qa/summary/part_d_tat3_parameter_subzero_by_physical_class.csv`
- Shadow-state breakdown: `outputs/part_d/qa/subzero_spatial_qa/summary/part_d_tat3_parameter_subzero_by_shadow_state.csv`
- Recurring coordinate summary: `outputs/part_d/qa/subzero_spatial_qa/summary/part_d_tat3_parameter_recurring_subzero_coordinates.csv`
- Overall contact sheet: `outputs/part_d/qa/subzero_spatial_qa/summary/part_d_tat3_parameter_subzero_overall_contact_sheet.png`
- Per-image QA images: `outputs/part_d/qa/subzero_spatial_qa/<image_id>/`
- PNG visual QA outputs are reproducible local artifacts and remain ignored by default; compact CSV/XLSX/Markdown outputs carry the tracked checkpoint record.

## Reproducibility

```powershell
.\.venv\Scripts\python.exe scripts\part_d\02_qa_subzero_temperature_pixels.py
```

## Still Deferred

- physical plausibility of apparent temperatures
- suitability for final delta T analysis
