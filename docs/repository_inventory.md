# Repository Inventory After Workflow Revision

This inventory was prepared before reorganizing files for the revised workflow.

## Current

- `scripts/01_create_vt_pairs.py`: builds the V/T image-pair inventory.
- `scripts/02_extract_dji_metadata.py`: extracts DJI metadata into a small XLSX.
- `scripts/03_estimate_image_footprints.py`: estimates visible and thermal image
  footprints using the revised V/T geometry assumptions.
- `scripts/04_create_10m_grids_pilot.py`: creates LUHK-aligned 10 m context
  cells for selected pilot pairs.
- `scripts/05_assign_luhk_landuse_pilot_overlays.py`: draws LUHK context
  overlays for pilot pairs.
- `scripts/camera_profiles.py`: stores visible/thermal camera-profile
  assumptions used by footprint scripts.
- `scripts/inspect_camera_metadata.py`: summarizes existing DJI metadata and
  applies the preliminary Matrice 4T camera-identification rule.
- `data/LUHK2024_SC.xlsx`: small LUHK class mapping metadata.
- `data/metadata/vt_pairs.xlsx` and `data/metadata/dji_image_metadata.xlsx`:
  small metadata tables kept under version control.
- `data/metadata/vt_inventory_validation_summary.xlsx`,
  `data/metadata/pilot_candidate_pairs.xlsx`, and
  `data/metadata/camera_metadata_validation_summary.xlsx`: Part A closure
  validation outputs.
- `docs/`: project notes, assumptions, progress records, and the method change
  log.

## Generated But Kept For Progress History

- `data/processed/**/*.xlsx`: small generated pilot tables that support
  progress reporting and are useful for reproducibility.
- `outputs/reports/*.txt`: script run summaries.
- `outputs/geodata/*.geojson`: generated geospatial outputs used in the pilot
  reporting workflow.
- `outputs/figures/hong_kong_land_use_*.png`: LUHK context figures.
- `outputs/figures/pilot_grid_overlays/*.png`: pilot grid previews used in the
  LUHK-aligned grid workflow.

## Archived Experimental Previews

- `outputs/archive/figures/*.png`: older one-off footprint/example previews.
- `outputs/archive/figures_quick_cheacked/*.png`: early quick-check plots from
  the typo-named preview folder.

## Deprecated

- `scripts/deprecated/03_estimate_thermal_footprints.py`: old thermal-only
  compatibility entry point.
- `scripts/deprecated/05_assign_luhk_landuse_example.py`: old single-example
  compatibility entry point.
- `scripts/deprecated/plot_hong_kong_land_use.py`: early standalone LUHK plotter
  that reads the source ZIP directly.

## Untracked Or Ignored Local Data

- `data/raw/`: read-only drone source data.
- `data/base/`, `data/luhk/`, `data/TDOP_TIFF_*/`, and
  `data/True_Digital_Orthophoto_TDOP_GEOPACKAGE/`: local raster/GIS source
  data.
- `data/*Raster*GEOTIFF*.zip` and other `data/*.zip`: downloaded source
  archives are local data. The previously tracked LUHK GeoTIFF ZIP was removed
  from version control after confirming the local extracted LUHK raster at
  `data/luhk/LUMHK_RasterGrid_2024.tif`.
- `outputs/georef/` and `outputs/qgis_exports/`: QGIS-generated control points,
  temporary exports, and large intermediate rasters.
- `.venv/`, `.matplotlib-cache/`, and `exiftool-*_*/`: local environment,
  cache, and vendor tool folders.

## Unclear

- `data/qgis/*.qgz`: useful local QGIS project files, but they may contain
  machine-specific paths. They are ignored for now unless the project decides to
  maintain portable QGIS project files in Git.
