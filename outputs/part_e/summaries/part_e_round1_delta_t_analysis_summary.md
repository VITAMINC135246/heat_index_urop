# Part E formal pixel-level ΔT spectrum and statistical summary

> Provisional five-image HKUST pilot. Part D apparent-temperature radiometric plausibility review and the image-level TAT3 ambient parameters remain limitations; results do not generalize to all of Hong Kong.

## Method and observation unit

The formal observation is one original thermal pixel. For every accepted finite pixel:

```text
delta_t_c = temperature_c - ambient_temperature_c
```

All 1,638,400 accepted finite pilot pixels remain in the canonical Parquet. Formal plots use dispersed individual pixels selected by `spatially_thinned_stratified_pseudorandom` with primary seed 20260715; neither 10 m LUHK cells nor 8 px sampling tiles are averaged. Spatial thinning does not remove spatial autocorrelation, so sampled pixels are not described as independent observations.

Here, spectrum means the statistical distribution/density spectrum of pixel-level ΔT, not an electromagnetic reflectance or multispectral-band spectrum. Python/SciPy is the formal plotting engine; density curves use Scott's bandwidth rule, common comparison axes, and no extrapolation beyond each group's observed sampled range.

## 1. Overall pixel ΔT spectrum

The overall image-stratified sample contains 12,500 pixels from 5 images, representing 1,638,400 accepted finite pixels. Median ΔT is 3.68 °C, mean is 5.41 °C, Q25–Q75 is 1.71 to 8.38 °C, and Q05–Q95 is -0.56 to 16.67 °C. Figure 00 should be used with the descriptive table; curve height is normalized density, not pixel count.

## 2. LUHK spectra

- 73 | Woodland / shrubland / grassland / wetland: sampled/full n=150/7,253; images=2/2; median=1.07 °C; mean=1.53 °C; Q25–Q75=0.58 to 2.54 °C; Q05–Q95=0.20 to 3.66 °C.
- 72 | Woodland / shrubland / grassland / wetland: sampled/full n=613/31,408; images=1/1; median=1.56 °C; mean=2.01 °C; Q25–Q75=0.80 to 2.85 °C; Q05–Q95=0.20 to 4.91 °C.
- 71 | Woodland / shrubland / grassland / wetland: sampled/full n=1,346/76,074; images=4/4; median=2.09 °C; mean=2.31 °C; Q25–Q75=1.18 to 3.17 °C; Q05–Q95=0.27 to 4.80 °C.
- 51 | Other urban / built-up land: sampled/full n=4/200; images=1/1; median=3.34 °C; mean=3.64 °C; Q25–Q75=3.11 to 3.86 °C; Q05–Q95=2.66 to 5.04 °C. KDE status: insufficient_sample (sampled n < 100).
- 31 | GIC / open space: sampled/full n=10,000/1,523,465; images=5/5; median=3.90 °C; mean=5.68 °C; Q25–Q75=1.83 to 9.05 °C; Q05–Q95=-0.64 to 16.97 °C.

LUHK class 51 has too few sampled pixels for a smooth spectrum. Codes 71, 72, and 73 retain separate official codes even where their displayed broad names coincide. The approximate north-up footprint-to-LUHK assignment remains a spatial-label limitation.

## 3. Physical surface-cover spectra

- Vegetation / tree canopy: sampled/full n=10,000/696,329; images=5/5; median=2.72 °C; mean=3.20 °C; Q25–Q75=1.68 to 4.16 °C; Q05–Q95=0.35 to 7.58 °C.
- Concrete pavement: sampled/full n=6,677/322,856; images=5/5; median=5.56 °C; mean=6.87 °C; Q25–Q75=2.97 to 10.32 °C; Q05–Q95=0.39 to 17.50 °C.
- Roof: sampled/full n=9,406/569,601; images=5/5; median=6.41 °C; mean=6.93 °C; Q25–Q75=1.61 to 11.74 °C; Q05–Q95=-1.73 to 18.56 °C.
- Grass / low vegetation: sampled/full n=770/39,392; images=5/5; median=11.95 °C; mean=10.57 °C; Q25–Q75=7.28 to 13.77 °C; Q05–Q95=1.92 to 16.74 °C.
- Bare soil: sampled/full n=221/10,222; images=2/2; median=13.33 °C; mean=11.84 °C; Q25–Q75=7.84 to 15.92 °C; Q05–Q95=1.67 to 19.02 °C.

