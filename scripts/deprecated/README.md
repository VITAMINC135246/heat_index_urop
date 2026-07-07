# Deprecated Scripts

These scripts are kept for research history, but they are no longer part of the
current Part B workflow.

- `03_estimate_thermal_footprints.py`: compatibility wrapper for an older
  thermal-only footprint workflow. Use `scripts/03_estimate_image_footprints.py`
  when footprint estimates are needed.
- `05_assign_luhk_landuse_example.py`: compatibility wrapper for an older
  single-example LUHK overlay workflow. Use
  `scripts/05_assign_luhk_landuse_pilot_overlays.py` for LUHK context overlays.
- `plot_hong_kong_land_use.py`: early standalone LUHK plotting script that reads
  the original LUHK ZIP directly. The revised workflow treats LUHK as official
  land-use context and uses visible drone images for surface-cover segmentation
  experiments.

Do not delete these files without checking whether earlier progress reports,
figures, or notes refer to them.
