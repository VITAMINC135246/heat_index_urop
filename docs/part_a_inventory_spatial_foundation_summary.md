# Part A Inventory And Spatial Foundation Summary

Date: 2026-07-07

## Scope

Part A checked the repository structure, revised planning documents, V/T pair
inventory, metadata readiness, LUHK references, camera/spatial assumptions, and
pilot-selection readiness. This pass did not implement V/T alignment, surface
cover segmentation, temperature extraction, or model preparation.

## Authoritative Plan

`docs/revised_project_overview.md` is the authoritative plan for the revised
A-E workflow. `docs/method_change_log.md` records the method change, and older
Part B progress notes remain research history only.

## Files Checked

- `data/raw/`
- `data/metadata/`
- `data/processed/`
- `data/luhk/`
- `docs/`
- `scripts/`
- `outputs/`

## Files Created Or Updated

- `data/metadata/vt_inventory_validation_summary.xlsx`
- `data/metadata/pilot_candidate_pairs.xlsx`
- `docs/part_a_inventory_spatial_foundation_summary.md`
- `docs/revised_project_overview.md`
- `docs/camera_parameter_assumptions.md`

## V/T Inventory Validation

Existing file validated: `data/metadata/vt_pairs.xlsx`.

The existing XLSX was compared with the in-memory output of
`scripts/01_create_vt_pairs.py`; it matches, so the XLSX was not regenerated.

Inventory statistics:

- Total pair records: 910
- Paired V/T records: 909
- Missing visible records: 0
- Missing thermal records: 1
- Duplicate records: 0
- HKUST records: 823
- Garden Hill records: 87
- HKUST paired records: 823
- Garden Hill paired records: 86
- Exact base-name matches: 745
- Session sample-number fallback matches: 164
- Unmatched records: 1
- Pilot records marked in `vt_pairs.xlsx`: 0

The pairing logic scans JPG/JPEG files recursively below `data/raw/HKUST/`,
matches visible `_V` and thermal `_T` images within the same parent folder, and
ignores non-V/T suffixes such as `_S`. A scan found 1 `_S` file, 0 `MISC/THM`
image files, and 0 viewer/tool image files.

## HKUST And Garden Hill Status

HKUST and Garden Hill are distinguishable in `vt_pairs.xlsx` through the
`location` and `dataset_folder` fields. HKUST is the current priority for the
pilot workflow. Garden Hill remains preserved in the inventory and research
history, but it is deprioritized because it is less suitable for the
HKUST-focused pilot.

## Metadata Readiness

Existing metadata file validated: `data/metadata/dji_image_metadata.xlsx`.

Metadata status:

- Metadata rows: 1819
- Visible rows: 910
- Thermal rows: 909
- Rows with GPS latitude/longitude: 1819
- Rows with relative altitude: 1817
- Rows with image dimensions: 1819

Useful fields already present include image path, image type, pair ID, pair
status, parent folder, capture datetime, GPS latitude/longitude, altitude
fields, gimbal/flight attitude fields, image width/height, focal length, camera
model, thermal metadata placeholders, and documented first-pass assumptions.

ExifTool is present locally at `exiftool-13.59_64/`. The broken local `.venv`
was recreated with Python 3.12.13, and the project dependencies were installed
from `requirements.txt`. `rasterio`, `geopandas`, `shapely`, `pyproj`,
`pandas`, `numpy`, `Pillow`, and `matplotlib` now import successfully in
`.venv`. OpenCV is not installed because it is not required by the current Part
A scripts or `requirements.txt`; it can be added later if Part B alignment code
requires it.

## LUHK Data Status

LUHK files checked:

- `data/luhk/LUMHK_RasterGrid_2024.tif`
- `data/luhk/LUMHK_RasterGrid_2024.tif.aux.xml`
- `data/LUHK2024_SC.xlsx`

The LUHK GeoTIFF is present. A lightweight TIFF tag check confirms a raster
size of 6375 by 4800 pixels, 10 m pixel size, and EPSG:2326 / Hong Kong 1980
Grid metadata. `data/LUHK2024_SC.xlsx` is present as the category reference.
After the environment repair, `rasterio` also opens the raster successfully and
confirms EPSG:2326, 10 m pixel size, and nodata value -128.

