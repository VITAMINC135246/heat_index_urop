# Version 0.1 local workflow

Version 0.1 adapts the verified five-image pilot into a modular local MVP. It
does not replace the existing alignment, reviewed visible annotation, DJI
temperature extraction, or formal Part E statistical methods.

## Entry point and modes

```powershell
.\.venv\Scripts\python.exe scripts\run_analysis.py --help
```

Selected-file mode requires one visible and one thermal file per group:

```powershell
.\.venv\Scripts\python.exe scripts\run_analysis.py `
  --surface-cover grass_low_vegetation `
  selected --group path\image_V.JPG path\image_T.JPG
```

Dataset mode discovers exact V/T filename pairs recursively and processes all
eligible groups unless a benchmark-derived `--max-groups` guard is supplied:

```powershell
.\.venv\Scripts\python.exe scripts\run_analysis.py `
  dataset --dataset 20260202_Thermal_HKUST
```

Automatic partner discovery for incomplete groups is out of scope.

## Part A and Part B

Part A returns structured file, role, identifier, timestamp, session,
readability, metadata, and thermal-availability validation. It does not claim
that two images show matching content.

Part B separately records scene correspondence, coverage, the automatic
candidate, manual review, and the final state. An improved cross-modal score is
only a candidate. Normal Part C requires:

```text
scene_correspondence = accepted
coverage_class = thermal_fully_supported_by_visible
manual_review_status = accepted
final_alignment_status = accepted
```

An optional `--part-b-review` JSON is keyed by group or image ID:

```json
{
  "decisions": {
    "DJI_20260202091128_0058": {
      "scene_correspondence": "rejected",
      "coverage_class": "no_usable_overlap",
      "auto_candidate_status": "available",
      "manual_review_status": "rejected",
      "review_evidence_path": "outputs/part_b/review_packages/..."
    }
  }
}
```

The legacy pilot adapter accepts a pilot group only when its manually reviewed
Part C mask and successful Part D grid-compatible temperature result exist. It
does not use the automatic score alone as acceptance.

## Part C* polygon rule

The Matplotlib tool supports draw, clear/redraw, accept, and cancel. A physical
surface-cover category must be selected before drawing. `--polygon-json`
supports reproducible reviewed coordinates and automated tests.

- Inside an accepted polygon: `label_known=true`, the selected class is
  assigned, and finite pixels are eligible for target/surface-cover analysis.
- Outside: `label_known=false`, the integer array uses non-physical sentinel
  `-1`, `exclusion_reason=label_unknown`, and pixels are not eligible for
  target/surface-cover analysis.
- The full temperature matrix remains available for provenance and overall
  thermal summaries.
- Cancellation creates no successful canonical result and never enters Part E.

`known_mask.npy`, not the integer sentinel, is authoritative.

## Temperature and canonical result

Temperature is resolved from an explicit NPY, a compatible pilot Part D
matrix, or DJI SDK extraction with a matching TAT3 parameter row. The SDK route
uses the existing distance, humidity, emissivity, ambient, and reflected
temperature parameters.

Each successful image uses:

```text
data/processed/images/<image_id>/
  manifest.json
  temperature.npy
  surface_cover_labels.npy
  known_mask.npy
  shadow_mask.npy          # optional
  pixels.parquet
```

The manifest stores versions, source/config hashes, IDs, routes, native
dimensions, temperature metadata, label provenance, polygon coordinates,
QA/review state, known/unknown counts, exclusions, and artifact hashes.

The lightweight local result index accepts a cache hit only when source hashes,
schema version, processing version, configuration hash, QA/status, manifest,
and required artifacts are compatible. A hit skips Parts A--D.

## Part E and optional exports

The common adapter combines only successful compatible results and retains:

```text
source_method
label_provenance
label_known
analysis_eligible
exclusion_reason
target_name
annotation_review_status
```

Formal Part E sampling now derives native image dimensions, carries provenance,
and keeps source methods separate when several are present. Polygon exterior
pixels cannot enter a surface-cover family.

Full pixel CSV and Excel are opt-in:

```powershell
# Default: no large pixel CSV or Excel
.\.venv\Scripts\python.exe scripts\part_e\run_part_e_pipeline.py

# Explicit large per-image delivery
.\.venv\Scripts\python.exe scripts\part_e\run_part_e_pipeline.py `
  --include-per-image-excel
```

Existing pilot artifacts are preserved; these defaults affect regeneration.

## Tests and workload limits

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\benchmark_v0_1.py
```

X (groups/request) and Y (retained canonical images) are different limits. The
benchmark measures validation/decode, NPY loading, polygon rasterization,
Parquet reading/summarization, and actual artifact sizes. It calculates a
numeric interactive X only when measured manual-review seconds and an
interaction budget are supplied. It calculates Y only when a storage budget is
supplied. Optional CSV/Excel is excluded from canonical retention.

### 2026-07-17 local benchmark observation

Two consecutive five-image runs (cold/warm filesystem cache) observed:

- Part A validation p95: 0.009--0.024 seconds per group.
- Existing temperature NPY median load: 0.0005--0.0098 seconds per image.
- Polygon rasterization p95 at 512 x 640: 0.00008--0.00012 seconds.
- Three-column read of the 1,638,400-row pilot Parquet: 0.061--0.062 seconds.
- Image-level summary of that table: 0.122--0.133 seconds.
- One schema-0.1 canonical result currently occupies 3,319,871 bytes.
- The five legacy full-pixel CSV files occupy 1,046,292,296 bytes, versus
  6,828,746 bytes for the combined compressed pilot Parquet.
- The five legacy per-image workbooks occupy 270,621,553 bytes.

These are machine observations, not general capacity claims. The provisional
rollout guard is one group per interactive polygon invocation and five groups
for the first unattended non-pilot batches. This is an operating-safety
recommendation, not a built-in processing limit: dataset mode still defaults
to all eligible groups, and `--max-groups` is an explicit caller guard. Raise X
only after recording Part B candidate generation, DJI SDK extraction, full
Part E, peak-memory, and manual-review p95 values.

No fixed Y is asserted without a storage budget. Calculate it from the measured
canonical directory size (or a larger representative sample) and exclude
opt-in CSV/Excel delivery files from the canonical-retention calculation.

## Known limitations

- New normal-route groups require reviewed Part C label outputs from the
  existing workflow or `--normal-labels-npy`; semantic review is not automated.
- Part B coverage classification remains an explicit human-reviewed state.
- New R-JPEG extraction requires a matching TAT3 row and external DJI SDK.
- The common adapter provides provenance-safe aggregation and descriptive
  source summaries. Formal spectra remain most thoroughly validated on the
  five-image visible-review pilot.
- Part A exposes altitude and camera metadata fields, but new datasets may need
  the existing DJI metadata extraction table before those fields are complete.
