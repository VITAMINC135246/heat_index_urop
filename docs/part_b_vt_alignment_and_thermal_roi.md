# Part B V/T Alignment And Thermal ROI

Status: Round 1.1 alignment refinement

Part B is limited to V/T alignment and thermal ROI acceptance. It estimates the
visible-image region corresponding to the thermal grid and creates review
figures so the alignment can be visually accepted or rejected.

Part C is the later LUHK context plus surface-cover classification and
temperature summarization stage. Surface-cover annotation should not continue
until Part B alignment is accepted.

## Current Boundary

- Part A is complete and should not be modified or redone.
- Part B Round 1 review packages are preserved.
- Round 1 superpixel images and annotation XLSXs already exist, but they are
  parked as early Part C preparation.
- Round 1 alignment is not accepted because the V/T overlay shows slight
  misalignment.
- Round 1.1 refines alignment for the existing five HKUST pilot pairs only.

## Acceptance Criterion

The current Part B acceptance criterion is visual/manual acceptance of the V/T
ROI alignment. Automatic scores are diagnostics, not final proof, because
thermal-visible matching is cross-modal and can fail even when a numeric score
improves.

For each pilot pair, review:

- old ROI box on the full visible image
- refined ROI box on the full visible image
- old and refined V/T alpha blends
- old and refined side-by-side visible ROI and thermal previews
- old and refined edge overlays
- the old-vs-refined contact sheet

If automatic alignment remains uncertain, fill the manual GCP template using
stable features visible in both images, such as building corners, roof edges,
road intersections, sharp pavement boundaries, or other fixed large objects.

## Round 1.1 Outputs

- `scripts/part_b/b05_refine_vt_alignment.py`
- `scripts/part_b/b06_generate_alignment_refinement_review.py`
- `outputs/part_b/alignment_refinement/<image_id>/`
- `outputs/part_b/summaries/part_b_round1_1_alignment_summary.xlsx`
- `outputs/part_b/summaries/part_b_round1_1_alignment_attempts.xlsx`
- `outputs/part_b/summaries/part_b_round1_1_alignment_summary.md`

OpenCV-based phase correlation, ECC, and feature matching are attempted only
when OpenCV is installed. If OpenCV is unavailable or unstable, the workflow
records the skipped or rejected method and falls back to auditable small local
search plus manual GCP templates.

## Manual GCP Template

Each pair has a manual GCP template:

`outputs/part_b/alignment_refinement/<image_id>/manual_gcp_template.xlsx`

Columns:

- `pair_id`
- `V_x`
- `V_y`
- `T_x`
- `T_y`
- `point_description`
- `include`
- `notes`

Use full visible-image pixel coordinates for `V_x` and `V_y`, and thermal-grid
pixel coordinates for `T_x` and `T_y`. Mark usable rows with `include=yes`.
When enough included points exist, the alignment script can estimate
translation, affine, or homography transforms and report residual errors.

## Do Not Do Yet

- Do not ingest annotation XLSXs.
- Do not convert superpixels to masks.
- Do not extract thermal temperature values.
- Do not treat LUHK as pixel-level surface cover.
- Do not start full batch processing.
