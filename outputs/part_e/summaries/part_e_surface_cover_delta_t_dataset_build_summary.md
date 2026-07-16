# Part E Cell-By-Surface-Cover Delta-T Dataset Build Summary

**Provisional-result rule:** This is a provisional pilot delta-T analysis using temperature matrices that have completed structural extraction QA but have not yet completed full radiometric parameter validation.

- Minimum valid class temperature pixels: 30
- Minimum class fraction of valid classified pixels: 0.01

## Variants Built

- `all_finite`: observations=4259, analysis_valid=4160, audit_exclusions=99

## Validation

- PASS: primary keys, taxonomy, and delta-T arithmetic checks passed.

## Outputs

- Main all-finite cell-cover dataset: `outputs/part_e/tables/part_e_surface_cover_delta_t_observations_all_finite.csv`
- Cell-cover exclusion audit: `outputs/part_e/tables/part_e_surface_cover_delta_t_exclusion_audit.csv`
