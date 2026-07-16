# Part E Cell-Level Delta-T Dataset Build Summary

**Provisional-result rule:** This is a provisional pilot delta-T analysis using temperature matrices that have completed structural extraction QA but have not yet completed full radiometric parameter validation.

- Minimum valid temperature coverage fraction: 0.5

## Variants Built

- `all_finite`: observations=2992, analysis_valid=2970, audit_exclusions=22

## Validation

- PASS: no duplicate primary keys, non-negative counts, and delta-T arithmetic checks passed.

## Outputs

- Main all-finite cell dataset: `outputs/part_e/tables/part_e_cell_delta_t_observations_all_finite.csv`
- Cell exclusion audit: `outputs/part_e/tables/part_e_cell_delta_t_exclusion_audit.csv`
