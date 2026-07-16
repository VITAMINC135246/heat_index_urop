# Method Change Log

## 2026-07-16 Part E pixel-level spectrum priority

Part E's primary scientific visual result is now the pixel-level ΔT
distribution/density spectrum. Spectrum means a statistical distribution of
ΔT values, not electromagnetic reflectance or multispectral-band analysis.

Key implications:

- The formal observation is one accepted finite thermal pixel with
  `delta_t_c = temperature_c - ambient_temperature_c`.
- All finite pixels remain in the canonical Parquet. Formal samples retain
  original pixel values after spatial thinning; no LUHK-cell, tile, or
  neighbouring-pixel mean is calculated before analysis.
- Formal spectra use Python/SciPy and completed sampled-pixel Parquets. Boxplots,
  spatial QA, coverage charts, and Excel charts are supporting outputs.
- The earlier cell-level spectrum workflow was retired from the active tree
  after validation; it remains recoverable from Git history and is absent from
  the formal pipeline.
- Density height is normalized, not pixel count; counts and image coverage are
  reported separately.
- P-values remain exploratory, spatial dependence remains a limitation, and the
  five-image pilot does not generalize to all of Hong Kong.
- The current pilot has no valid shadow-present pixels, so a surface-cover ×
  shadow spectrum is not estimable and no empty figure is produced.

## 2026-07-15 Part D TAT3-parameter extraction baseline

Part D temperature extraction now requires per-image parameters parsed from
exported TAT3 reports before the DJI Thermal SDK is called. The old
placeholder/default SDK measurement-parameter path is deprecated and should not
be used for downstream delta-T analysis.

Key implications:

- `scripts/part_d/03_parse_tat3_ambient_temperature_reports.py` must run before
  `scripts/part_d/01_extract_temperature_matrices.py`.
- The canonical pilot parameter table is
  `outputs/part_d/qa/tat3_parameter_audit/part_d_tat3_pilot_parameters.csv`.
- Part D now uses the TAT3/embedded ambient temperature, reflected
  temperature, emissivity, and distance values for each pilot image.
- TAT3-derived humidity is retained for SDK reproducibility but is not
  interpreted as reliable field humidity.
- The previous Round 1 placeholder-parameter outputs have been removed from
  the active checkpoint record.

## 2026-07-15 Part E delta-T analysis reframing

Part E is now defined as statistical analysis and visualization of provisional
delta-T distributions. Prediction modeling is a later optional extension and is
not part of the current Part E Round 1 task.

Key implications:

- Delta-T is calculated after aggregation to LUHK-aligned 10 m cells, or to
  cell-by-physical-surface-cover observations within those cells.
- Individual thermal pixels are not treated as independent statistical
  observations.
- Each thermal image requires exactly one documented ambient-temperature value.
- The current Part D TAT3 parameter table provides documented pilot
  ambient-temperature values that can seed the Part E ambient manifest.
- Results must remain provisional until the remaining physical plausibility
  review of apparent temperatures is complete.
- The old June 2026 progress note with superseded prediction-first language has
  been archived under `docs/archive/deprecated/`.

This 2026-07-15 cell-aggregation definition was superseded on 2026-07-16 by the
formal pixel-level method above. It remains recorded here as change history.

## 2026-07-07 revised A-E project structure

The project objective has been updated from an image-recognition-first framing
to a thermal-ROI workflow that links UAV thermal imagery, visible-image
surface-cover information, and official LUHK 2024 land-use data.

The older A-D plan is superseded for planning purposes. The current structure is:

- A. Data inventory and spatial foundation.
- B. V/T ROI alignment and visible-image surface-cover classification inside
  the thermal ROI.
- C. Temperature extraction and Delta-T table construction.
- D. Statistical analysis by LUHK land-use context and visible-image
  surface-cover class.
- E. Reporting, visualization, and optional exploratory modeling.

Key implications:

- Analysis should focus on the thermal ROI because temperature is only
  available in the thermal image.
- Visible-image labels must be aligned or cropped to the thermal ROI before
  they are linked to thermal pixels or thermal grid cells.
- LUHK remains the official broad land-use context, not fine surface-cover
  ground truth.
- Orthomosaic construction is optional for the pilot stage.
- Prediction modeling is a later optional extension, not the immediate project
  objective.
- Footprint, cover, and LUHK overlay outputs should not be treated as final
  until camera assumptions are validated per image.

## 2026-07-07 Part A closure and Matrice 4T camera correction

Part A was closed as an inventory and spatial-foundation stage only. It
validates V/T inventory, metadata availability, LUHK raster presence, pilot
candidate readiness, and first-pass assumptions. It does not include V/T
alignment, segmentation, temperature extraction, LUHK overlay production, or
model preparation.

The DJI platform is treated as DJI Matrice 4T. Important camera implications:

- Visible `_V.JPG` files must not be assumed to all use one wide-angle camera.
  Matrice 4T includes wide, medium tele, and tele visible cameras.
- Existing metadata distinguishes visible cameras by 35mm-equivalent focal
  length: 24 mm wide, 70 mm medium tele, and 168 mm tele.
- Thermal `_T.JPG` files use the thermal camera. Existing metadata reports
  approximately 12 mm actual focal length and 52 mm 35mm-equivalent focal
  length; the DJI specification may describe this as 53 mm equivalent, which is
  not treated as a contradiction.
- Aperture / f-number is useful metadata but is not the main footprint geometry
  input.

The working Windows `.venv` was recreated with Python 3.12.13 and the
`requirements.txt` spatial stack, including `rasterio`.

The full current overview is documented in `docs/revised_project_overview.md`.

## 2026-07-06 workflow revision

The Part B workflow has changed from direct land-use interpretation from visible
drone images to a layered land-use and surface-cover workflow.

- Official LUHK raster data provides the land-use context. LUHK should be used
  as a broad, authoritative land-use layer, not as pixel-level surface-cover
  ground truth for drone imagery.
- Visible drone images are used for semi-automatic surface-cover segmentation
  within the thermal region of interest.
- SLIC and maskSLIC superpixels are the main candidate methods for generating
  surface-cover regions. SAM-based mask proposal can be tested as an optional
  candidate-region generator.
- Manual review is required because the project does not yet have enough labeled
  image data to train or validate a dedicated CNN/U-Net segmentation model.
- QGIS SCP and QGIS Deepness pretrained models may be tested as baseline
  comparisons only. Their outputs should not be treated as ground truth.

Practical implication: LUHK answers "what official land-use context is this
thermal ROI in?", while visible-image segmentation answers "what surface-cover
patches are visible inside the thermal ROI?" These should remain separate
analysis layers.
