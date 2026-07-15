# Part D TAT3-Parameter Temperature Extraction Summary

## Scope

- Extracted the five accepted pilot `_T.JPG` images.
- Required per-image SDK measurement parameters from `outputs/part_d/qa/tat3_parameter_audit/part_d_tat3_pilot_parameters.csv`.
- Used thermal temperature extraction only; no delta T modeling and no prediction modeling were run.
- Treated RGB thermal previews as visualization only, never as temperature data.
- The old placeholder/default-parameter extraction path is deprecated and is not used by this run.

## Tool Status

- DJI Thermal SDK status: available
- DJI Thermal SDK executable: `external DJI Thermal SDK path from ignored local config`
- DJI Thermal SDK root: `external DJI Thermal SDK path from ignored local config`
- ExifTool status: not available in this run
- Local SDK config: `config/part_d_sdk.local.json` (ignored by Git)

## Results

- Pilot images tested: 5
- Successful temperature matrices: 5
- Matrices aligned with Part C masks: 5
- Pilot input manifest: `outputs/part_d/summaries/part_d_tat3_parameter_pilot_input_manifest.csv`
- Extraction summary CSV: `outputs/part_d/summaries/part_d_tat3_parameter_temperature_extraction_summary.csv`
- Class QA CSV: `outputs/part_d/qa/part_d_tat3_parameter_class_temperature_qa.csv`
- Shadow QA CSV: `outputs/part_d/qa/part_d_tat3_parameter_shadow_temperature_qa.csv`

## Per Image

| image_id | status | ambient C | reflected C | emissivity | humidity % | shape | min C | max C | mean C | aligns | notes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| DJI_20260107143259_0005 | success | 11.0 | 11.0 | 0.95 | 50.0 | 512x640 | -17.569128 | 45.517204 | 14.280269 | yes | extracted and aligned; QA flags: outside_typical_surface_temperature_review_range |
| DJI_20260107143320_0007 | success | 10.6 | 10.6 | 0.95 | 50.0 | 512x640 | -22.298025 | 47.676201 | 16.311846 | yes | extracted and aligned; QA flags: outside_typical_surface_temperature_review_range |
| DJI_20260107143328_0008 | success | 10.5 | 10.5 | 0.95 | 50.0 | 512x640 | -24.257025 | 47.772148 | 16.052845 | yes | extracted and aligned; QA flags: outside_typical_surface_temperature_review_range |
| DJI_20260107143344_0009 | success | 9.9 | 9.9 | 0.95 | 50.0 | 512x640 | -23.785177 | 48.889641 | 16.105944 | yes | extracted and aligned; QA flags: outside_typical_surface_temperature_review_range |
| DJI_20260107143401_0011 | success | 9.9 | 9.9 | 0.95 | 50.0 | 512x640 | -29.153143 | 40.569206 | 16.039099 | yes | extracted and aligned; QA flags: outside_typical_surface_temperature_review_range |

## QA Boundary

The class and shadow summaries are QA statistics only. They are intended to confirm extraction, shape alignment, and review values before any later delta T analysis.

## Unresolved Setup Issues

- None for SDK extraction in this run.

## Recommended Next Steps

- Run the Part D sub-zero spatial QA on these TAT3-parameter matrices.
- Review remaining physically implausible extrema against TAT3 previews and source imagery.
- Keep the DJI SDK outside the repository and update only the ignored local config path if the SDK is moved.
- Proceed to delta T analysis only after accepting the TAT3-parameter extraction and QA outputs.

<!-- PART_D_TAT3_PARAMETER_SUBZERO_QA:START -->
## TAT3-Parameter Sub-Zero Spatial QA Addendum

This QA checked the current TAT3-parameter matrices only; the DJI Thermal SDK was not rerun.

- Summary: `outputs/part_d/summaries/part_d_tat3_parameter_subzero_spatial_qa_summary.md`
- Table: `outputs/part_d/qa/subzero_spatial_qa/summary/part_d_tat3_parameter_subzero_spatial_qa_summary.csv`
- Per-image QA image root: `outputs/part_d/qa/subzero_spatial_qa`
- PNG visual QA outputs are reproducible local artifacts and are not part of the default tracked checkpoint.
- All five matrices remained readable and structurally aligned with Part C masks.
- Remaining sub-zero pixels are documented for physical plausibility review, not as final physical interpretation.
<!-- PART_D_TAT3_PARAMETER_SUBZERO_QA:END -->
