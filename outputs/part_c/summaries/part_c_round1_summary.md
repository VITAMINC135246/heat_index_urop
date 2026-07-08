# Part C Round 1 Summary

Part C Round 1 prepares LUHK context and semi-automatic surface-cover review outputs for the five accepted Part B pilot pairs.

No thermal temperature extraction, supervised model training, manual annotation ingestion, or final mask generation was performed.

## Inputs From Accepted Part B

- Alignment summary: `outputs/part_b/summaries/part_b_round1_1_alignment_summary.csv`
- Accepted refined ROI columns: `refined_roi_*`, `final_transform_matrix_json`
- Visible camera profiles: `data/metadata/visible_camera_profiles.csv`
- Thermal metadata table: `data/metadata/dji_image_metadata.csv`

## Segmentation Parameters

- Method: `skimage.segmentation.slic`
- Requested segments: `220`
- Compactness: `12.0`
- Sigma: `1.0`
- Image basis: `refined_visible_roi_resized_to_thermal_grid`

## Image Interpretation Notes

- Thermal preview images are grayscale contrast previews only; the original thermal JPG files are not modified.
- `refined_visible_roi` is the accepted Part B crop at visible-image pixels.
- `refined_visible_roi_resized_to_thermal_grid` is the same crop resampled to the thermal image grid, usually `640x512`; it should look visually similar in contact sheets.
- LUHK image overlays use approximate metadata-based thermal footprints, so they are for uncertainty review rather than precise surface-cover labeling.

## Pair Outputs To Inspect

### DJI_20260107143259_0005

- Dominant LUHK context: `GIC / open space` (0.679465)
- LUHK overlay contact sheet: `outputs/part_c/luhk_context/DJI_20260107143259_0005/DJI_20260107143259_0005_luhk_overlay_contact_sheet.png`
- Refined ROI: `outputs/part_c/surface_cover_review/DJI_20260107143259_0005/DJI_20260107143259_0005_refined_visible_roi.png`
- Thermal-grid ROI: `outputs/part_c/surface_cover_review/DJI_20260107143259_0005/DJI_20260107143259_0005_refined_visible_roi_resized_to_thermal_grid.png`
- Review contact sheet: `outputs/part_c/surface_cover_review/DJI_20260107143259_0005/DJI_20260107143259_0005_part_c_review_contact_sheet.png`
- Segmentation contact sheet: `outputs/part_c/superpixels/DJI_20260107143259_0005/DJI_20260107143259_0005_segmentation_contact_sheet.png`
- Segment ID full map: `outputs/part_c/superpixels/DJI_20260107143259_0005/DJI_20260107143259_0005_segment_id_labels_full.png`
- Segment ID quadrant map: `outputs/part_c/superpixels/DJI_20260107143259_0005/DJI_20260107143259_0005_segment_id_labels_quadrants.png`
- Segment summary: `outputs/part_c/superpixels/DJI_20260107143259_0005/DJI_20260107143259_0005_segment_summary.csv`
- Annotation CSV to fill: `data/annotations/part_c/DJI_20260107143259_0005_surface_cover_annotations.csv`

### DJI_20260107143320_0007

- Dominant LUHK context: `GIC / open space` (0.974836)
- LUHK overlay contact sheet: `outputs/part_c/luhk_context/DJI_20260107143320_0007/DJI_20260107143320_0007_luhk_overlay_contact_sheet.png`
- Refined ROI: `outputs/part_c/surface_cover_review/DJI_20260107143320_0007/DJI_20260107143320_0007_refined_visible_roi.png`
- Thermal-grid ROI: `outputs/part_c/surface_cover_review/DJI_20260107143320_0007/DJI_20260107143320_0007_refined_visible_roi_resized_to_thermal_grid.png`
- Review contact sheet: `outputs/part_c/surface_cover_review/DJI_20260107143320_0007/DJI_20260107143320_0007_part_c_review_contact_sheet.png`
- Segmentation contact sheet: `outputs/part_c/superpixels/DJI_20260107143320_0007/DJI_20260107143320_0007_segmentation_contact_sheet.png`
- Segment ID full map: `outputs/part_c/superpixels/DJI_20260107143320_0007/DJI_20260107143320_0007_segment_id_labels_full.png`
- Segment ID quadrant map: `outputs/part_c/superpixels/DJI_20260107143320_0007/DJI_20260107143320_0007_segment_id_labels_quadrants.png`
- Segment summary: `outputs/part_c/superpixels/DJI_20260107143320_0007/DJI_20260107143320_0007_segment_summary.csv`
- Annotation CSV to fill: `data/annotations/part_c/DJI_20260107143320_0007_surface_cover_annotations.csv`

### DJI_20260107143328_0008

