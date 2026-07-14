# Part C LUHK and Surface-Cover Classification

Part C prepares manually reviewed physical surface-cover masks and separate shadow masks for the five accepted pilot visible/thermal pairs. It uses the accepted Part B Round 1.1 refined visible ROI as the spatial source and keeps the thermal image grid as the target grid for later Part D temperature analysis.

Part C does not extract thermal temperature values, calculate temperature differences, or train a supervised model.

## Current Stage

Round 1 generated LUHK context, refined ROI review images, SLIC superpixels, segment ID maps, annotation workbooks, and surface-cover review sheets.

Round 1.1 ingests the manually reviewed annotation workbook:

`data/annotations/part_c/part_c_surface_cover_annotations.xlsx`

The reviewed labels are converted into final thermal-grid-aligned physical surface-cover masks and separate binary shadow masks. The current final-mask manifest is:

`outputs/part_c/summaries/part_c_final_mask_manifest.xlsx`

## Inputs

- Accepted Part B alignment summary: `outputs/part_b/summaries/part_b_round1_1_alignment_summary.xlsx`
- Part C Round 1 summary: `outputs/part_c/summaries/part_c_round1_summary.xlsx`
- Pilot pair metadata: `data/metadata/part_b_pilot_pairs.xlsx`
- Manual annotation workbook: `data/annotations/part_c/part_c_surface_cover_annotations.xlsx`
- LUHK context summary: `outputs/part_c/summaries/part_c_luhk_context_summary.xlsx`

## LUHK Context

LUHK is broad land-use context only. It is summarized from existing Part A approximate drone footprint/grid products using the thermal footprint cells in:

`data/processed/grids/pilot_luhk_aligned_10m_grid_cells.xlsx`

LUHK proportions are weighted by each grid cell's thermal overlap ratio. These summaries remain approximate because the underlying drone footprints are metadata-based north-up rectangles, while Part B refined alignment is an image-space visible/thermal correction rather than a full georeferenced correction.

LUHK outputs should not be treated as physical surface cover. They provide context for interpreting the manually reviewed surface-cover masks.

## Physical Surface-Cover Classes

Allowed physical classes are stored in:

- `data/annotations/part_c/surface_cover_classes.xlsx`
- `data/annotations/part_c/surface_cover_class_mapping.xlsx`

Current final class IDs are:

| class_id | class_name |
| --- | --- |
| 0 | no_data_unreviewed |
| 1 | roof |
| 2 | concrete_pavement |
| 3 | asphalt_road |
| 4 | vegetation_tree |
| 5 | grass_low_vegetation |
| 6 | bare_soil |
| 7 | water |
| 8 | vehicle_temporary_object |
| 9 | unclear_ignore |

`shadow` is not a physical surface-cover class. If an area is shaded but the physical cover is still interpretable, keep the physical cover in `manual_class` and set `shadow_status` to `1`.

## Shadow Status

Shadow is stored separately as a binary flag:

- `0`: no_shadow
- `1`: shadow_present

The mapping is stored in:

`data/annotations/part_c/shadow_flag_mapping.xlsx`

Final shadow masks are generated separately from physical surface-cover masks, so later analysis can compare physical cover with and without shadow filtering.

## Manual Annotation Rules

The main reviewed table is:

`data/annotations/part_c/part_c_surface_cover_annotations.xlsx`

Required columns are:

- `pair_id`
- `segment_id`
- `suggested_class`
- `manual_class`
- `shadow_status`
- `confidence`
- `review_status`
- `notes`

For current reviewed outputs, `manual_class` is the authoritative physical class. `suggested_class` is retained as the baseline candidate label. `review_status` is restricted to `Not yet` and `Yes`; current final masks should only be used when the relevant rows have been reviewed.

## Final Mask Outputs

Final masks are written under:

`outputs/part_c/masks/<image_id>/`

Each image directory contains:

- thermal-grid physical class ID masks as PNG and NPY
- visible-ROI-resampled physical class ID masks as PNG and NPY
- physical class color previews
- overlays on thermal preview, refined visible ROI, and refined visible ROI resized to the thermal grid
- thermal-grid and visible-ROI shadow flag masks as PNG and NPY
- shadow previews and overlays
- a class legend
- one final contact sheet for manual review

The best first image to inspect per pair is:

`outputs/part_c/masks/<image_id>/<image_id>_final_mask_contact_sheet.png`

## Summary Outputs

- `outputs/part_c/summaries/part_c_manual_annotation_validation.xlsx`: validation checks for the reviewed annotation workbook
- `outputs/part_c/summaries/part_c_manual_annotation_validation.md`: compact validation report
- `outputs/part_c/summaries/part_c_final_mask_manifest.xlsx`: one row per pilot pair with all final mask paths
- `outputs/part_c/summaries/part_c_surface_cover_summary.xlsx`: per-image physical surface-cover area summaries
- `outputs/part_c/summaries/part_c_shadow_flag_summary.xlsx`: per-image shadow flag summaries
- `outputs/part_c/summaries/part_c_luhk_surface_cover_combined_summary.xlsx`: combined LUHK, surface-cover, and shadow summary
- `outputs/part_c/summaries/part_c_round3_final_mask_generation_summary.md`: run report for the latest final-mask generation
- `outputs/part_c/summaries/part_c_round1_1_method_update.md`: short method update

## Scripts

Round 1 review package:

```bash
python scripts/part_c/01_prepare_round1_review.py
```

Baseline prefill and per-segment review overlays:

```bash
python scripts/part_c/02_prefill_surface_cover_annotations.py
```

Final validation, mask generation, and summaries after manual review:

```bash
python scripts/part_c/03_generate_final_masks_and_summaries.py
```

Do not rerun Round 1 scripts after manual review unless the annotation workbooks have been backed up and the intent is to rebuild the review package.

## Restrictions

- Do not redo Part A or Part B for this step.
- Do not redo Part C Round 1 segmentation unless an input is missing or intentionally replaced.
- Do not treat LUHK as physical surface cover.
- Do not use `shadow` as a physical surface-cover label.
- Do not extract thermal temperature or calculate delta T in Part C.
- Do not train CNN, U-Net, or other supervised models in Part C.
