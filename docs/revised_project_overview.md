# Revised Project Overview

Prepared for: HEAT INDEX UROP progress planning
Status: Current pilot-stage direction

This document is the authoritative project plan for the current revised A-E
workflow. Older progress notes remain useful research history, but this file
controls the current stage definitions.

## Current Objective

The project is no longer primarily framed as using image recognition to predict
heat index. The current realistic objective is to build a pilot workflow that
links UAV thermal imagery, visible-image surface-cover information, and official
LUHK land-use data, then analyzes temperature and delta-temperature differences
across land-use and surface-cover conditions.

The immediate workflow should focus on the thermal region of interest (ROI),
because temperature is only available from the thermal image. Visible UAV
imagery is used to identify finer surface-cover types inside that thermal ROI.
LUHK 2024 remains the official broad land-use context, but it is not treated as
surface-cover ground truth.

Prediction modeling is a later optional extension. It should only be attempted
after reliable V/T ROI alignment, reviewed visible-image surface-cover labels,
temperature extraction, ambient-temperature matching, and Part E descriptive
analysis tables are available.

## Why The Method Changed

The earlier image-recognition framing was too broad for the available data and
current project stage. There is not enough labeled UAV imagery to train a
reliable CNN or U-Net surface-cover model, and LUHK cannot serve as detailed
pixel-level ground truth. In addition, visible and thermal images differ in
resolution and coverage, so surface-cover labels from the visible image must be
aligned or cropped to the thermal ROI before they can be linked to thermal
pixels or grid cells.

The revised method therefore separates the problem into linked but distinct
layers:

- LUHK 2024: official 10 m broad land-use context.
- Visible UAV images: finer surface-cover interpretation.
- Thermal UAV images: actual temperature information.
- V/T ROI alignment: the bridge between visible labels and thermal
  temperatures.

SLIC, maskSLIC, SAM, QGIS SCP, and Deepness may be useful auxiliary
segmentation or baseline tools, but their outputs require manual review and
should not be treated as trusted ground truth.

Orthomosaic construction is optional and is not the main workflow for the
current pilot stage.

## A. Data Inventory And Spatial Foundation

Goal: Organize all UAV data, V/T pairs, metadata, LUHK data, and project
assumptions.

Main work:

- Maintain the V/T pair inventory.
- Identify usable HKUST images and deprioritize Garden Hill images for the
  current workflow.
- Record missing V/T cases.
- Keep LUHK 2024 as the official 10 m land-use raster.
- Document camera and spatial estimation assumptions, including approximate
  nadir view, image top as north, GPS as approximate image center, altitude
  from metadata, and unknown terrain elevation.

Tools and techniques: Python, pandas, ExifTool, rasterio, geopandas, XLSX
metadata tables, Git, and GitHub.

Expected outputs:

- V/T pair XLSX.
- Metadata summary.
- LUHK category reference.
- Camera and georeferencing assumption notes.
- Pilot candidate image list. Final pilot selection requires later visual QA
  and V/T alignment review.

Current status: Mostly completed in first-pass form. The project already has a
V/T pairing workflow, metadata outputs, LUHK references, camera/spatial
assumption notes, and a candidate pilot list. Further updates may be needed as
more images are selected or filtered.

## B. V/T ROI Alignment And Visible Surface-Cover Classification

Goal: Determine where each thermal image corresponds within the visible image so
that visible-image surface-cover information can be reviewed inside the thermal
ROI and later linked to thermal pixels or cells.

Main work:

- Align visible images to thermal images or crop visible images to the thermal
  ROI.
- Identify the visible-image surface-cover classes inside the thermal ROI.
- Keep LUHK broad land-use context separate from visible-image surface cover.
- Produce V/T ROI previews and classification QA notes.
- Record whether alignment and surface-cover review are successful.
- Use manual inspection for failed or uncertain cases.
- Keep residual error or QA notes where possible.

Tools and techniques: OpenCV feature matching and homography where feasible,
metadata-based footprint estimation after camera assumptions are validated,
QGIS Georeferencer or manual GCP correction where needed, Python visualization,
QGIS visual checking, and semi-automatic surface-cover aids such as SLIC,
maskSLIC, SAM, QGIS SCP, or Deepness. These aids require manual review and are
not trusted ground truth.

Expected outputs:

- V-to-T alignment transform or ROI crop information.
- Thermal ROI visible crop.
- Reviewed visible-image surface-cover mask or annotation for selected pilot
  images.
- LUHK broad land-use context attached as a separate layer where needed.
- Overlay / ROI preview images.
- Alignment and classification QA notes.

Current status: The revised method has been decided, but a stable pilot
alignment and surface-cover review workflow still needs to be completed.

## C. Pilot LUHK, Physical Surface-Cover, And Shadow Masks

Goal: Use reviewed visible ROI annotations and LUHK context to produce
thermal-grid physical surface-cover masks, separate shadow masks, and
LUHK-aligned 10 m cell context for the pilot images.

Main work:

- Keep LUHK official land-use context separate from physical surface-cover
  labels.
- Generate thermal-grid physical surface-cover class masks from reviewed
  visible-image annotations.
- Store shadow as a separate binary state, not as a physical surface-cover
  class.
- Preserve Part C QA status, class mappings, mask manifests, and review notes.

Tools and techniques: Python, pandas, reviewed annotation workbooks, SLIC
segment review outputs, NumPy masks, and visual QA contact sheets.

