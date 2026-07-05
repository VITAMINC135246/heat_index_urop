# Camera Parameter Assumptions for V/T LUHK Overlays

This note documents the revised pilot workflow for DJI visible `_V.JPG` and
thermal `_T.JPG` images. The previous thermal-first logic was correct for
thermal temperature work: thermal analysis should be based on `_T.JPG`
geometry, and `_V.JPG` should not be used as the geometric basis unless an
explicit V-to-T registration step is added.

The workflow now supports both image types by estimating separate footprints and
then linking them through shared LUHK 10 m raster cell IDs.

## Revised Workflow

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

## Camera Geometry Rules

Use a clear image type for every footprint or overlay:

- `image_type = "visible"` for `_V.JPG`
- `image_type = "thermal"` for `_T.JPG`

The scripts keep two camera profiles:

- `visible_profile`: only identifies the visible workflow. It is not used as a
  silent fallback for footprint estimation.
- `thermal_profile`: the thermal fallback profile for `_T.JPG` products when
  thermal metadata cannot resolve FOV.

Visible and thermal footprints are never assumed to be identical.

## Metadata Priority

The code resolves footprint camera parameters in this order:

1. Explicit horizontal and vertical FOV metadata.
2. Sensor width and height plus focal length.
3. Focal length plus 35mm-equivalent focal length plus actual image aspect.
4. Fallback profile only for thermal images.

For visible images, fallback is not allowed. If visible metadata lacks enough
FOV, sensor, or 35mm-equivalent information, the visible footprint row is marked
`status = incomplete` with a warning message. The thermal fallback profile is
not borrowed for `_V.JPG`.

Aperture is ignored for ground-footprint estimation.

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
