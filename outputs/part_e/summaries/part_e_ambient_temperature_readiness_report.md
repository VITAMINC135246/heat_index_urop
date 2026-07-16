# Part E ambient-temperature readiness report

## Status

- **Ready and consumed for the provisional five-image pilot.**
- Each pilot image has exactly one finite image-level TAT3 ambient parameter.
- The active standardized manifest is
  `data/metadata/part_e_ambient_temperature_manifest.csv`.
- Values match the Part D TAT3 extraction summary; the deprecated 25 °C
  placeholder is not used.
- TAT3 parameters are not independently validated meteorological air
  temperatures, so the Part E results remain provisional.

## Formal use

For every accepted finite thermal pixel:

```text
delta_t_c = temperature_c - ambient_temperature_c
```

The completed canonical pixel Parquet contains 1,638,400 rows across five
512×640 pilot images. Formal spectra use spatially thinned samples of original
pixel values and do not aggregate temperatures by LUHK cell or sampling tile.

## Pilot values

| Image | Ambient temperature (°C) | Source | Status |
|---|---:|---|---|
| DJI_20260107143259_0005 | 11.0 | TAT3 | provisional |
| DJI_20260107143320_0007 | 10.6 | TAT3 | provisional |
| DJI_20260107143328_0008 | 10.5 | TAT3 | provisional |
| DJI_20260107143344_0009 | 9.9 | TAT3 | provisional |
| DJI_20260107143401_0011 | 9.9 | TAT3 | provisional |

If a later project-approved meteorological source supersedes TAT3, replace the
manifest with one documented finite value per image, then rerun only the
smallest affected Part E stages.
