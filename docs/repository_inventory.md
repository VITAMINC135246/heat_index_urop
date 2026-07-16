# Repository structure and data/output boundary

This audit reflects the repository after the Part E cleanup on 2026-07-16.
It defines the intended boundary and records exceptions that should be handled
in a future coordinated migration rather than by moving files ad hoc.

## Intended boundary

### `data/`

`data/` contains inputs that may be consumed by more than one analysis or
pipeline stage:

- `data/raw/`: immutable source imagery and vendor files; local and ignored.
- `data/base/`, `data/luhk/`, and the local TDOP folders: external reference
  rasters; local and ignored.
- `data/metadata/`: compact manifests, identifiers, acquisition metadata, and
  provenance tables.
- `data/annotations/`: human-reviewed labels and annotation workbooks.
- `data/processed/<part>/`: reproducible machine-readable intermediates that
  downstream stages may consume.

Files in `data/` should not be presentation-only artifacts. Large,
reproducible payloads may remain ignored when their source and build procedure
are documented.

### `outputs/`

`outputs/` contains results intended for inspection, communication, or final
delivery:

- figures and visual QA;
- reports and summaries;
- compact analytical result tables;
- review packages and contact sheets;
- Excel workbooks and exported charts.

An output may be consumed by a later presentation step within the same
pipeline, but a durable cross-Part dependency should normally point to
`data/processed/` or `data/metadata/`.

## Part E status

Part E now follows the boundary consistently:

- input manifest: `data/metadata/part_e_ambient_temperature_manifest.csv`;
- canonical pixel dataset, samples, and Excel source payloads:
  `data/processed/part_e/`;
- analytical tables, QA, summaries, figures, and workbooks:
  `outputs/part_e/`;
- current implementation map: `scripts/part_e/README.md`.

The active script directory contains one formal implementation with unique
stage numbers `00` through `11`. Superseded cell-level scripts, tables,
summaries, and unnumbered spectrum figures were removed from the active tree.
They remain available from Git history and the
`pre-e2e-validation-2026-07-15` tag.

## Known boundary exceptions

These are real structure issues, but they were not moved in this cleanup
because paths are embedded in scripts, workbooks, manifests, and existing
progress records:

1. Part C reads accepted Part B alignment summaries from
   `outputs/part_b/summaries/`.
2. Parts D and E read final Part C masks and manifests from
   `outputs/part_c/masks/` and `outputs/part_c/summaries/`.
3. Part E reads the Part D extraction summary from
   `outputs/part_d/summaries/`.

These paths make selected `outputs/` files function as durable processed data.
A future coordinated migration should place the machine-readable alignment
transforms, mask arrays, mask manifests, temperature extraction summaries, and
accepted parameter tables under `data/processed/part_b/`,
`data/processed/part_c/`, and `data/processed/part_d/`. Human-facing copies
may remain under `outputs/`.

Additional naming exceptions:

- `data/LUHK2024_SC.xlsx` is reference metadata and would fit more strictly
  under `data/metadata/` or `data/reference/`.
- local `data/TDOP_TIFF_*/` and
  `data/True_Digital_Orthophoto_TDOP_GEOPACKAGE/` folders are raw/reference
  inputs but sit directly under `data/`; they are ignored, so this is a local
  layout issue rather than a Git payload issue.
- root-level numbered scripts are the historical Part A workflow, while later
  stages use `scripts/part_b/` through `scripts/part_e/`.
- `outputs/archive/figures_quick_cheacked/` preserves a historical typo. It
  should only be renamed if old documentation links are updated together.

## Version-control policy

- Track source code, configuration, documentation, compact manifests, compact
  QA/results, and selected final deliverables.
- Ignore raw imagery, external rasters, caches, environments, large
  reproducible Parquets, per-image Part E workbooks, and workbook previews.
- Do not use `outputs/` as the only location for a machine-readable artifact
  required by another Part when the next coordinated path migration is made.
- Prefer Git history or a named tag over keeping duplicate deprecated outputs
  in the active tree.