Expected outputs:

- LUHK context summaries.
- Thermal-grid physical surface-cover masks.
- Separate binary shadow masks.
- Mask manifests, class mappings, QA summaries, and contact sheets.

Current status: Completed for the five pilot images in reviewed pilot form.
The physical surface-cover masks and shadow masks are ready for temperature
matrix joins.

## D. Temperature Extraction And Radiometric QA

Goal: Extract thermal temperature matrices from the DJI thermal images and
validate the extraction before using the temperatures for delta-T analysis.

Main work:

- Extract `512 x 640` temperature matrices from the five pilot thermal images.
- Confirm matrix shape and compatibility with Part C masks.
- Quantify non-finite and sub-zero pixels.
- Preserve sub-zero pixels unless a documented sensitivity rule is explicitly
  configured.
- Use per-image TAT3 report parameters for SDK extraction before final
  scientific interpretation.

Tools and techniques: DJI Thermal SDK, Python, NumPy, pandas, matplotlib, and
spatial QA plots.

Expected outputs:

- Temperature matrices.
- Temperature extraction manifest.
- Structural QA summaries.
- Sub-zero spatial QA outputs.
- TAT3 parameter ingest and remaining physical plausibility notes.

Current status: TAT3 parameter ingest, TAT3-parameter temperature extraction,
and sub-zero spatial QA are completed for the five pilot images. Remaining
review is focused on physical plausibility of apparent-temperature extrema
before delta-T analysis.

## E. Statistical Analysis And Visualization Of Delta-T Distributions

Part E is: statistical analysis and visualization of delta-T distributions,
with prediction as an optional later extension.

Goal: Calculate provisional delta-T observations after LUHK-cell or
cell-by-surface-cover aggregation, then describe and visualize their
distributions by LUHK context, physical surface cover, image, and QA state.
Prediction is an optional later extension and is not part of current Part E
Round 1.

Main work:

- Assign exactly one documented ambient-temperature value to each thermal image.
- Aggregate valid thermal pixels into existing LUHK-aligned 10 m cells.
- Aggregate valid thermal pixels by physical surface-cover class within each
  cell.
- Calculate delta-T after aggregation, not at independent pixel level.
- Compare provisional delta-T distributions by LUHK class, physical
  surface-cover class, image, flight, and acquisition time.
- Keep all finite temperatures in the primary analysis and support explicit
  sensitivity analysis for configured thresholds.
- Document the current shadow limitation: shadow masks exist, but the five
  pilot masks contain no `shadow_flag = 1` pixels.

Expected outputs:

- Cell-level provisional delta-T observations.
- Cell-by-physical-surface-cover provisional delta-T observations.
- Descriptive summary tables and exploratory statistical-test tables.
- Publication-style pilot figures and spatial cell maps.
- Part E summary report with provisional interpretation, reproducibility
  commands, and unresolved limitations.

Current status: Part E scripts and ambient-temperature templates have been
prepared. Numeric delta-T outputs are pending a local Part E ambient manifest
derived from the documented TAT3 pilot parameter table or another explicitly
approved source. All results must remain provisional until remaining
apparent-temperature plausibility review is complete.

## Feasibility Assessment

- Data inventory and LUHK presence checks: high feasibility.
- V/T ROI alignment: medium to high feasibility, but manual QA is required because
  thermal and visible images may not share enough visual features for fully
  automatic matching.
- Surface-cover classification: medium to high feasibility using
  semi-automatic segmentation plus manual review.
- CNN or U-Net training: low feasibility at this stage due to insufficient
  labeled data.
- Temperature extraction: medium feasibility, dependent on successful use of
  DJI Thermal Analysis Tool 3 or DJI Thermal SDK.
- Statistical analysis and visualization: medium to high feasibility once
  temperature extraction and ambient-temperature matching are complete.
- Reporting and visualization: high feasibility after pilot outputs exist.
- Full Hong Kong heat index prediction: low feasibility at the current stage
  and should not be presented as the immediate goal.

## Current Progress

- The project folder has already been organized.
- V/T image pairing has been implemented in first-pass form.
- The project has generated a V/T pair inventory XLSX.
- HKUST and Garden Hill image groups have been distinguished.
- Garden Hill images are currently deprioritized because they are lower quality
  and less suitable for the HKUST-focused workflow.
- LUHK has been clarified as official broad land-use context rather than fine
  surface-cover ground truth.
- The need for V/T alignment has been identified because thermal and visible
  images have different size and coverage.
- The revised method now focuses on the thermal ROI instead of the whole visible
  image.
- TAT3 parameter ingest, TAT3-parameter temperature extraction, and sub-zero
  spatial QA are complete for five pilot images.
- The next major input needed for Part E is a local ambient manifest derived
  from the documented TAT3 pilot parameter table or another explicitly approved
  source.

## Related Documents

- `docs/method_change_log.md`: short record of methodology changes.
- `docs/camera_parameter_assumptions.md`: camera and georeferencing
  assumptions used by the current pilot scripts.
- `docs/part_b_land_use_surface_cover_scheme.txt`: classification scheme for
  LUHK context and visible-image surface cover.
- `docs/part_e_delta_t_statistical_analysis.md`: current Part E delta-T
  analysis method and provisional-result requirements.
- `docs/archive/deprecated/progress_update_part_b_pilot_plan.md`: historical
  June 2026 progress update, now superseded by the current A-E structure for
  planning purposes.
