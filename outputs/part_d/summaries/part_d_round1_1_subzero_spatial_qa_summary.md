# Part D Round 1.1 Sub-Zero Spatial QA Summary

## Scope

- Located and quantified valid pixels with extracted temperature below 0 deg C, below -5 deg C, and below -10 deg C.
- Checked matrix, thermal JPG, physical surface-cover mask, and shadow mask shape compatibility.
- Generated spatial QA images without rerunning the DJI Thermal SDK.
- Did not run delta T analysis, radiometric parameter validation, 10 m aggregation, or modeling.

## Definitions

- Expected matrix shape: `512x640` rows x columns.
- Near image edge: within `5` pixels of any image border.
- Connected components: 8-connected components on valid temperature pixels below 0 deg C.
- Shadow state is interpreted only as `0 = non-shadow`, `1 = shadow`.

## Per-Image Findings

| image_id | QA | <0 px (%) | <-5 px (%) | <-10 px (%) | min C | pattern | dominant <0 class | edge fraction | shadow fraction | orientation/alignment |
|---|---:|---:|---:|---:|---:|---|---|---:|---:|---|
| DJI_20260107143259_0005 | warn | 128 (0.039%) | 51 (0.016%) | 33 (0.010%) | -19.389074 | mixed | roof | 0.000 | 0.000 | none_detected_by_shape_and_JPG_intensity_diagnostic |
| DJI_20260107143320_0007 | warn | 140 (0.043%) | 116 (0.035%) | 90 (0.027%) | -24.187902 | mixed | roof | 0.000 | 0.000 | none_detected_by_shape_and_JPG_intensity_diagnostic |
| DJI_20260107143328_0008 | warn | 285 (0.087%) | 183 (0.056%) | 129 (0.039%) | -26.157614 | mixed | roof | 0.000 | 0.000 | none_detected_by_shape_and_JPG_intensity_diagnostic |
| DJI_20260107143344_0009 | warn | 828 (0.253%) | 585 (0.179%) | 417 (0.127%) | -25.896322 | mixed | roof | 0.001 | 0.000 | none_detected_by_shape_and_JPG_intensity_diagnostic |
| DJI_20260107143401_0011 | warn | 5309 (1.620%) | 4014 (1.225%) | 2953 (0.901%) | -31.229254 | mixed | roof | 0.025 | 0.000 | none_detected_by_shape_and_JPG_intensity_diagnostic |

## Overall Result

- QA statuses: pass=0, warn=5, fail=0.
- Total valid pixels: 1638400.
- Total below 0 deg C pixels: 6690 (0.408325% of valid).
- Total below -5 deg C pixels: 4949 (0.302063% of valid).
- Total below -10 deg C pixels: 3622 (0.221069% of valid).
- Coordinates below 0 deg C in all five images: 0.
- Coordinates below 0 deg C in exactly two images: 45.

## Structural QA

- No obvious shape, transpose, flip, image-size, or mask-compatibility failure was detected by this QA.

## Checkpoint Recommendation

- Recommend checkpointing Part D Round 1 after review.
- Rationale: all five matrices are readable, `512x640`, structurally aligned with Part C masks, and no obvious flip, transpose, corruption, or unit-scale failure was detected.
- The sub-zero anomaly is documented and should be carried into Part D Round 2 radiometric validation.
- Suggested commit message: `Complete Part D Round 1 extraction and sub-zero spatial QA`.

## Outputs

- Summary CSV: `outputs/part_d/qa/subzero_spatial_qa/summary/part_d_round1_1_subzero_spatial_qa_summary.csv`
- Summary XLSX: `outputs/part_d/qa/subzero_spatial_qa/summary/part_d_round1_1_subzero_spatial_qa_summary.xlsx`
- Physical class breakdown: `outputs/part_d/qa/subzero_spatial_qa/summary/part_d_round1_1_subzero_by_physical_class.csv`
- Shadow-state breakdown: `outputs/part_d/qa/subzero_spatial_qa/summary/part_d_round1_1_subzero_by_shadow_state.csv`
- Recurring coordinate summary: `outputs/part_d/qa/subzero_spatial_qa/summary/part_d_round1_1_recurring_subzero_coordinates.csv`
- Overall contact sheet: `outputs/part_d/qa/subzero_spatial_qa/summary/part_d_round1_1_subzero_overall_contact_sheet.png`
- Per-image QA images: `outputs/part_d/qa/subzero_spatial_qa/<image_id>/`
- PNG visual QA outputs are reproducible local artifacts and remain ignored by default; compact CSV/XLSX/Markdown outputs carry the tracked checkpoint record.

## Reproducibility

```powershell
.\.venv\Scripts\python.exe scripts\part_d\02_qa_subzero_temperature_pixels.py
```

## Deferred To Part D Round 2

- emissivity
- reflected apparent temperature
- atmospheric temperature
- relative humidity
- object distance
- SDK default versus embedded measurement parameters
- physical plausibility of apparent temperatures
- whether any image must be re-extracted
- suitability for final delta T analysis
