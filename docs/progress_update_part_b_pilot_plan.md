# Heat Index UROP Progress Update: Part B Pilot Plan

**Prepared for:** Professor progress discussion
**Date:** 2026-06-16

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
defined. The next pilot task is to select one V/T pair, register the
high-resolution visible image to the thermal grid, and transfer a visible-image
surface-cover annotation to that grid.

## Project Workflow Overview: A-D

### A. Data Extraction

- Extract a `640 × 512` pixel-level temperature matrix from each DJI thermal
  R-JPEG.
- Use Windows with DJI TDT 3 or DJI Thermal SDK.
- This part is temporarily paused because the required Windows/DJI environment
  is not currently available.

### B. Land-Use and Surface-Cover Alignment

- Build and validate visible/thermal image pairs.
- Use LUHK as broad land-use context.
- Annotate physical surface cover on the visible image.
- Establish visible-to-thermal (V→T) geometric registration.
- Transfer the visible-image categorical mask to the thermal `640 × 512` grid.

### C. ΔT Spectrum and Statistical Analysis

- Compare temperature or ΔT among land-use and surface-cover classes.
- Examine the effects of shadow, surface-cover composition, and broad
  land-use context.
- Retain both broad context and visible physical surface information instead
  of treating them as the same variable.

### D. Prediction Model Building

- Later, build a simple prediction model using land-use/surface-cover features
  and extracted temperature matrices.
- The initial objective can be point-level or window-level ΔT prediction,
  rather than an immediate full-city real-time model.

## Current Data Status

- Raw DJI data is stored under `data/raw/HKUST/`.
- It includes Garden Hill and HKUST datasets from multiple dates and sessions.
- Garden Hill and HKUST use different directory depths, but their original
  structures have been retained.
- Original DJI files are not modified, renamed, or moved.
- The generated V/T inventory is stored at `data/metadata/vt_pairs.csv`.

## V/T Pairing Progress

The reproducible inventory script is:

```text
scripts/01_create_vt_pairs.py
```

It recursively scans JPG/JPEG files ending in `_V` and `_T` and generates:

```text
data/metadata/vt_pairs.csv
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
resolution. One `10 m × 10 m` cell represents approximately `100 m²` and may
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
verified pair, the visible image is `4032 × 3024` and the thermal JPG is
`1280 × 1024`; the intended extracted temperature-matrix grid is `640 × 512`.
The sensors may also differ in field of view, physical position, rotation,
scale, and perspective.

Consequently, simply resizing the visible image would not provide reliable
pixel correspondence. The required mapping is:

```text
visible image coordinate → thermal image 640 × 512 coordinate
```

## Proposed Registration Approach

1. Select one `0016_V/T` pair as the first pilot.
2. Lock the unique pilot pair from `vt_pairs.csv`.
3. Inspect image quality, overlap, and visible landmarks.
4. Manually select control points.
5. Compare affine transformation and homography.
6. Use RANSAC to reject incorrect control-point matches.
7. Warp the visible image to the thermal `640 × 512` grid.
8. Generate overlay, checkerboard, and edge-overlay diagnostics.
9. Calculate reprojection error.
10. Select the most stable V→T transformation.
11. Apply the same transformation to the visible surface-cover mask.

Categorical masks must use **nearest-neighbour interpolation** during
transformation. Bilinear interpolation must not be used because it would
create invalid intermediate class IDs.

## Current Limitation

I currently do not have access to a Windows device or the required DJI TDT 3 /
DJI Thermal SDK environment. Pixel-level temperature-matrix extraction has
therefore not started in the current environment.

Part B does not depend on having the temperature matrix and can proceed now.
Part A temperature extraction can resume when Windows access becomes available.

## Next-Week Plan

- Validate and freeze the updated same-session/sample-number pairing inventory.
- Confirm and freeze the first unique pilot pair.
- Create `pilot_pairs.csv`.
- Complete the first V→T registration.
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



need to find the经纬度 of the _T.jpg, match with the HK grid graph, use the major one to define the landuse;
NEED DJI TAT3 to get the centre 经纬度, need a 算法to calculate the real coordinates of rach pixel. 考虑畸变