The sampled medians and quartiles support the location ordering shown in Figure 02, while the density spectra additionally expose spread, skewness, overlap, and possible multimodality. Those visual features are descriptive and are not interpreted from curve height alone.

## 4. Within-GIC surface-cover spectra

- Vegetation / tree canopy: sampled/full n=10,000/581,928; images=5/5; median=2.72 °C; mean=3.22 °C; Q25–Q75=1.68 to 4.20 °C; Q05–Q95=0.27 to 7.73 °C.
- Concrete pavement: sampled/full n=6,673/322,791; images=5/5; median=5.56 °C; mean=6.87 °C; Q25–Q75=2.97 to 10.32 °C; Q05–Q95=0.39 to 17.50 °C.
- Roof: sampled/full n=9,398/569,132; images=5/5; median=6.41 °C; mean=6.92 °C; Q25–Q75=1.61 to 11.74 °C; Q05–Q95=-1.73 to 18.56 °C.
- Grass / low vegetation: sampled/full n=770/39,392; images=5/5; median=11.95 °C; mean=10.57 °C; Q25–Q75=7.28 to 13.77 °C; Q05–Q95=1.92 to 16.74 °C.
- Bare soil: sampled/full n=221/10,222; images=2/2; median=13.33 °C; mean=11.84 °C; Q25–Q75=7.84 to 15.92 °C; Q05–Q95=1.67 to 19.02 °C.

Figure 04 limits the overlay to well-supported groups with at least the formal minimum sampled n and at least two contributing images. Figure 03 retains facets for all adequately sampled within-GIC cover classes so smaller densities do not disappear behind larger curves.

## 5. Between-image consistency

- DJI 2026-01-07 143259_0005: sampled/full n=2,500/327,680; images=1/1; median=2.01 °C; mean=3.22 °C; Q25–Q75=0.80 to 3.83 °C; Q05–Q95=-0.26 to 13.26 °C.
- DJI 2026-01-07 143328_0008: sampled/full n=2,500/327,680; images=1/1; median=3.90 °C; mean=5.64 °C; Q25–Q75=1.64 to 8.71 °C; Q05–Q95=-0.94 to 16.94 °C.
- DJI 2026-01-07 143320_0007: sampled/full n=2,500/327,680; images=1/1; median=4.16 °C; mean=5.85 °C; Q25–Q75=2.27 to 8.21 °C; Q05–Q95=-0.61 to 17.35 °C.
- DJI 2026-01-07 143344_0009: sampled/full n=2,500/327,680; images=1/1; median=4.40 °C; mean=6.12 °C; Q25–Q75=1.98 to 9.57 °C; Q05–Q95=-0.36 to 17.35 °C.
- DJI 2026-01-07 143401_0011: sampled/full n=2,500/327,680; images=1/1; median=4.77 °C; mean=6.21 °C; Q25–Q75=2.36 to 10.62 °C; Q05–Q95=-0.75 to 16.82 °C.

Between-image location and shape differences are visible in Figure 05. Because the pilot contains only five temporally adjacent images, these differences are a consistency check rather than an estimate of broad temporal or city-wide variability.

## 6. Sampling stability

- luhk / 31 | GIC / open space: sampled median range across 21 seeds=3.78 to 3.93 °C.
- luhk / 51 | Other urban / built-up land: sampled median range across 21 seeds=2.92 to 6.31 °C.
- luhk / 71 | Woodland / shrubland / grassland / wetland: sampled median range across 21 seeds=2.01 to 2.09 °C.
- luhk / 72 | Woodland / shrubland / grassland / wetland: sampled median range across 21 seeds=1.41 to 1.56 °C.
- luhk / 73 | Woodland / shrubland / grassland / wetland: sampled median range across 21 seeds=0.96 to 1.14 °C.
- surface_cover / Bare soil: sampled median range across 21 seeds=13.11 to 13.78 °C.
- surface_cover / Concrete pavement: sampled median range across 21 seeds=5.45 to 5.59 °C.
- surface_cover / Grass / low vegetation: sampled median range across 21 seeds=11.92 to 12.10 °C.
- surface_cover / Roof: sampled median range across 21 seeds=6.20 to 6.50 °C.
- surface_cover / Vegetation / tree canopy: sampled median range across 21 seeds=2.69 to 2.72 °C.

