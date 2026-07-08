# Part C Codex Prefill Summary

Prefill version: `codex_draft_v1`

These labels are a draft for human review. They were inferred from visible ROI segment color, brightness, texture, and shape features. LUHK was not used as surface-cover evidence.

## Overall Class Counts

- `vegetation_tree`: 386
- `roof`: 191
- `unclear_ignore`: 107
- `concrete_pavement`: 94
- `bare_soil`: 27
- `asphalt_road`: 17
- `water`: 3
- `grass_low_vegetation`: 1

## Visual Correction Pass

After checking the prefill overlays and segment ID quadrant maps, Codex manually corrected 62 high-confidence dark rooftop / solar-panel segments from `vegetation_tree`, `water`, `asphalt_road`, or `unclear_ignore` to `roof`.

- Correction list: `outputs/part_c/summaries/part_c_codex_visual_corrections.csv`
- Corrected overlay paths: `outputs/part_c/summaries/part_c_codex_review_overlay_paths.csv`

The corrected overlays are named `<image_id>_codex_review_class_overlay.png`.

## Per-Pair Review Files

### DJI_20260107143259_0005

- Annotation CSV: `data/annotations/part_c/DJI_20260107143259_0005_surface_cover_annotations.csv`
- Prefill class overlay: `outputs/part_c/superpixels/DJI_20260107143259_0005/DJI_20260107143259_0005_codex_prefill_class_overlay.png`
- Segment ID quadrants: `outputs/part_c/superpixels/DJI_20260107143259_0005/DJI_20260107143259_0005_segment_id_labels_quadrants.png`

### DJI_20260107143320_0007

- Annotation CSV: `data/annotations/part_c/DJI_20260107143320_0007_surface_cover_annotations.csv`
- Prefill class overlay: `outputs/part_c/superpixels/DJI_20260107143320_0007/DJI_20260107143320_0007_codex_prefill_class_overlay.png`
- Segment ID quadrants: `outputs/part_c/superpixels/DJI_20260107143320_0007/DJI_20260107143320_0007_segment_id_labels_quadrants.png`

### DJI_20260107143328_0008

- Annotation CSV: `data/annotations/part_c/DJI_20260107143328_0008_surface_cover_annotations.csv`
- Prefill class overlay: `outputs/part_c/superpixels/DJI_20260107143328_0008/DJI_20260107143328_0008_codex_prefill_class_overlay.png`
- Segment ID quadrants: `outputs/part_c/superpixels/DJI_20260107143328_0008/DJI_20260107143328_0008_segment_id_labels_quadrants.png`

### DJI_20260107143344_0009

- Annotation CSV: `data/annotations/part_c/DJI_20260107143344_0009_surface_cover_annotations.csv`
- Prefill class overlay: `outputs/part_c/superpixels/DJI_20260107143344_0009/DJI_20260107143344_0009_codex_prefill_class_overlay.png`
- Segment ID quadrants: `outputs/part_c/superpixels/DJI_20260107143344_0009/DJI_20260107143344_0009_segment_id_labels_quadrants.png`

### DJI_20260107143401_0011

- Annotation CSV: `data/annotations/part_c/DJI_20260107143401_0011_surface_cover_annotations.csv`
- Prefill class overlay: `outputs/part_c/superpixels/DJI_20260107143401_0011/DJI_20260107143401_0011_codex_prefill_class_overlay.png`
- Segment ID quadrants: `outputs/part_c/superpixels/DJI_20260107143401_0011/DJI_20260107143401_0011_segment_id_labels_quadrants.png`

## Review Notes

- Check `roof` versus `concrete_pavement` carefully around buildings.
- Check dark roofs and solar panels; color rules may label them as `vegetation_tree`.
- Check dark canopy versus `shadow` carefully.
- Check `water`; this draft uses a restrictive blue/low-texture rule, but shaded surfaces can still confuse it.
- Change `manual_class` directly where needed and set `review_status` to `reviewed` after human review.
