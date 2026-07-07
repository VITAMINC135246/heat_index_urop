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
temperature extraction, and analysis tables are available.

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

Tools and techniques: Python, pandas, ExifTool, rasterio, geopandas, CSV
metadata tables, Git, and GitHub.

Expected outputs:

- V/T pair CSV.
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

## C. Temperature Extraction And Delta-T Table Construction

Goal: Extract thermal temperature values from DJI thermal images and combine
them with the reviewed Part B spatial and classification outputs.

Main work:

- Confirm DJI R-JPEG thermal files are usable.
- Extract pixel-level or region-level temperature values.
- Obtain or define ambient temperature source.
- Calculate delta-T.
- Join temperature, LUHK land use, surface cover, image metadata, and QA
  information into one analysis-ready table.

Tools and techniques: DJI Thermal Analysis Tool 3, DJI Thermal SDK if batch
extraction is possible, Python, pandas, and heatmap or histogram QA plots.

Expected outputs:

- Temperature matrix or region-level temperature values.
- Delta-T table.
- Joined dataset with temperature, LUHK, surface cover, and metadata.
- QA figures.

Current status: Not yet fully started because temperature extraction depends on
Windows, DJI Thermal Analysis Tool 3, or DJI Thermal SDK access. Earlier project
work should prepare the spatial and classification layers so the temperature
matrix can be joined later.

## D. Statistical Analysis By Land-Use Context And Surface Cover

Goal: Analyze how temperature or delta-T varies across official LUHK land-use
categories and visible-image surface-cover categories.

Main work:

- Compare delta-T distributions by LUHK land use.
- Compare delta-T distributions by surface cover.
- Analyze differences within broad LUHK categories, especially GIC areas at
  HKUST.
- Generate summary tables and figures.

Tools and techniques: pandas, scipy, statsmodels, matplotlib, QGIS, and
geopandas.

Expected outputs:

- Delta-T summary statistics.
- Boxplots, histograms, and maps.
- Comparison between LUHK-only and LUHK plus surface-cover analysis.

Current status: Not started yet. This stage depends on successful temperature
extraction and reliable spatial and classification alignment.

## E. Reporting, Visualization, And Optional Exploratory Modeling

Goal: Communicate the pilot workflow and results, and optionally test simple
exploratory prediction only after enough reliable data exists.

Main work:

- Prepare final pilot workflow report and figures.
- Summarize assumptions, QA outcomes, and limitations.
- Visualize representative ROI, surface-cover, LUHK, temperature, and delta-T
  outputs.
- Optionally test simple exploratory models, such as regression, Random Forest,
  or XGBoost, only after reliable labels and temperature tables are available.

Expected outputs:

- Final pilot workflow report.
- Publication or presentation figures.
- Reproducibility notes.
- Optional exploratory model results clearly marked as non-final.

Current status: Not started. This depends on Parts B-D.

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
- Statistical analysis: medium to high feasibility once temperature extraction
  succeeds.
- Reporting and visualization: high feasibility after pilot outputs exist.
- Full Hong Kong heat index prediction: low feasibility at the current stage
  and should not be presented as the immediate goal.

## Current Progress

- The project folder has already been organized.
- V/T image pairing has been implemented in first-pass form.
- The project has generated a V/T pair inventory CSV.
- HKUST and Garden Hill image groups have been distinguished.
- Garden Hill images are currently deprioritized because they are lower quality
  and less suitable for the HKUST-focused workflow.
- LUHK has been clarified as official broad land-use context rather than fine
  surface-cover ground truth.
- The need for V/T alignment has been identified because thermal and visible
  images have different size and coverage.
- The revised method now focuses on the thermal ROI instead of the whole visible
  image.
- Temperature extraction is still pending because it requires Windows, DJI
  Thermal Analysis Tool 3, or DJI Thermal SDK access.
- The next major work should be a pilot workflow using several high-quality
  HKUST V/T pairs: validate per-image camera assumptions, align visible images
  to thermal images, label surface cover inside the thermal ROI, keep LUHK as
  separate context, and prepare for later temperature extraction.

## Related Documents

- `docs/method_change_log.md`: short record of methodology changes.
- `docs/camera_parameter_assumptions.md`: camera and georeferencing
  assumptions used by the current pilot scripts.
- `docs/part_b_land_use_surface_cover_scheme.txt`: classification scheme for
  LUHK context and visible-image surface cover.
- `docs/progress_update_part_b_pilot_plan.md`: historical June 2026 progress
  update, now superseded by the revised A-E structure for planning purposes.
