# Heat Index UROP Progress Update: Part B Pilot Plan

**Prepared for:** Professor progress discussion
**Date:** 2026-06-16

## July 2026 Supersession Note

This document is retained as a historical progress record. Its original A-D
workflow framing has been superseded by the revised A-E project structure in
`docs/revised_project_overview.md`. The current objective is to link UAV thermal
imagery, visible-image surface-cover information, and LUHK 2024 land-use data,
then analyze temperature and delta-temperature differences across land-use and
surface-cover conditions. Prediction modeling is now treated as a later optional
extension rather than the immediate goal.

## Executive Summary

The received DJI dataset structure and contents appear usable. Before leaving
Hong Kong, I confirmed that the thermal data could be opened and extracted
using DJI Thermal Analysis Tool 3 (TDT 3). However, I currently do not have
access to a Windows device or a working DJI TDT 3 / DJI Thermal SDK
environment, so pixel-level temperature-matrix extraction is temporarily
paused.

While Part A is paused, I have advanced Part B: land-use and surface-cover
alignment. The raw data structure has been preserved, a reproducible V/T pair
inventory has been generated, and a two-layer classification scheme has been
defined.

Current implementation update: the pilot LUHK workflow now estimates separate
footprints for visible `_V.JPG` and thermal `_T.JPG` images, selects five valid
HKUST V/T pairs, and creates 10 m cells aligned to the LUHK raster row/column
grid. Visible and thermal image correspondence is expressed through shared
LUHK `global_cell_id` values, not by assuming identical V/T camera geometry.

## Project Workflow Overview: Revised A-E

### A. Data Inventory And Spatial Foundation

- Maintain the V/T pair inventory and metadata summaries.
- Identify usable HKUST images and deprioritize Garden Hill images for the
  current HKUST-focused workflow.
- Record missing V/T cases and selected pilot images.
- Keep LUHK 2024 as the official 10 m broad land-use raster.
- Document camera and spatial assumptions, including approximate nadir view,
  image top as north, GPS as approximate image center, metadata altitude, and
  unknown terrain elevation.

Current status: Mostly completed in first-pass form.

### B. V/T ROI Alignment And Visible Surface-Cover Classification

- Align visible images to thermal images or crop visible images to the thermal
  ROI.
- Classify visible-image surface cover inside the thermal ROI.
- Keep LUHK broad land-use context separate from visible-image surface cover.
- Produce V/T ROI previews and alignment/classification QA notes.
- Use OpenCV feature matching or homography where feasible.
- Use metadata-based footprint estimation, QGIS Georeferencer, or manual GCP
  correction when needed.
- Use manual inspection for failed or uncertain cases.

Current status: The revised method has been decided, but a stable pilot
alignment and surface-cover review workflow still needs to be completed.

### C. Temperature Extraction And Delta-T Table Construction

- Confirm DJI R-JPEG thermal files are usable.
- Extract pixel-level or region-level temperature values.
- Obtain or define an ambient temperature source.
- Calculate delta-T.
- Join temperature, LUHK land use, surface cover, metadata, and QA fields into
  an analysis-ready table.

Current status: Not fully started because temperature extraction depends on
Windows, DJI Thermal Analysis Tool 3, or DJI Thermal SDK access.

### D. Statistical Analysis By Land-Use Context And Surface Cover

- Compare delta-T distributions by LUHK land-use category.
- Compare delta-T distributions by visible-image surface-cover category.
- Analyze differences within broad LUHK categories, especially GIC areas at
  HKUST.
- Generate summary tables, boxplots, histograms, and maps.

Current status: Not started. This depends on successful temperature extraction
and reliable spatial and classification alignment.

### E. Reporting, Visualization, And Optional Exploratory Modeling

- Prepare the final pilot workflow report and figures.
- Document assumptions, QA outcomes, and limitations.
- Optionally test simple exploratory models only after enough reliable labeled
  data and temperature tables exist.

Current status: Not started. This depends on Parts B-D.

## Current Data Status

- Raw DJI data is stored under `data/raw/HKUST/`.
- It includes Garden Hill and HKUST datasets from multiple dates and sessions.
- Garden Hill and HKUST use different directory depths, but their original
  structures have been retained.
- Original DJI files are not modified, renamed, or moved.
- The generated V/T inventory is stored at `data/metadata/vt_pairs.xlsx`.

## V/T Pairing Progress

The reproducible inventory script is:

```text
scripts/01_create_vt_pairs.py
```

It recursively scans JPG/JPEG files ending in `_V` and `_T` and generates:

```text
data/metadata/vt_pairs.xlsx
```

The initial strict rule paired files only when they had the same parent
directory and identical complete base names. Inspection showed that many
apparent missing records were actually V/T images whose timestamps differed by
one second, for example:

```text
DJI_20260202171028_0071
DJI_20260202171029_0071
```

Both belong to sample number `0071`. The pairing script has therefore already
been improved to use two stages:

1. Exact match: same parent/session and identical complete base name.
2. Fallback match: same parent/session and same sample number.

This prevents cross-session matches while allowing legitimate one-second
timestamp differences. The current inventory contains 910 records: 909 paired
records and one record missing a thermal counterpart. Of the paired records,
745 are exact base-name matches and 164 use the session/sample-number fallback.

## Classification Scheme

