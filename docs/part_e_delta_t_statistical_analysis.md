# Part E Pixel-Level ΔT Statistical Analysis and Spectra

Part E is the provisional five-image HKUST pilot for pixel-level delta-temperature
analysis. Its primary scientific visual result is the **ΔT distribution/density
spectrum**. In this project, spectrum means a statistical distribution of
pixel-level ΔT values; it does not mean electromagnetic reflectance or
multispectral-band analysis.

## Formal observation and formula

The formal observation is one original thermal pixel. For every accepted finite
pixel:

```text
delta_t_c = temperature_c - ambient_temperature_c
```

All finite pixels are preserved in
`data/processed/part_e/part_e_pixel_delta_t.parquet`. LUHK cell IDs, sampling
tiles, and image identifiers are provenance or sampling strata only. The formal
workflow does not calculate LUHK-cell means, tile means, neighbouring-pixel
means, or other spatial aggregates before analysis.

The image-level ambient values are provisional TAT3 parameters reconciled to
the Part D extraction summary. They are not independently validated
meteorological air-temperature observations.

## Eligibility and data layers

- Overall and image spectra require an accepted finite thermal pixel.
- LUHK spectra additionally require a valid approximate LUHK label.
- Surface-cover spectra additionally require a reviewed valid physical-cover
  label.
- Within-GIC spectra require LUHK code 31 and a valid physical-cover label.
- Surface-cover × shadow contrasts require both `shadow_flag=0` and
  `shadow_flag=1` within the same cover class with adequate sampled pixels.

LUHK remains official 10 m broad land-use context, not fine physical-cover
ground truth. Physical cover comes from reviewed Part C thermal-grid masks.
Shadow remains a separate binary mask and is never recoded as a cover class.

## Sampling

Formal figures and exploratory tests use deterministic,
spatially-thinned, stratified pseudorandom samples of individual pixels. The
primary seed is `20260715`; twenty secondary seeds support stability analysis.
An 8 px tile may contribute at most one selected pixel to the initial thinned
candidate set, but tile values are never averaged. Selected records retain the
original pixel-level ΔT values.

Spatial thinning improves geographic dispersion but does not eliminate spatial
autocorrelation. Sampled pixels must not be described as completely independent
observations.

## Primary spectrum figure family

The formal Python stage is
`scripts/part_e/04_generate_pixel_delta_t_spectra.py`. It reads only the
completed sampled-pixel Parquets and existing coverage/stability tables. It
writes PNG and PDF figures, a source summary, and captions under:

- `outputs/part_e/figures/spectrum/`
- `outputs/part_e/tables/part_e_pixel_delta_t_spectrum_summary.csv`

The numbered family is:

1. overall pixel ΔT spectrum;
2. LUHK-class spectra;
3. physical surface-cover spectra;
4. within-GIC cover spectra;
5. within-GIC cover overlay;
6. between-image spectra;
7. shadow contrast, only when estimable;
8. sampling-stability distribution;
9. sampled-median bootstrap uncertainty summary.

The current pilot has no valid `shadow_flag=1` pixels. Figure 06 is therefore
recorded as **not estimable** and is intentionally not created.

## Density and uncertainty rules

KDEs use SciPy `gaussian_kde` with Scott's bandwidth rule. Direct comparisons
share x and y scales. Each curve is evaluated only over its group's observed
sampled range. The zero-ΔT reference, median, mean, and Q25–Q75 interval are
shown. Groups with fewer than 100 sampled pixels, too few unique values, or
near-constant values receive rugs/annotations instead of a misleading smooth
curve.

Density is normalized within a group; curve height is not pixel count. Counts,
full eligible populations, and image coverage are reported separately. Figure
08 uses a deterministic percentile bootstrap interval for the median, but the
interval is descriptive because ordinary pixel resampling does not fully model
neighbouring-pixel correlation.

## Statistical interpretation

Interpretation prioritizes distribution shape, location shifts, spread,
skewness, overlap, possible multimodality, medians, quartiles, effect sizes,
between-image consistency, and sensitivity to sampling seed. Visual density
differences are not conclusions by themselves. They must be cross-referenced
to the source summary, image coverage, effect sizes, exploratory tests, and
stability results.

P-values are exploratory and use multiple-testing correction where applicable.
They support the distribution analysis; they do not establish causal,
city-wide, or pixel-independent effects.

## Supporting outputs and Excel policy

Boxplots, coverage charts, the image boxplot, earlier stability and bootstrap
charts, spatial maps, QA panels, and native Excel charts remain useful
supporting or appendix outputs. They are not the primary Part E figure family.

Python is the formal spectrum plotting engine. Excel is an optional interactive
delivery layer. Excel COM or native-chart export failure must not block the
canonical Parquet, sampling, spectrum, statistical-analysis, or report stages.
Future batches should not create hundreds of complete per-image workbooks
unless explicitly requested.

## Resumable pipeline

Regenerate or validate only the spectrum stage from completed samples:

```powershell
.\.venv\Scripts\python.exe scripts\part_e\run_part_e_pipeline.py `
    --config config\part_e_delta_t_analysis.json `
    --resume `
    --from-stage spectrum `
    --to-stage spectrum
```

Equivalent shorthand:

```powershell
.\.venv\Scripts\python.exe scripts\part_e\run_part_e_pipeline.py `
    --config config\part_e_delta_t_analysis.json `
    --spectrum-only
```

The driver also supports `--dry-run`, `--image-id`, `--workers`,
`--skip-supporting-figures`, and `--skip-excel`. With `--resume`, completed
upstream artifacts are reused rather than regenerated.

## Retired research history

The superseded cell-level scripts and their generated outputs were removed from
the active tree after the pixel workflow passed validation. Their data source
was cell- or cell-cover aggregated observations, so they are not formal Part E
implementations. They remain recoverable from Git history and the
`pre-e2e-validation-2026-07-15` checkpoint tag.

## Limitations

- The pilot contains only five HKUST thermal images and does not generalize to
  all of Hong Kong.
- TAT3 ambient parameters and the physical plausibility of apparent-temperature
  extremes remain provisional.
- Neighbouring pixels remain spatially correlated after thinning.
- LUHK labels use an approximate north-up footprint model that ignores recorded
  yaw.
- No shadow-present pixels are available, so a shadow effect is not estimable.
