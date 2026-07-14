# Part B Round 1 Outputs Status

Status: preserved, not accepted as final Part B alignment

Part B Round 1 generated useful review material for five HKUST pilot V/T pairs:

- `outputs/part_b/review_packages/<image_id>/`
- `outputs/part_b/overlays/`
- `outputs/part_b/superpixels/`
- `outputs/part_b/summaries/part_b_round1_summary.md`
- `outputs/part_b/summaries/part_b_round1_roi_estimates.xlsx`
- `outputs/part_b/summaries/part_b_round1_segments.xlsx`
- `data/metadata/part_b_pilot_pairs.xlsx`
- `data/metadata/visible_camera_profiles.xlsx`
- `data/annotations/surface_cover_classes.xlsx`
- `data/annotations/part_b_round1_segment_annotations.xlsx`
- `data/annotations/part_b_round1/*_segment_annotation_template.xlsx`

The review packages are preserved because they are useful visual diagnostics.
The superpixel outputs and annotation XLSX templates were generated early. They
are preserved for future Part C preparation, but they should not be treated as
accepted Part B deliverables.

The current Part B alignment is not accepted yet. Round 1 used
`metadata_fov_center_crop` with medium confidence, and visual inspection showed
that the visible ROI and thermal image are close but slightly misaligned.

Part B Round 1.1 is therefore the active next step. It refines V/T alignment
and thermal ROI for the same five pilot pairs, produces before/after review
figures, records automatic alignment attempts, and prepares manual GCP fallback
templates where automatic cross-modal alignment is not reliable enough.

Do not continue surface-cover annotation, convert superpixels to masks, extract
temperature values, or start Part C officially until Part B alignment is
accepted.
