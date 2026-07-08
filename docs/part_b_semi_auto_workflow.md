# Part B Semi-Automatic V/T ROI And Surface-Cover Workflow

Status: Round 1 pilot workflow

Part B creates reviewable visible-image surface-cover annotation aids inside the
thermal image region of interest. It is a semi-automatic labeling workflow, not
a land-cover prediction model.

## Scope

Part B uses visible `_V.JPG` images to prepare surface-cover labels inside the
thermal ROI. Thermal `_T.JPG` images provide the target image grid for later
temperature analysis, but Round 1 does not extract temperature values.

LUHK remains broad land-use context only. LUHK classes must not be treated as
surface-cover labels for drone pixels or superpixels.

## Inputs

- `data/metadata/vt_pairs.csv`
- `data/metadata/dji_image_metadata.csv`
- `data/metadata/pilot_candidate_pairs.csv`
- `docs/camera_parameter_assumptions.md`
- Raw local V/T images under `data/raw/HKUST/`

Garden Hill is excluded from this Round 1 pilot unless a later note documents a
specific reason to include it.

## Pilot Selection

Round 1 uses five HKUST V/T pairs. If `data/metadata/part_b_pilot_pairs.csv`
already exists, the script reuses that pilot list. Otherwise, it selects the
first five high-priority HKUST candidates that have both local `_V.JPG` and
`_T.JPG` files, excludes Garden Hill, and prefers rows with existing pilot grid
outputs.

## Camera Profiles

Visible images are not assumed to come from one fixed camera. The script
classifies each visible image using the Matrice 4T focal-length rules already
documented in Part A:

- `wide_visible`: 24 mm 35mm-equivalent focal length.
- `medium_tele_visible`: 70 mm 35mm-equivalent focal length.
- `tele_visible`: 168 mm 35mm-equivalent focal length.

The summary table is written to
`data/metadata/visible_camera_profiles.csv`.

## ROI Estimate

For each pilot pair, the script estimates the visible-image ROI corresponding
to the thermal image with this first-pass rule:

1. Resolve visible and thermal horizontal/vertical FOV from metadata using
   `scripts/camera_profiles.py`.
2. Compute thermal-to-visible FOV ratios.
3. Crop the visible image at the center using those ratios.
4. Resize the visible ROI to the thermal image grid size for review.

If metadata FOV cannot be resolved, the fallback is a centered crop matching
the thermal aspect ratio. The ROI is not a feature-matched homography and is
not precise georeferencing.

## Segmentation

The visible ROI resized to the thermal grid is segmented with SLIC superpixels
when `scikit-image` is available. A simple RGB/spatial SLIC-like fallback is
kept in the script for environments without `scikit-image`, but Round 1 should
prefer real SLIC.

The output segments are annotation units only. They are not trusted
surface-cover labels until manually reviewed.

Allowed Round 1 classes:

- `roof`
- `concrete_pavement`
- `asphalt_road`
- `vegetation_tree`
- `grass_low_vegetation`
- `bare_soil`
- `water`
- `shadow`
- `vehicle_temporary_object`
- `unclear_ignore`

## Outputs

- `data/metadata/part_b_pilot_pairs.csv`
- `data/annotations/surface_cover_classes.csv`
- `data/annotations/part_b_round1_segment_annotations.csv`
- `data/annotations/part_b_round1/*_segment_annotation_template.csv`
- `outputs/part_b/review_packages/<image_id>/`
- `outputs/part_b/overlays/`
- `outputs/part_b/superpixels/`
- `outputs/part_b/summaries/part_b_round1_summary.md`

Generated PNG review images are local review artifacts and are ignored by git
under the current repository rules.

## Run

```bash
python scripts/part_b/01_prepare_round1_review.py
```

Use the project virtual environment when available:

```bash
.venv/Scripts/python.exe scripts/part_b/01_prepare_round1_review.py
```

## Manual Review

Start with each `07_contact_sheet.png`, then inspect the ROI overlay and SLIC
boundary overlay. Fill the annotation templates by assigning `manual_class`,
`confidence`, `review_status`, and reviewer notes.

## Limitations

- The current ROI estimate assumes the thermal view is centered in the visible
  image.
- Camera offsets, lens distortion, terrain relief, and building height are not
  modeled.
- Superpixels may cross meaningful surface-cover boundaries.
- Shadow is allowed as a review class for Round 1, but later analysis may split
  illumination state from physical surface cover.
- Temperature extraction belongs to Part C and is intentionally not performed
  here.
