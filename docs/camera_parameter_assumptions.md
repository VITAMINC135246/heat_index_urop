# Camera Parameter Assumptions For V/T ROI And Spatial Preparation

This note documents the revised pilot workflow for DJI visible `_V.JPG` and
thermal `_T.JPG` images. The previous thermal-first logic was correct for
thermal temperature work: thermal analysis should be based on `_T.JPG`
geometry, and `_V.JPG` should not be used as the geometric basis unless an
explicit V-to-T registration step is added.

Part A documents assumptions and validates metadata readiness only. Footprint,
cover, and LUHK overlay products should not be treated as final until
per-image camera selection and V/T ROI alignment are validated.

## Current Spatial Script Context

1. `scripts/03_estimate_image_footprints.py`
   estimates one footprint row per image for each valid HKUST V/T pair:
   one visible row and one thermal row.
2. `scripts/04_create_10m_grids_pilot.py`
   selects five pilot V/T pairs and creates LUHK-aligned 10 m cells from the
   LUHK raster row/column grid.
3. `scripts/05_assign_luhk_landuse_pilot_overlays.py`
   creates visible overlays, thermal overlays, common V/T cell overlays, and
   standalone EPSG:2326 map views.

Compatibility wrappers remain at:

- `scripts/03_estimate_thermal_footprints.py`
- `scripts/05_assign_luhk_landuse_example.py`

These wrappers call the revised scripts so old commands fail less abruptly, but
the active workflow is the V/T workflow above.

Do not rerun the footprint or LUHK overlay scripts as part of Part A closure.
They are later spatial-support scripts and their outputs need per-image camera
validation before use.

## Camera Geometry Rules

Use a clear image type for every footprint or overlay:

- `image_type = "visible"` for `_V.JPG`
- `image_type = "thermal"` for `_T.JPG`

The scripts keep two camera profiles:

- `visible_profile`: only identifies the visible workflow. It has no fixed
  fallback focal length because DJI Matrice 4T has multiple visible cameras.
- `thermal_profile`: the thermal fallback profile for `_T.JPG` products when
  thermal metadata cannot resolve FOV.

Visible and thermal footprints are never assumed to be identical.

## DJI Matrice 4T Camera Metadata

The supervisor's drone is treated as DJI Matrice 4T. It has three visible
cameras and one thermal camera:

- Wide-angle visible camera: 1/1.3 inch CMOS, 48 MP, f/1.7, 24 mm
  35mm-equivalent focal length.
- Medium tele visible camera: 1/1.3 inch CMOS, 48 MP, f/2.8, 70 mm
  35mm-equivalent focal length.
- Tele visible camera: 1/1.5 inch CMOS, 48 MP, f/2.8, 168 mm
  35mm-equivalent focal length.
- Infrared thermal camera: 640 x 512, f/1.0, about 53 mm 35mm-equivalent focal
  length, uncooled VOx microbolometer, high-res mode supported.

Important correction: do not assume that all `_V.JPG` files use the wide-angle
camera. Later footprint estimation and V/T ROI alignment must first identify
which visible camera produced each `_V.JPG`.

Existing metadata in `data/metadata/dji_image_metadata.csv` provides a
preliminary camera rule:

- `image_type = visible` and `focal_length_35mm = 24`: wide visible camera.
- `image_type = visible` and `focal_length_35mm = 70`: medium tele visible
  camera.
- `image_type = visible` and `focal_length_35mm = 168`: tele visible camera.
- `image_type = thermal`, `focal_length = 12`, and `focal_length_35mm` near
  `52` or `53`: thermal camera.

The metadata currently classifies as 409 wide visible rows, 16 medium tele
visible rows, 485 tele visible rows, and 909 thermal rows. The preliminary rule
is implemented in `scripts/camera_profiles.py` and summarized by
`scripts/inspect_camera_metadata.py`.

Actual focal length and 35mm-equivalent focal length are different quantities.
For example, `_T.JPG` metadata reports actual focal length near 12 mm while the
DJI specification reports about 53 mm equivalent focal length. This is not a
contradiction.

## Part A First-Pass Spatial Assumptions

These assumptions support inventory review and later footprint estimation only.
They do not mean that the images are accurately orthorectified.

- Thermal `_T.JPG` metadata and thermal camera parameters are the priority for
  thermal footprint estimation and future temperature analysis.
- Visible `_V.JPG` metadata is used for visible-image context and V/T pairing.
- Images are treated as approximately nadir or vertical for first-pass spatial
  estimation.
- Image top is treated as north unless a later workflow uses reliable yaw or
  orientation metadata.
- GPS latitude and longitude are treated as the approximate image center.
- Relative altitude is extracted from EXIF/XMP metadata when available.
- Terrain elevation is currently unknown and is a documented uncertainty.
- Visible and thermal images have different image dimensions and may have
  different fields of view.
- Explicit V/T alignment or ROI construction is therefore required later before
  visible surface-cover labels are linked to thermal pixels or cells.
- No footprint, cover calculation, or LUHK overlay should be treated as final
  until camera selection logic has been validated per image.

## Metadata Priority

The code resolves footprint camera parameters in this order:

1. Explicit horizontal and vertical FOV metadata.
2. Sensor width and height plus focal length.
3. Actual focal length plus 35mm-equivalent focal length plus actual image
   aspect.
4. Fallback profile only for thermal images.

For visible images, fallback is not allowed. If visible metadata lacks enough
FOV, sensor, or 35mm-equivalent information, the visible footprint row is marked
`status = incomplete` with a warning message. The thermal fallback profile is
not borrowed for `_V.JPG`.

If only equivalent focal length is available, footprint or FOV estimates are
approximate and must be documented. Aperture / f-number is useful camera
metadata but is not the main input for footprint geometry.

## LUHK-Aligned Grid Rule

The 10 m grid is aligned to the LUHK 2024 raster, not to an arbitrary image
footprint origin. Each selected cell is an official LUHK raster cell with:

- `luhk_row`
- `luhk_col`
- `global_cell_id`
- LUHK raw code
- aggregated LUHK category

For each pilot pair, the grid table records:

- `visible_coverage_ratio`
- `thermal_coverage_ratio`
- `is_visible_covered`
- `is_thermal_covered`
- `is_common_vt_cell`

This makes V/T correspondence explicit through shared LUHK cell IDs. It does
not imply that the visible and thermal images have the same image geometry.

## Current Pilot Outputs

The current generated outputs include:

- `data/processed/footprints/image_footprints.csv`
- `outputs/geodata/image_footprints.geojson`
- `data/processed/grids/pilot_luhk_aligned_10m_grid_cells.csv`
- `outputs/geodata/pilot_luhk_aligned_10m_grid_cells.geojson`
- `outputs/figures/pilot_landuse_overlays/`

Reports are written to:

- `outputs/reports/03_estimate_image_footprints_summary.txt`
- `outputs/reports/04_create_10m_grids_pilot_summary.txt`
- `outputs/reports/05_assign_luhk_landuse_pilot_overlays_summary.txt`

## Remaining Limitations

This is still a first-pass geospatial overlay, not precise photogrammetric
registration. The main limitations are:

- GPS is treated as the image center.
- Yaw/heading metadata is reported but not yet used to rotate footprints.
- Terrain elevation and building heights are not modeled.
- Single images are not orthorectified.
- LUHK is a broad 10 m land-use context layer, not a pixel-level surface-cover
  mask.
- There is no explicit V-to-T pixel registration yet.
