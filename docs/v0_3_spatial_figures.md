# Version 0.3 canonical spatial figures

## Input and unit

`scripts/part_e/05_generate_pixel_spatial_figures.py` reads the shared
canonical Parquet directly. It has no dependency on the legacy five-pilot
XLSX/mask/temperature tables. A spatial unit is
`image_id × source_method × measurement_type`; duplicate source units for one
image receive source-qualified filenames.

Only `full_thermal_pixel` and `polygon_selected_thermal_pixel` can produce
native grids. TAT3 points/regions receive recorded not-applicable exclusions.
Rows and columns are validated for non-negative coordinates, duplicates,
dynamic dimensions, and complete native coverage.

## Output family

Every generated unit has PNG and PDF versions of:

1. temperature map;
2. ΔT map, or an explicit unavailable panel when ambient is invalid;
3. surface-cover overlay, with unknown pixels retained;
4. LUHK overlay, or explicit unavailable panel;
5. target/polygon overlay, or not-applicable panel for unrestricted full image;
6. shadow overlay, or explicit unavailable panel;
7. analysis-eligibility/unknown mask;
8. combined spatial QA panel.

Titles/notes include measurement type, source method, temperature source,
surface/LUHK provenance, target ID, and target name. Polygon boundaries are
derived from the accepted per-capture target mask. Inside target is visibly
distinguished from outside unknown context; target cover/LUHK is never
extrapolated outside.

## Validation and resume

The directory also contains:

- `spatial_figure_manifest.csv`;
- `spatial_figure_exclusions.csv`;
- `spatial_figure_validation.json`.

The validation JSON records canonical SHA-256, spatial-method SHA-256, and
every expected figure file. Formal Part E refuses completion if either hash
differs, a file is absent/small, or both generated files and recorded
exclusions are empty. Resume rechecks the method and listed files rather than
trusting directory existence.
