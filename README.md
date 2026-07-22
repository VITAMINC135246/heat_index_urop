# Heat Index UROP

Pilot workflow for linking UAV thermal imagery, visible-image surface-cover
information, and official LUHK 2024 land-use data. The current objective is to
analyze temperature and delta-temperature differences across land-use and
surface-cover conditions, not to immediately build a full heat-index prediction
model. Version 0.3.2 is the supported persistent workflow. It preserves the
verified Part A–E methods, adds canonical schema-aware spatial figures, and
supports explicit opt-in capture-level temporal analysis without treating
pixels as time replicates.

## Contents

- `docs/revised_project_overview.md`: current A-E project objective,
  methodology, feasibility assessment, and progress summary.
- `docs/method_change_log.md`: record of major method revisions.
- `docs/camera_parameter_assumptions.md`: camera and footprint assumptions for
  the current V/T and LUHK pilot workflow.
- `docs/part_b_land_use_surface_cover_scheme.txt`: LUHK land-use and
  visible-image surface-cover classification reference.
- `docs/part_e_delta_t_statistical_analysis.md`: current Part E delta-T
  analysis method, ambient-temperature requirement, and provisional-result
  rule.
- `docs/repository_inventory.md`: repository layout policy, current boundary
  exceptions, and future migration guidance.
- `docs/v0_2_workflow.md`: route state machine, adapters, Part B0, Part C GUI,
  formal Part E, extremes, and limitations.
- `docs/v0_2_canonical_schema.md`: schema, measurement/provenance definitions,
  eligibility, artifacts, and cache dependencies.
- `docs/v0_2_gui_and_tat3.md`: GUI smoke test and temporary TAT3 instructions.
- `docs/v0_2_benchmark.md`: measured stage timings, memory/storage, and separate
  request-X versus retention-Y guidance.
- `docs/v0_2_user_acceptance_test_plan.md`: complete Chinese user-acceptance
  procedure, including all five pilots, the soccer-field V/T mismatch route,
  per-case evidence, and all 48 automated cases.
- `docs/v0_3_workflow.md`: v0.3 routing, spatial, temporal, cache, and soccer-field scope.
- `docs/v0_3_canonical_schema.md`: schema-0.2 retention decision and optional v0.3 linkage metadata.
- `docs/v0_3_spatial_figures.md`: canonical spatial maps, unavailable-layer semantics, and completeness validation.
- `docs/v0_3_temporal_analysis.md`: explicit same-location temporal groups, observed ranges, QA, and scientific limits.
- `docs/v0_3_gui_and_soccer_field.md`: per-capture polygon and real soccer-field reproduction workflow.
- `docs/v0_3_user_acceptance_test_plan.md`: step-by-step Chinese ordinary-user acceptance flow from one command.
- `scripts/`: reproducible inventory, metadata, footprint, grid, and LUHK
  overlay scripts.
- `data/metadata/`: generated V/T and metadata XLSX tables kept under version
  control.
- `outputs/`: generated reports, geodata, and progress figures.

## Current project direction

The revised workflow separates three linked data layers:

1. LUHK 2024 provides official 10 m broad land-use context.
2. Visible UAV images provide finer surface-cover information inside the
   thermal region of interest.
3. Thermal UAV images provide the actual temperature information.

Because temperature is only available in the thermal image, the current pilot
focuses on the thermal ROI rather than the whole visible image. V/T alignment
or ROI construction is required before visible-image surface-cover masks can be
linked to thermal pixels or thermal grid cells.

Semi-automatic tools such as SLIC, maskSLIC, SAM, QGIS SCP, or Deepness may be
used as candidate segmentation or baseline tools, but manual review remains
necessary. CNN or U-Net training and full Hong Kong heat-index prediction are
later optional extensions, not the immediate objective.

## Windows Python Environment

The project uses a local Windows virtual environment. From the project root:

