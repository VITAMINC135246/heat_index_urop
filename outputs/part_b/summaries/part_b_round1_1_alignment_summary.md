# Part B Round 1.1 Alignment Summary

This package preserves the existing Part B Round 1 review outputs and adds before/after V/T alignment refinement figures for the same five HKUST pilot pairs.

No surface-cover annotation was ingested, no superpixels were converted to masks, and no thermal temperature data was extracted.

## Stage Boundary

- Part B is currently V/T alignment and thermal ROI acceptance only.
- Existing Round 1 superpixel and annotation CSV outputs are parked for future Part C preparation.
- Automatic cross-modal scores are diagnostics; visual/manual acceptance is still required.

## Pilot Pair Results

- DJI_20260107143259_0005: quality=acceptable, confidence=medium, needs_manual_gcp=no, method=skimage_edge_grid_search_seeded_by_opencv_phase_correlation_from_metadata_fov_center_crop, dx=-0.4670204275428169, dy=16.409970445062665, scale=0.99, rotation=0.0, score_delta=0.12341.
- DJI_20260107143320_0007: quality=acceptable, confidence=medium, needs_manual_gcp=no, method=skimage_edge_grid_search_seeded_by_opencv_phase_correlation_from_metadata_fov_center_crop, dx=2.2386855320318575, dy=16.94046015719998, scale=0.99, rotation=0.0, score_delta=0.098559.
- DJI_20260107143328_0008: quality=acceptable, confidence=medium, needs_manual_gcp=no, method=skimage_edge_grid_search_from_metadata_fov_center_crop, dx=0.0, dy=20.0, scale=0.99, rotation=0.0, score_delta=0.097996.
- DJI_20260107143344_0009: quality=acceptable, confidence=medium, needs_manual_gcp=no, method=skimage_edge_grid_search_seeded_by_opencv_phase_correlation_from_metadata_fov_center_crop, dx=1.2114594387424005, dy=18.141872202534476, scale=0.99, rotation=0.0, score_delta=0.098294.
- DJI_20260107143401_0011: quality=acceptable, confidence=medium, needs_manual_gcp=no, method=skimage_edge_grid_search_seeded_by_opencv_phase_correlation_from_metadata_fov_center_crop, dx=0.4169631268416829, dy=14.42551262650066, scale=0.99, rotation=0.0, score_delta=0.088789.

## Review First

- `outputs/part_b/alignment_refinement/DJI_20260107143259_0005/10_alignment_comparison_contact_sheet.png`
- `outputs/part_b/alignment_refinement/DJI_20260107143320_0007/10_alignment_comparison_contact_sheet.png`
- `outputs/part_b/alignment_refinement/DJI_20260107143328_0008/10_alignment_comparison_contact_sheet.png`
- `outputs/part_b/alignment_refinement/DJI_20260107143344_0009/10_alignment_comparison_contact_sheet.png`
- `outputs/part_b/alignment_refinement/DJI_20260107143401_0011/10_alignment_comparison_contact_sheet.png`

For each pair, compare the old and refined alpha blends, edge overlays, and full-visible ROI boxes.

## Alignment Data

- `outputs/part_b/summaries/part_b_round1_1_alignment_summary.csv`
- `outputs/part_b/summaries/part_b_round1_1_alignment_attempts.csv`
- `outputs/part_b/summaries/part_b_round1_local_outputs_manifest.csv`
- `outputs/part_b/alignment_refinement/<image_id>/top_alignment_candidates.csv`
- `outputs/part_b/alignment_refinement/<image_id>/manual_gcp_template.csv`

## Known Limitations

- OpenCV was available for this run; phase correlation, ECC, and ORB attempts are recorded in the attempts CSV.
- Edge and gradient scores can improve for the wrong reason across thermal-visible imagery.
- Refined crop/rotation candidates still require visual acceptance before Part B is closed.
- Manual GCP residuals are blank until included control points are filled.
