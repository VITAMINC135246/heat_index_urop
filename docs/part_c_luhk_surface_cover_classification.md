# Part C LUHK and Surface-Cover Classification

Part C prepares a reviewable pilot package for LUHK context and semi-automatic surface-cover classification. It starts from the accepted Part B Round 1.1 refined visible ROI and keeps the thermal image grid as the target grid for later temperature analysis.

## Inputs

- Accepted Part B alignment summary: `outputs/part_b/summaries/part_b_round1_1_alignment_summary.csv`
- Accepted refined visible ROI bounding boxes and transform matrices from Part B Round 1.1
- Pilot pair metadata: `data/metadata/part_b_pilot_pairs.csv`
- Visible camera profiles: `data/metadata/visible_camera_profiles.csv`
- DJI image metadata and approximate Part A footprint/grid outputs

## LUHK Context Method

LUHK is broad land-use context only. It is summarized from existing Part A approximate drone footprint/grid products using the thermal footprint cells in `data/processed/grids/pilot_luhk_aligned_10m_grid_cells.csv`.

The LUHK proportions are weighted by each grid cell's thermal overlap ratio. These summaries are approximate because the underlying drone footprints are metadata-based north-up rectangles, and Part B refined alignment is an image-space V/T alignment rather than a full georeferenced correction.

For visual review, Part C also writes LUHK overlays on:

- the thermal preview image
- the refined visible ROI resized to the thermal grid

These overlays are meant to show likely spatial mismatch or footprint uncertainty. They are not corrected georegistration products.

## Surface-Cover Method

Surface-cover review is prepared from the accepted refined visible ROI, not from LUHK. For each accepted pilot pair, the workflow:

1. Crops the refined visible ROI using the Part B Round 1.1 bounding box.
2. Resizes the refined ROI to the thermal image grid.
3. Runs SLIC superpixels on the thermal-grid-resized visible ROI.
4. Writes boundary overlays, average-color superpixel overlays, segment ID maps, numbered segment ID label maps, segment summary CSVs, annotation tables, and per-image class review sheets with legends.

The current SLIC settings are recorded in `outputs/part_c/summaries/part_c_round1_summary.md`.

The refined visible ROI and the thermal-grid-resized ROI should look visually similar. The difference is pixel grid: the first is the accepted visible-image crop, while the second is resampled to the thermal grid, usually `640x512`, for later per-thermal-pixel analysis.

Thermal images shown in Part C contact sheets are grayscale contrast previews only. The original thermal JPG files are not modified, and no thermal temperature values are extracted.

## Manual Review Requirement

The `suggested_class` values store the current baseline surface-cover candidates. The `manual_class` values start as a copy of `suggested_class` so reviewers only need to edit rows where they disagree.

Use the numbered segment ID maps in `outputs/part_c/superpixels/<image_id>/` to locate each `segment_id` before editing annotation CSVs. The quadrant label maps are the easiest view when the full label map is crowded.

Use the class review sheets in `outputs/part_c/surface_cover_review/<image_id>/` to see the current per-segment surface-cover classification overlay and legend for each image.

Manual reviewers should edit `manual_class` in `data/annotations/part_c/part_c_surface_cover_annotations.csv`. Set `review_status` to `Yes` only after checking a row; otherwise leave `Not yet`.

Allowed classes are listed in `data/annotations/part_c/surface_cover_classes.csv`.

## Outputs For Later Parts

Part C prepares review assets for later Part D and Part E work:

- Refined visible ROI images aligned to the thermal grid
- Segment ID maps on the thermal grid
- Numbered segment ID maps for manual review
- Segment summaries and annotation templates
- Per-image surface-cover class review sheets and legends
- Approximate LUHK context summaries

Part C does not create final masks. Final masks should only be generated after manual labels are reviewed and accepted.

## Restrictions

- Do not extract thermal temperature in Part C.
- Do not train CNN, U-Net, or any supervised model.
- Do not treat LUHK as surface cover.
- Do not treat superpixels as final labels.
- Do not ingest manual annotations yet.
- Do not generate final masks before manual review.

## Run

```bash
python scripts/part_c/01_prepare_round1_review.py
```