```powershell
C:\Users\Victo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Verify the spatial stack:

```powershell
.\.venv\Scripts\python.exe -c "import rasterio, geopandas, shapely, pyproj, pandas, numpy, PIL, matplotlib; print('spatial stack ok')"
.\.venv\Scripts\python.exe scripts\inspect_camera_metadata.py
```

If matplotlib cannot write its default cache under the user profile, set a
local cache directory before plotting:

```powershell
$env:MPLCONFIGDIR = "$PWD\.matplotlib-cache"
```

`.venv/`, local raw data, source rasters, and temporary plotting caches are not
tracked by Git.

## Usage

### Version 0.3.2 persistent workflow

For an ordinary user, start the complete v0.3.2 workflow from the repository
root with one command:

```powershell
.\.venv\Scripts\python.exe scripts\run_user_workflow.py
```

The launcher asks whether to run the five accepted pilots, the football field,
both, one V/T group, a dataset directory, or several specifically selected V/T
groups in one run. The last choice is useful for repeated captures of one target
and accepts multiple TAT3 reports plus a separate accepted polygon per capture.
Enter paths and review decisions when asked. Ordinary users do not write JSON
files, select a workflow config, or construct a long command line. By default
the launcher writes to the isolated acceptance area and opens the newest run
folder; read `USER_RESULTS.md` first.

Each invocation has a run ID. Its workflow summary is under
`outputs/runs/v0_3_user_acceptance/workflow_runs/<run_id>/`, and its formal
analysis is under
`outputs/runs/v0_3_user_acceptance/part_e/schema_0_2/<run_id>/`. The persistent
canonical image store may be reused as an input/cache, but Part E figures,
tables, QA, and temporal results are kept run-scoped so one run cannot silently
stand in for another.

The launcher asks whether already accepted reviews should be reopened. Choose
Yes to revise normal Part C or Part C* for the selected group(s); no cache
folders need to be deleted by hand.

The launcher executes Part A, Part B0, reviewed Part B, normal reviewed Part C
or Part C*, shared Part D, canonical writing, extremes, and formal Part E.
Console messages announce the current stage and whether user review is needed.

No code path contains a fabricated soccer-field 26°C result. The real workflow
requires a separately accepted polygon for each capture, real compatible
temperature matrices, and documented ambient-air records.

Automatic alignment evidence never accepts the normal route. Ambiguous B0 and
unreviewed final Part B groups pause for explicit decisions. A valid thermal
input can use Part C* only with accepted target, surface-cover, and LUHK context.

Temporal analysis is optional and defaults to **No**. Selecting Yes does not
automatically group images: the user must confirm that selected captures show
the same physical location and comparable accepted ROI, and provide stable
location, target, and temporal-group identifiers. One capture produces only a
single-observation description; at least two compatible times are required for
a temporal range. Multiple independent temporal groups may be defined.
Pixelwise change maps additionally require confirmed cross-capture
registration, its method, and a stable registration ID.

Normal-route LUHK is read-only official 10 m context and remains separate from
the visible-image surface-cover labels. For a Part C* polygon, only the accepted
target interior may receive its target-scoped context; the exterior remains
unknown and is excluded from formal target statistics.

The v0.3.2 LUHK work reconnects the established Part C method; it is not a new
classification algorithm. It preserves the existing official cell mapping,
category vocabulary, and approximate metadata-derived north-up footprint.
Changes are limited to exposing the mapping on the native thermal grid,
validating dependencies and unavailable states, and carrying its provenance
through the GUI, cache, canonical result, and Part E.

### Verified real-data snapshot (2026-07-22)

A real normal-Part-C desktop GUI check confirmed the terminal contract: Cancel
returned non-accepted and created no new successful canonical result; Accept
returned accepted and continued to canonical creation. A separate explicit
three-capture football-field run completed at workflow run
`run_20260722T053855Z` with matching run-scoped Part E. Its primary ROI-mean
temperature range was 20.362969 degC and its provisional TAT3-based ROI-mean
delta-T range was 24.36297 degC. The three independently accepted polygons were
confirmed only at target level, so pixelwise change is unavailable without
cross-capture registration; the 09:11:28--17:04:53 window is partial daytime
coverage, not a full-day result. See `docs/v0_3_benchmark.md` for exact paths,
additional statistics, output counts, and scientific limits.

The newer workflow run `run_20260722T055625Z` completed all six image routes
(five normal pilots plus one football-field Part C* capture). Its run-scoped
Part E also completed and passed final validation. The run-scoped result has
exactly those six image IDs, 8 spectrum PNG/PDF pairs, 48 spatial PNG/PDF pairs,
and a single-capture football temporal report that supplies descriptive
statistics while explicitly withholding trend and peak-to-trough claims.

Temporary manual TAT3 point/region analysis is deliberately separate:

```powershell
.\.venv\Scripts\python.exe scripts\run_tat3_manual_analysis.py --help
```

It writes an ignored temporary bundle and does not modify the canonical
warehouse or result index. See the v0.2 documents above. The numbered scripts
remain the verified scientific implementations and compatibility entry points;
`docs/v0_1_workflow.md` is retained for the earlier release contract.

Install the Python dependencies in your environment, then run:

```bash
python3 -m pip install -r requirements.txt
```

Generate or refresh the core metadata tables with:

```bash
python3 scripts/01_create_vt_pairs.py
python3 scripts/02_extract_dji_metadata.py
```

The current pilot LUHK grid workflow is listed below. Part D Round 1
temperature extraction has been completed locally for the five pilot thermal
images; refreshing those matrices still depends on the external DJI Thermal SDK
setup.

Do not proceed to footprint, cover, or LUHK overlay production until per-image
camera selection has been validated. DJI Matrice 4T visible `_V.JPG` images may
come from wide, medium tele, or tele visible cameras.

## Dataset layout

Raw drone data is stored under `data/raw/HKUST/`. Garden Hill session folders
are directly below the dataset folder, while HKUST session folders are below
`DCIM/`. The V/T inventory script scans recursively, so it handles both layouts
without assuming a fixed directory depth.

## V/T pair inventory

`scripts/01_create_vt_pairs.py` scans JPG/JPEG files whose names end in `_V` or
`_T` and builds pairs in two stages. It first pairs files in the same parent
directory whose complete base names match. Remaining files may pair by their
final sample number, such as `0071`, only within the same parent/session.
Timestamp differences are allowed and recorded. The script never pairs across
sessions, and multiple candidates are marked ambiguous instead of being chosen
arbitrarily. It writes the stable inventory to `data/metadata/vt_pairs.xlsx`.

Run it from the project root:

```bash
python3 scripts/01_create_vt_pairs.py
```

The output columns are:

- `pair_id`: stable project-relative identifier for the record
- `dataset_folder`: first folder below `data/raw/HKUST/`
- `location`: inferred GardenHill, HKUST, or Unknown location
- `capture_date`: session date when available, otherwise dataset date
- `session_folder`: nearest parent folder beginning with `DJI_`
- `base_name`: exact common base name, or a sample-number label for fallback pairs
- `sample_number`: final numeric sample identifier, with leading zeros preserved
- `v_path`, `t_path`: project-relative POSIX paths
- `status`: paired, missing, or duplicate state
- `match_method`: exact base-name, session sample-number, unmatched, or ambiguous
- `timestamp_difference_seconds`: absolute V/T timestamp difference when parseable
- `pilot`: whether the record matches the explicitly configured unique pilot
- `notes`: duplicate paths or scan metadata that needs attention

Pilot selection is explicit. Set `PILOT_PAIR_ID` near the top of
`scripts/01_create_vt_pairs.py` to one generated project-relative `pair_id`, then
rerun the script. When it is `None`, no record is marked as the pilot; sample
number `0016` alone does not automatically select a pilot.

## Revised A-E workflow

- Part A: inventory and spatial foundation.
- Part B: V/T ROI alignment and visible-image surface-cover classification
  inside the thermal ROI.
- Part C: pilot LUHK context, physical surface-cover masks, and separate shadow
  masks.
- Part D: thermal temperature extraction and QA, including later radiometric
  parameter validation.
- Part E: statistical analysis and visualization of delta-T distributions, with
  prediction as an optional later extension.

## Part E formal pixel-spectrum workflow

The primary Part E scientific figures are pixel-level **ΔT distribution/density
spectra**. Here, spectrum means a statistical distribution of ΔT values, not an
electromagnetic or multispectral spectrum. One formal observation is one
accepted finite thermal pixel that is also `analysis_eligible` and inside
`target_mask`:

```text
delta_t_c = temperature_c - ambient_temperature_c
```

All source pixels remain in the canonical Parquet. Formal figures and
exploratory tests use only the target-eligible population and spatially thinned
samples of original pixels; LUHK cells and sampling tiles are never averaged.
Spatial thinning disperses records but does not remove spatial autocorrelation.

The ordinary launcher runs and validates the spectrum stage automatically.
Formal PNG/PDF figures and captions are linked from the run's
`USER_RESULTS.md`. Boxplots, coverage charts, spatial panels, and Excel charts
remain supporting outputs. Python/SciPy is the formal plotting engine; Excel is
optional. The lower-level Part E runner remains a developer interface rather
than a required user step.

Part A does not include V/T geometric alignment, visible/thermal ROI matching,
segmentation, temperature extraction, LUHK overlay production, or model
preparation.

## Part B classification scheme

Part B keeps broad land use and visible surface cover as separate layers.
Broad land use retains the original LUHK categories, while surface cover is
independently annotated from visible drone imagery. Shadow is stored as a
separate mask rather than a surface-cover class.

LUHK is a broad-brush, 10 m resolution context dataset and must not be treated
as pixel-level surface-cover ground truth for drone imagery. The complete
classification definitions and annotation principles are documented in
`docs/part_b_land_use_surface_cover_scheme.txt`.

## Progress update

The current revised planning overview is summarized in
`docs/revised_project_overview.md`. The older June 2026 Part B pilot progress
note is archived at `docs/archive/deprecated/progress_update_part_b_pilot_plan.md`
for research history, but its A-D framing has been superseded by the current
A-E structure.

## Current V/T footprint and LUHK grid workflow

The current pilot workflow estimates separate footprints for DJI visible
`_V.JPG` and thermal `_T.JPG` images. Thermal analysis still uses `_T.JPG`
geometry. Visible overlays use visible geometry and visible metadata; they must
not borrow the thermal fallback profile. These scripts are spatial-support
tools for later stages, not Part A deliverables.

Run the current pilot sequence from the project root:

```bash
python3 scripts/03_estimate_image_footprints.py
python3 scripts/04_create_10m_grids_pilot.py --max-pairs 5
python3 scripts/05_assign_luhk_landuse_pilot_overlays.py
```

Step 03 writes one footprint row per image to
`data/processed/footprints/image_footprints.xlsx`. Step 04 selects five valid
HKUST V/T pairs and creates 10 m cells aligned to the official LUHK raster
row/column grid, not to each image footprint origin. Step 05 draws separate
visible, thermal, common-cell, and EPSG:2326 map overlays for each pilot pair.

The explicit V/T camera rules, metadata priority, LUHK-aligned grid rule, and
remaining limitations are documented in `docs/camera_parameter_assumptions.md`.

## Data-management rule

Treat `data/raw/` as read-only source data. Do not move, rename, overwrite, or
write generated data into the original DJI folders. Raw data is not uploaded to
GitHub. Generated inventories such as `data/metadata/vt_pairs.xlsx` store only
paths relative to the project root.
