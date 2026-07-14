# Part B Round 1 Summary

This Round 1 package prepares semi-automatic visible-image surface-cover review aids for five selected HKUST V/T pairs. It does not extract thermal temperature values and does not train a classification model.

## Files Created

- data/metadata/visible_camera_profiles.csv
- data/metadata/part_b_pilot_pairs.csv
- data/annotations/surface_cover_classes.csv
- data/annotations/part_b_round1_segment_annotations.csv
- data/annotations/part_b_round1/*_segment_annotation_template.csv
- outputs/part_b/review_packages/<image_id>/
- outputs/part_b/overlays/
- outputs/part_b/superpixels/
- outputs/part_b/summaries/part_b_round1_roi_estimates.csv
- outputs/part_b/summaries/part_b_round1_segments.csv

## Pilot Selection

Selection source: selected from pilot_candidate_pairs.csv. The selected pairs are the first five HKUST high-priority candidate rows with local V/T files, Garden Hill excluded, and existing pilot grid output preferred.

- 1. DJI_20260107143259_0005 (20260107_Thermal_HKUST/DCIM/DJI_202601071424_001::DJI_20260107143259_0005)
- 2. DJI_20260107143320_0007 (20260107_Thermal_HKUST/DCIM/DJI_202601071424_001::DJI_20260107143320_0007)
- 3. DJI_20260107143328_0008 (20260107_Thermal_HKUST/DCIM/DJI_202601071424_001::DJI_20260107143328_0008)
- 4. DJI_20260107143344_0009 (20260107_Thermal_HKUST/DCIM/DJI_202601071424_001::DJI_20260107143344_0009)
- 5. DJI_20260107143401_0011 (20260107_Thermal_HKUST/DCIM/DJI_202601071424_001::DJI_20260107143401_0011)

## Visible Camera Profiles

- wide_visible: 409 visible metadata rows observed; rule 35mm focal length=24.0.
- medium_tele_visible: 16 visible metadata rows observed; rule 35mm focal length=70.0.
- tele_visible: 485 visible metadata rows observed; rule 35mm focal length=168.0.

## ROI Estimation

- DJI_20260107143259_0005: metadata_fov_center_crop (medium confidence), crop 1108,786 to 2924,2239.
- DJI_20260107143320_0007: metadata_fov_center_crop (medium confidence), crop 1108,786 to 2924,2239.
- DJI_20260107143328_0008: metadata_fov_center_crop (medium confidence), crop 1108,786 to 2924,2239.
- DJI_20260107143344_0009: metadata_fov_center_crop (medium confidence), crop 1108,786 to 2924,2239.
- DJI_20260107143401_0011: metadata_fov_center_crop (medium confidence), crop 1108,786 to 2924,2239.

## Segmentation

- DJI_20260107143259_0005: skimage_slic produced 198 review segments.
- DJI_20260107143320_0007: skimage_slic produced 195 review segments.
- DJI_20260107143328_0008: skimage_slic produced 188 review segments.
- DJI_20260107143344_0009: skimage_slic produced 187 review segments.
- DJI_20260107143401_0011: skimage_slic produced 179 review segments.

## Manual Review Next

- Inspect each contact sheet under outputs/part_b/review_packages/<image_id>/07_contact_sheet.png.
- Check whether the red visible ROI rectangle plausibly matches the thermal image coverage.
- Inspect outputs/part_b/superpixels/*_segment_boundary_overlay.png for over- or under-segmentation.
- Fill manual_class, confidence, review_status, and notes in the annotation CSV templates.

## Known Limitations

- ROI alignment is a metadata/FOV center-crop estimate, not feature registration or precise georeferencing.
- The workflow assumes the thermal ROI is centered in the visible frame; camera offsets and lens distortion are not modeled.
- SLIC segments are candidate annotation units only; they are not trusted surface-cover labels.
- Shadow is included as an allowed review class for now, but later analysis may separate illumination from physical surface cover.
- Generated PNG review images are local review artifacts and are ignored by git under the current repository rules.