LUHK is documented as an official 10 m broad land-use context layer. It must
not be treated as fine surface-cover ground truth. Visible UAV imagery will be
used later to identify surface cover inside the thermal ROI.

Older generated overlay reports may mention the former extracted path
`data/LUHK2024_extracted/...`; the current verified LUHK raster for Part A is
`data/luhk/LUMHK_RasterGrid_2024.tif`.

## Camera And Spatial Assumptions

The assumptions are documented in `docs/camera_parameter_assumptions.md`.
Current first-pass assumptions are:

- Thermal `_T.JPG` metadata and thermal parameters are the priority for thermal
  footprint estimation.
- Visible `_V.JPG` metadata supports visible-image context and V/T pairing.
- Images are treated as approximately nadir / vertical.
- Image top is treated as north unless better orientation metadata is used
  later.
- GPS latitude/longitude is treated as the approximate image center.
- Relative altitude is taken from EXIF/XMP when available.
- Terrain elevation is unknown and remains an uncertainty.
- Visible and thermal images have different dimensions and possibly different
  fields of view.
- V/T alignment is required later in Part B.
- DJI Matrice 4T `_V.JPG` files may come from wide, medium tele, or tele
  visible cameras. Later footprint and alignment work must identify the
  visible camera per image instead of applying one fixed visible-camera
  assumption.
- Existing metadata provides a preliminary camera rule: 24 mm 35mm-equivalent
  focal length indicates wide visible, 70 mm indicates medium tele visible,
  168 mm indicates tele visible, and 52-53 mm indicates the thermal camera.

No claim is made that images are accurately orthorectified at this stage.

## Pilot Readiness

Created candidate list: `data/metadata/pilot_candidate_pairs.xlsx`.

This list is candidate-only and was produced from existing inventory, metadata,
and footprint status. No manual visual QA or alignment was performed.

Candidate statistics:

- HKUST paired candidate records: 823
- High-priority metadata/footprint candidates: 672
- Medium-priority metadata/footprint candidates: 148
- Candidates needing metadata or footprint review: 3
- Candidates matching existing pilot grid outputs: 5
- Candidate records with sample number `0016`: 12
- Camera metadata validation: 409 wide visible rows, 16 medium tele visible
  rows, 485 tele visible rows, and 909 thermal rows classified from existing
  metadata with high confidence.

The first rows prioritize existing five-pair pilot grid outputs and sample
`0016` candidates where possible, but final pilot selection remains a Part B
visual QA and alignment decision.

## Remaining TODOs Before Part B

- Freeze a small final pilot set after visual QA.
- Validate per-image camera selection before treating footprints, cover
  calculations, or LUHK overlay outputs as final.
- Begin V/T ROI alignment and visible-image surface-cover classification in
  Part B.
- Only after Part B spatial/classification readiness, begin temperature
  extraction in Part C.

## Part A Status

Part A is mostly complete and ready for the next stage with minor environment
limitations documented. The project now has a usable V/T inventory, pairing
statistics, HKUST/Garden Hill distinction, LUHK reference check, metadata
readiness check, camera/spatial assumptions, and pilot-candidate list.

## Version 0.1 integration note

`scripts/workflow/input_validation.py` now returns one structured validation
record per V/T group for both dataset and selected-file modes. It validates
existence, readability, type, role, identifier, time/session consistency, image
metadata availability, and thermal availability. It deliberately does not
claim scene correspondence; that decision remains in Part B. The existing
pairing and DJI metadata scripts remain reusable preparation tools.
# Version 0.2 integration

The persistent entry point now writes a structured Part A record for every
group, including failures. It reuses the existing inventory/metadata/camera
assumptions and adds explicit fatal-thermal versus visible-only errors, pairing
uncertainty, native temperature-grid compatibility, and cache-safe metadata
fingerprints. Part A still does not perform alignment or invent missing inputs.