- Dominant LUHK context: `GIC / open space` (0.996589)
- LUHK overlay contact sheet: `outputs/part_c/luhk_context/DJI_20260107143328_0008/DJI_20260107143328_0008_luhk_overlay_contact_sheet.png`
- Refined ROI: `outputs/part_c/surface_cover_review/DJI_20260107143328_0008/DJI_20260107143328_0008_refined_visible_roi.png`
- Thermal-grid ROI: `outputs/part_c/surface_cover_review/DJI_20260107143328_0008/DJI_20260107143328_0008_refined_visible_roi_resized_to_thermal_grid.png`
- Review contact sheet: `outputs/part_c/surface_cover_review/DJI_20260107143328_0008/DJI_20260107143328_0008_part_c_review_contact_sheet.png`
- Segmentation contact sheet: `outputs/part_c/superpixels/DJI_20260107143328_0008/DJI_20260107143328_0008_segmentation_contact_sheet.png`
- Segment ID full map: `outputs/part_c/superpixels/DJI_20260107143328_0008/DJI_20260107143328_0008_segment_id_labels_full.png`
- Segment ID quadrant map: `outputs/part_c/superpixels/DJI_20260107143328_0008/DJI_20260107143328_0008_segment_id_labels_quadrants.png`
- Segment summary: `outputs/part_c/superpixels/DJI_20260107143328_0008/DJI_20260107143328_0008_segment_summary.csv`
- Annotation CSV to fill: `data/annotations/part_c/DJI_20260107143328_0008_surface_cover_annotations.csv`

### DJI_20260107143344_0009

- Dominant LUHK context: `GIC / open space` (1.0)
- LUHK overlay contact sheet: `outputs/part_c/luhk_context/DJI_20260107143344_0009/DJI_20260107143344_0009_luhk_overlay_contact_sheet.png`
- Refined ROI: `outputs/part_c/surface_cover_review/DJI_20260107143344_0009/DJI_20260107143344_0009_refined_visible_roi.png`
- Thermal-grid ROI: `outputs/part_c/surface_cover_review/DJI_20260107143344_0009/DJI_20260107143344_0009_refined_visible_roi_resized_to_thermal_grid.png`
- Review contact sheet: `outputs/part_c/surface_cover_review/DJI_20260107143344_0009/DJI_20260107143344_0009_part_c_review_contact_sheet.png`
- Segmentation contact sheet: `outputs/part_c/superpixels/DJI_20260107143344_0009/DJI_20260107143344_0009_segmentation_contact_sheet.png`
- Segment ID full map: `outputs/part_c/superpixels/DJI_20260107143344_0009/DJI_20260107143344_0009_segment_id_labels_full.png`
- Segment ID quadrant map: `outputs/part_c/superpixels/DJI_20260107143344_0009/DJI_20260107143344_0009_segment_id_labels_quadrants.png`
- Segment summary: `outputs/part_c/superpixels/DJI_20260107143344_0009/DJI_20260107143344_0009_segment_summary.csv`
- Annotation CSV to fill: `data/annotations/part_c/DJI_20260107143344_0009_surface_cover_annotations.csv`

### DJI_20260107143401_0011

- Dominant LUHK context: `GIC / open space` (0.998364)
- LUHK overlay contact sheet: `outputs/part_c/luhk_context/DJI_20260107143401_0011/DJI_20260107143401_0011_luhk_overlay_contact_sheet.png`
- Refined ROI: `outputs/part_c/surface_cover_review/DJI_20260107143401_0011/DJI_20260107143401_0011_refined_visible_roi.png`
- Thermal-grid ROI: `outputs/part_c/surface_cover_review/DJI_20260107143401_0011/DJI_20260107143401_0011_refined_visible_roi_resized_to_thermal_grid.png`
- Review contact sheet: `outputs/part_c/surface_cover_review/DJI_20260107143401_0011/DJI_20260107143401_0011_part_c_review_contact_sheet.png`
- Segmentation contact sheet: `outputs/part_c/superpixels/DJI_20260107143401_0011/DJI_20260107143401_0011_segmentation_contact_sheet.png`
- Segment ID full map: `outputs/part_c/superpixels/DJI_20260107143401_0011/DJI_20260107143401_0011_segment_id_labels_full.png`
- Segment ID quadrant map: `outputs/part_c/superpixels/DJI_20260107143401_0011/DJI_20260107143401_0011_segment_id_labels_quadrants.png`
- Segment summary: `outputs/part_c/superpixels/DJI_20260107143401_0011/DJI_20260107143401_0011_segment_summary.csv`
- Annotation CSV to fill: `data/annotations/part_c/DJI_20260107143401_0011_surface_cover_annotations.csv`

## Annotation Files

- Main annotation file: `data/annotations/part_c/part_c_surface_cover_annotations.csv`
- Approved class list: `data/annotations/part_c/surface_cover_classes.csv`

Use the segment ID label maps to locate each `segment_id`, then fill `manual_class` during review. Suggested classes are low-confidence heuristics, not final labels.

## Parked Draft Assets

- Early Part B superpixel manifest: `outputs/part_c/superpixels/early_part_b_draft_superpixels_manifest.csv`

Those early assets were generated before Part B refined alignment acceptance from the old center-crop ROI and are reference only.

## Known Limitations

- LUHK context comes from approximate metadata-based drone footprints and is broad land-use only.
- LUHK overlays can show footprint mismatch, but they are not a corrected georegistration.
- Surface-cover segmentation is generated from visible imagery only.
- The thermal grid is used as the target image grid, but no thermal temperatures are extracted.
- Segment suggestions are heuristic and require manual review.
- Final masks are intentionally withheld until manual labels are accepted.

## Next Manual Task

Review the contact sheets, then fill `manual_class` in `data/annotations/part_c/part_c_surface_cover_annotations.csv` or the per-pair annotation CSVs.