Figure 07 displays the distribution of group medians across the primary seed and secondary seeds. Stability across seeds addresses sampling sensitivity only; it does not make spatially correlated pixels independent.

## 7. Effect sizes and exploratory tests

The formal sampled-pixel tables contain 113 effect-size rows and 117 statistical-test rows (37 executed and 80 skipped under coverage rules). P-values are exploratory, use false-discovery-rate adjustment where applicable, and support rather than replace the spectrum interpretation. Conclusions should cross-reference distribution summaries, effect sizes, image coverage, and seed stability.

The surface-cover × shadow contrast is **not estimable** because the five reviewed masks contain no valid `shadow_flag=1` pixels. No shadow-present observations or empty spectrum figure were created.

## 8. Uncertainty summary and supporting boxplots

Figure 08 reports sampled medians with percentile 95% bootstrap intervals from 1,000 pixel resamples. These intervals are descriptive because neighbouring-pixel correlation remains. Existing boxplots, coverage charts, image comparisons, the earlier stability chart, and the mean-CI chart are supporting outputs under `outputs/part_e/figures/excel/`; they are not the primary figure family.

## 9. Spatial QA

Full-pixel temperature, ΔT, LUHK, physical-cover, shadow, and combined panels under `outputs/part_e/figures/spatial_maps/` support alignment and spatial interpretation. They do not replace the sampled-pixel distribution analysis.

## 10. Excel deliverables

The main statistical workbook and five pilot pixel workbooks are preserved as interactive delivery layers. Native Excel charts are supporting figures. Excel COM is not required for the formal Python spectrum stage, and future batch runs should not create hundreds of full per-image workbooks unless explicitly requested.

## Ambient parameters used

| Image | Ambient temperature (°C) | Source | Validation status |
|---|---:|---|---|
| DJI_20260107143259_0005 | 11.0 | TAT3 | provisional |
| DJI_20260107143320_0007 | 10.6 | TAT3 | provisional |
| DJI_20260107143328_0008 | 10.5 | TAT3 | provisional |
| DJI_20260107143344_0009 | 9.9 | TAT3 | provisional |
| DJI_20260107143401_0011 | 9.9 | TAT3 | provisional |

## Primary outputs

- Formal figures and captions: `outputs/part_e/figures/spectrum/`.
- Spectrum source/summary table: `outputs/part_e/tables/part_e_pixel_delta_t_spectrum_summary.csv`.
- Grouped sampled/full summaries: `outputs/part_e/tables/part_e_delta_t_by_*_pixels.csv`.
- Effect sizes and exploratory tests: `outputs/part_e/tables/part_e_pixel_effect_sizes.csv` and `part_e_pixel_statistical_tests.csv`.
- Final QA: `outputs/part_e/qa/part_e_final_qa.md`.

## Reproducibility

```powershell
.\.venv\Scripts\python.exe scripts\part_e\run_part_e_pipeline.py --config config\part_e_delta_t_analysis.json --resume --from-stage spectrum --to-stage spectrum
.\.venv\Scripts\python.exe scripts\part_e\run_part_e_pipeline.py --config config\part_e_delta_t_analysis.json --resume --from-stage final-qa --to-stage report
```

The deprecated `06_create_clear_spectrum_figures.py` is research history only and is never called by the formal pipeline.

## Limitations

- Only five HKUST pilot images are included; results do not generalize to all of Hong Kong.
- TAT3 ambient parameters and Part D apparent-temperature physical plausibility remain provisional.
- Neighbouring thermal pixels remain spatially correlated after thinning.
- LUHK pixel labels use an approximate north-up footprint model that ignores recorded yaw.
- No shadow-present pixels are available, so a shadow effect is not estimable.
- Exploratory p-values do not establish causal or city-wide effects.
