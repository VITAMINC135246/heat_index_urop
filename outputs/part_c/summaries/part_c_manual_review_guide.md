# Part C Manual Review Guide

Use this guide to review the Part C Round 1 pilot package. Part C labels are manually reviewed candidates, not ground truth.

## Review Order

1. Open the LUHK overlay contact sheet for a pair and judge whether the approximate LUHK footprint looks spatially plausible.
2. Open the Part C review contact sheet and confirm the refined visible ROI covers the accepted thermal target area.
3. Open the segment ID quadrant map to locate segment IDs.
4. Edit `manual_class` in the main annotation CSV when your decision differs from `suggested_class`.
5. Update `review_status` to `Yes` only after the segment has been checked; otherwise leave `Not yet`.

## Segment ID Lookup

The annotation CSV uses `segment_id`. To find a segment:

- use `segment_id_labels_quadrants.png` first, because it is zoomed and less crowded
- use `segment_id_labels_full.png` for whole-image orientation
- use `segment_summary.csv` if you need centroid or bounding-box coordinates

## Labeling Rules

- Label surface cover from the visible ROI, not from LUHK.
- Use LUHK only as broad land-use context and uncertainty evidence.
- If a segment is mixed, label the dominant visible surface when one class clearly dominates.
- If a segment is too mixed, shadowed, or ambiguous, use `unclear_ignore`.
- Keep `suggested_class` as-is; put your final review decision in `manual_class`.
- Use only classes listed in `data/annotations/part_c/surface_cover_classes.csv`.
- Edit the main CSV first; the per-pair CSVs are mirrors for browsing and can be regenerated.
- Confidence can stay low/medium/high according to your certainty.

## Per-Pair Files

### DJI_20260107143259_0005

- LUHK overlay: `outputs/part_c/luhk_context/DJI_20260107143259_0005/DJI_20260107143259_0005_luhk_overlay_contact_sheet.png`
- Review contact sheet: `outputs/part_c/surface_cover_review/DJI_20260107143259_0005/DJI_20260107143259_0005_part_c_review_contact_sheet.png`
- Surface-cover class review sheet: `outputs/part_c/surface_cover_review/DJI_20260107143259_0005/DJI_20260107143259_0005_surface_cover_class_review_sheet.png`
- Segment ID quadrants: `outputs/part_c/superpixels/DJI_20260107143259_0005/DJI_20260107143259_0005_segment_id_labels_quadrants.png`
- Segment summary: `outputs/part_c/superpixels/DJI_20260107143259_0005/DJI_20260107143259_0005_segment_summary.csv`
- Annotation CSV: `data/annotations/part_c/DJI_20260107143259_0005_surface_cover_annotations.csv`

### DJI_20260107143320_0007

- LUHK overlay: `outputs/part_c/luhk_context/DJI_20260107143320_0007/DJI_20260107143320_0007_luhk_overlay_contact_sheet.png`
- Review contact sheet: `outputs/part_c/surface_cover_review/DJI_20260107143320_0007/DJI_20260107143320_0007_part_c_review_contact_sheet.png`
- Surface-cover class review sheet: `outputs/part_c/surface_cover_review/DJI_20260107143320_0007/DJI_20260107143320_0007_surface_cover_class_review_sheet.png`
- Segment ID quadrants: `outputs/part_c/superpixels/DJI_20260107143320_0007/DJI_20260107143320_0007_segment_id_labels_quadrants.png`
- Segment summary: `outputs/part_c/superpixels/DJI_20260107143320_0007/DJI_20260107143320_0007_segment_summary.csv`
- Annotation CSV: `data/annotations/part_c/DJI_20260107143320_0007_surface_cover_annotations.csv`

### DJI_20260107143328_0008

- LUHK overlay: `outputs/part_c/luhk_context/DJI_20260107143328_0008/DJI_20260107143328_0008_luhk_overlay_contact_sheet.png`
- Review contact sheet: `outputs/part_c/surface_cover_review/DJI_20260107143328_0008/DJI_20260107143328_0008_part_c_review_contact_sheet.png`
- Surface-cover class review sheet: `outputs/part_c/surface_cover_review/DJI_20260107143328_0008/DJI_20260107143328_0008_surface_cover_class_review_sheet.png`
- Segment ID quadrants: `outputs/part_c/superpixels/DJI_20260107143328_0008/DJI_20260107143328_0008_segment_id_labels_quadrants.png`
- Segment summary: `outputs/part_c/superpixels/DJI_20260107143328_0008/DJI_20260107143328_0008_segment_summary.csv`
- Annotation CSV: `data/annotations/part_c/DJI_20260107143328_0008_surface_cover_annotations.csv`

### DJI_20260107143344_0009

- LUHK overlay: `outputs/part_c/luhk_context/DJI_20260107143344_0009/DJI_20260107143344_0009_luhk_overlay_contact_sheet.png`
- Review contact sheet: `outputs/part_c/surface_cover_review/DJI_20260107143344_0009/DJI_20260107143344_0009_part_c_review_contact_sheet.png`
- Surface-cover class review sheet: `outputs/part_c/surface_cover_review/DJI_20260107143344_0009/DJI_20260107143344_0009_surface_cover_class_review_sheet.png`
- Segment ID quadrants: `outputs/part_c/superpixels/DJI_20260107143344_0009/DJI_20260107143344_0009_segment_id_labels_quadrants.png`
- Segment summary: `outputs/part_c/superpixels/DJI_20260107143344_0009/DJI_20260107143344_0009_segment_summary.csv`
- Annotation CSV: `data/annotations/part_c/DJI_20260107143344_0009_surface_cover_annotations.csv`

### DJI_20260107143401_0011

- LUHK overlay: `outputs/part_c/luhk_context/DJI_20260107143401_0011/DJI_20260107143401_0011_luhk_overlay_contact_sheet.png`
- Review contact sheet: `outputs/part_c/surface_cover_review/DJI_20260107143401_0011/DJI_20260107143401_0011_part_c_review_contact_sheet.png`
- Surface-cover class review sheet: `outputs/part_c/surface_cover_review/DJI_20260107143401_0011/DJI_20260107143401_0011_surface_cover_class_review_sheet.png`
- Segment ID quadrants: `outputs/part_c/superpixels/DJI_20260107143401_0011/DJI_20260107143401_0011_segment_id_labels_quadrants.png`
- Segment summary: `outputs/part_c/superpixels/DJI_20260107143401_0011/DJI_20260107143401_0011_segment_summary.csv`
- Annotation CSV: `data/annotations/part_c/DJI_20260107143401_0011_surface_cover_annotations.csv`

## Stop Conditions

- Do not create final masks from these segments yet.
- Do not extract thermal temperature yet.
- Do not train a prediction model from these pilot labels.
