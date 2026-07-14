# Part D Round 1 Temperature Extraction Summary

## Scope

- Tested the five accepted pilot `_T.JPG` images.
- Used thermal temperature extraction only; no delta T modeling and no prediction modeling were run.
- Treated RGB thermal previews as visualization only, never as temperature data.

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
- Pilot input manifest: `outputs/part_d/summaries/part_d_round1_pilot_input_manifest.csv`
- Extraction summary CSV: `outputs/part_d/summaries/part_d_round1_temperature_extraction_summary.csv`
- Class QA CSV: `outputs/part_d/qa/part_d_round1_class_temperature_qa.csv`
- Shadow QA CSV: `outputs/part_d/qa/part_d_round1_shadow_temperature_qa.csv`

## Per Image

| image_id | status | shape | min C | max C | mean C | aligns with Part C masks | notes |
|---|---:|---:|---:|---:|---:|---:|---|
| DJI_20260107143259_0005 | success | 512x640 | -19.389074 | 42.374504 | 11.728144 | yes | extracted and aligned; QA flags: outside_typical_surface_temperature_review_range |
| DJI_20260107143320_0007 | success | 512x640 | -24.187902 | 44.43914 | 13.63475 | yes | extracted and aligned; QA flags: outside_typical_surface_temperature_review_range |
| DJI_20260107143328_0008 | success | 512x640 | -26.157614 | 44.515831 | 13.364334 | yes | extracted and aligned; QA flags: outside_typical_surface_temperature_review_range |
| DJI_20260107143344_0009 | success | 512x640 | -25.896322 | 45.51281 | 13.299032 | yes | extracted and aligned; QA flags: outside_typical_surface_temperature_review_range |
| DJI_20260107143401_0011 | success | 512x640 | -31.229254 | 37.284782 | 13.23331 | yes | extracted and aligned; QA flags: outside_typical_surface_temperature_review_range |

## QA Boundary

The class and shadow summaries are QA statistics only. They are intended to confirm extraction, shape alignment, and plausible values before any later delta T analysis.

## Unresolved Setup Issues

- None for SDK extraction in this run.

## Recommended Next Steps

- Review the preview PNGs and QA tables for physically implausible values.
- Confirm measurement parameters such as emissivity, distance, humidity, ambient temperature, and reflected temperature before final analysis.
- Keep the DJI SDK outside the repository and update only the ignored local config path if the SDK is moved.
- Proceed to delta T analysis only after accepting these extraction outputs.

<!-- PART_D_ROUND_1_1_SUBZERO_QA:START -->
## Round 1.1 Sub-Zero Spatial QA Addendum

Round 1.1 checked the existing extracted matrices only; the DJI Thermal SDK was not rerun.

- Summary: `outputs/part_d/summaries/part_d_round1_1_subzero_spatial_qa_summary.md`
- Table: `outputs/part_d/qa/subzero_spatial_qa/summary/part_d_round1_1_subzero_spatial_qa_summary.csv`
- Per-image QA image root: `outputs/part_d/qa/subzero_spatial_qa`
- PNG visual QA outputs are reproducible local artifacts and are not part of the default tracked checkpoint.
- All five matrices remained readable and structurally aligned with Part C masks.
- Sub-zero pixels are documented as a Round 2 radiometric-validation issue, not as final physical interpretation.
<!-- PART_D_ROUND_1_1_SUBZERO_QA:END -->