The project now separates broad land-use context from visible physical surface
cover. Full definitions are documented in
`docs/part_b_land_use_surface_cover_scheme.txt`.

### Layer 1: LUHK Broad Land-Use Context

The original LUHK classes are retained:

1. Residential
2. Commercial
3. Industrial
4. GIC / open space
5. Transport
6. Other urban / built-up land
7. Agriculture
8. Woodland / shrubland / grassland / wetland
9. Barren land
10. Water bodies

LUHK is an official broad-brush land-use representation with a 10 m raster
resolution. One `10 m 脳 10 m` cell represents approximately `100 m虏` and may
contain several visible physical surfaces. LUHK is therefore appropriate as
broad land-use context, but not as drone pixel-level surface-cover ground
truth. Original LUHK categories should be retained; grouped classes can be
created later for specific statistical analyses.

### Layer 2: Drone Visible-Image Surface Cover

The pilot-stage classes are:

```text
0 Unknown / excluded
1 Building roof
2 Asphalt
3 Concrete / paved surface
4 Tree canopy
5 Low vegetation
6 Bare soil / rock
7 Water
```

Surface cover describes the physical surface actually visible in the drone
image and is more directly related to thermal behavior. A single LUHK class
may contain roofs, roads, vegetation, water, and other surfaces. The pilot
scheme remains intentionally compact to improve manual-annotation consistency.

Shadow is not a surface-cover class. It should be stored as a separate binary
mask:

```text
0 not shadowed
1 shadowed
```

## Why Registration Is Needed

The `_V.JPG` and `_T.JPG` images do not share the same resolution. In one
verified pair, the visible image is `4032 脳 3024` and the thermal JPG is
`1280 脳 1024`; the intended extracted temperature-matrix grid is `640 脳 512`.
The sensors may also differ in field of view, physical position, rotation,
scale, and perspective.

Consequently, simply resizing the visible image would not provide reliable
pixel correspondence. The required mapping is:

```text
visible image coordinate 鈫?thermal image 640 脳 512 coordinate
```

## Proposed Registration Approach

1. Select one `0016_V/T` pair as the first pilot.
2. Lock the unique pilot pair from `vt_pairs.xlsx`.
3. Inspect image quality, overlap, and visible landmarks.
4. Manually select control points.
5. Compare affine transformation and homography.
6. Use RANSAC to reject incorrect control-point matches.
7. Warp the visible image to the thermal `640 脳 512` grid.
8. Generate overlay, checkerboard, and edge-overlay diagnostics.
9. Calculate reprojection error.
10. Select the most stable V鈫扵 transformation.
11. Apply the same transformation to the visible surface-cover mask.

Categorical masks must use **nearest-neighbour interpolation** during
transformation. Bilinear interpolation must not be used because it would
create invalid intermediate class IDs.

## Current Limitation

I currently do not have access to a Windows device or the required DJI TDT 3 /
DJI Thermal SDK environment. Pixel-level temperature-matrix extraction has
therefore not started in the current environment.

Part B does not depend on having the temperature matrix and can proceed after
Part A closure. Temperature extraction belongs to revised Part C and can resume
when Windows / DJI extraction access is available.

## Current LUHK Overlay Implementation

The existing scripts previously generated a five-pair LUHK pilot diagnostic:

- `scripts/03_estimate_image_footprints.py` creates one footprint row per
  visible or thermal image.
- `scripts/04_create_10m_grids_pilot.py` creates LUHK-raster-aligned 10 m
  cells and records visible coverage, thermal coverage, and common V/T cells.
- `scripts/05_assign_luhk_landuse_pilot_overlays.py` outputs separate visible
  overlays, thermal overlays, common-cell overlays, and EPSG:2326 map views.

Visible `_V.JPG` footprints use visible metadata only. Thermal fallback camera
assumptions are not used for visible overlays. Thermal `_T.JPG` footprints keep
the thermal profile fallback only as a labeled fallback when metadata cannot
resolve FOV.

These outputs are useful history, but no footprint, cover, or LUHK overlay
should be treated as final until the Matrice 4T per-image visible camera
selection rule has been validated.

## Next-Week Plan

- Validate and freeze the updated same-session/sample-number pairing inventory.
- Confirm and freeze the first unique pilot pair.
- Validate per-image Matrice 4T camera selection before treating footprint or
  cover outputs as final.
- Create `pilot_pairs.xlsx`.
- Complete the first V鈫扵 registration.
- Generate registration diagnostics and review reprojection error.
- Start or complete the pilot visible-image surface-cover annotation.
- If Windows access becomes available, I will start testing temperature matrix
  extraction using DJI TDT 3 or DJI Thermal SDK.

## Discussion Points for the Professor

- Confirm whether the proposed compact pilot surface-cover scheme is
  sufficiently detailed.
- Select or approve the first `0016_V/T` pilot pair.
- Confirm whether affine transformation and homography should both be evaluated
  during the first pilot.
- Discuss access to a Windows device and the preferred DJI extraction workflow.

## Raw Historical Note

An older raw note at the end of this document had text-encoding corruption. Its
intended meaning appears to have been: find the thermal image coordinates,
match them with the Hong Kong grid, use the dominant LUHK context where needed,
and use DJI thermal tools plus an algorithm to estimate real coordinates for
thermal pixels while considering distortion. This note is historical only; the
current revised workflow is controlled by `docs/revised_project_overview.md`.
