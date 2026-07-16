# Formal Part E pixel-level ΔT spectrum figure captions

Spectrum means the statistical distribution/density spectrum of pixel-level ΔT; it is not an electromagnetic or multispectral spectrum.

## Figure 00 — Overall pixel-level ΔT density spectrum

Accepted finite pixels from all five pilot images are represented by the image-stratified sampled-pixel dataset (sampled n=12,500; full eligible n=1,638,400; 5/5 images). The curve uses SciPy Gaussian KDE with Scott's bandwidth rule and is evaluated only across the observed sampled range. One observation is one accepted finite thermal pixel with ΔT = temperature − image-level ambient temperature. Pixels were selected with spatially_thinned_stratified_pseudorandom (primary seed 20260715); original pixel ΔT values were retained. Density is normalized within each group and does not encode pixel count. Spatial thinning improves dispersion but does not remove spatial autocorrelation, so pixels are not described as independent.

## Figure 01 — Pixel-level ΔT spectrum by LUHK class

Eligibility requires an accepted finite pixel and a valid approximate LUHK label. 31 | GIC / open space: 10,000/1,523,465 pixels, 5/5 images; 51 | Other urban / built-up land: 4/200 pixels, 1/1 images; 71 | Woodland / shrubland / grassland / wetland: 1,346/76,074 pixels, 4/4 images; 72 | Woodland / shrubland / grassland / wetland: 613/31,408 pixels, 1/1 images; 73 | Woodland / shrubland / grassland / wetland: 150/7,253 pixels, 2/2 images. Groups below 100 sampled pixels are shown without a smoothed KDE. Directly compared facets share x and y scales; KDEs use Scott's rule and stop at each group's observed range. One observation is one accepted finite thermal pixel with ΔT = temperature − image-level ambient temperature. Pixels were selected with spatially_thinned_stratified_pseudorandom (primary seed 20260715); original pixel ΔT values were retained. Density is normalized within each group and does not encode pixel count. Spatial thinning improves dispersion but does not remove spatial autocorrelation, so pixels are not described as independent.

## Figure 02 — Pixel-level ΔT spectrum by physical surface cover

Eligibility requires an accepted finite pixel and a reviewed valid physical-cover label. Bare soil: 221/10,222 pixels, 2/2 images; Concrete pavement: 6,677/322,856 pixels, 5/5 images; Grass / low vegetation: 770/39,392 pixels, 5/5 images; Roof: 9,406/569,601 pixels, 5/5 images; Vegetation / tree canopy: 10,000/696,329 pixels, 5/5 images. Facets share comparison scales; KDEs use Scott's rule and stop at observed group ranges. One observation is one accepted finite thermal pixel with ΔT = temperature − image-level ambient temperature. Pixels were selected with spatially_thinned_stratified_pseudorandom (primary seed 20260715); original pixel ΔT values were retained. Density is normalized within each group and does not encode pixel count. Spatial thinning improves dispersion but does not remove spatial autocorrelation, so pixels are not described as independent.

## Figure 03 — Within-GIC pixel-level ΔT spectrum by physical surface cover

Eligibility additionally requires LUHK code 31 (GIC / open space). Bare soil: 221/10,222 pixels, 2/2 images; Concrete pavement: 6,673/322,791 pixels, 5/5 images; Grass / low vegetation: 770/39,392 pixels, 5/5 images; Roof: 9,398/569,132 pixels, 5/5 images; Vegetation / tree canopy: 10,000/581,928 pixels, 5/5 images. Facets share comparison scales; KDEs use Scott's rule and stop at observed group ranges. One observation is one accepted finite thermal pixel with ΔT = temperature − image-level ambient temperature. Pixels were selected with spatially_thinned_stratified_pseudorandom (primary seed 20260715); original pixel ΔT values were retained. Density is normalized within each group and does not encode pixel count. Spatial thinning improves dispersion but does not remove spatial autocorrelation, so pixels are not described as independent.

## Figure 04 — Within-GIC surface-cover ΔT spectrum overlay

The overlay includes groups with at least 100 sampled pixels, at least 2 contributing images, and adequate variation for KDE: Bare soil, Concrete pavement, Grass / low vegetation, Roof, Vegetation / tree canopy. Colored baseline ticks mark medians; Scott-rule KDEs are normalized per group and stop at observed ranges. One observation is one accepted finite thermal pixel with ΔT = temperature − image-level ambient temperature. Pixels were selected with spatially_thinned_stratified_pseudorandom (primary seed 20260715); original pixel ΔT values were retained. Density is normalized within each group and does not encode pixel count. Spatial thinning improves dispersion but does not remove spatial autocorrelation, so pixels are not described as independent.

## Figure 05 — Pixel-level ΔT spectrum by pilot image

Eligibility is any accepted finite pixel in the five-image pilot. DJI 2026-01-07 143259_0005: 2,500/327,680 pixels, 1/1 images; DJI 2026-01-07 143320_0007: 2,500/327,680 pixels, 1/1 images; DJI 2026-01-07 143328_0008: 2,500/327,680 pixels, 1/1 images; DJI 2026-01-07 143344_0009: 2,500/327,680 pixels, 1/1 images; DJI 2026-01-07 143401_0011: 2,500/327,680 pixels, 1/1 images. Facets use a common comparison scale and Scott-rule KDEs evaluated only over observed image ranges. One observation is one accepted finite thermal pixel with ΔT = temperature − image-level ambient temperature. Pixels were selected with spatially_thinned_stratified_pseudorandom (primary seed 20260715); original pixel ΔT values were retained. Density is normalized within each group and does not encode pixel count. Spatial thinning improves dispersion but does not remove spatial autocorrelation, so pixels are not described as independent.

## Figure 06 — Surface-cover × shadow spectrum

Status: **not estimable**. Reason: **no valid shadow_flag=1 pixels**. All five reviewed shadow masks contain only shadow_flag=0, so no empty or synthetic comparison figure was created.

## Figure 07 — Sampling-stability distribution

Boxes summarize surface-cover sampled medians across the primary seed and 20 secondary seeds; diamonds mark seed 20260715. Each seed selects dispersed original pixels with spatially_thinned_stratified_pseudorandom; no tile or pixel mean is substituted. Spatial autocorrelation remains, and the display describes seed sensitivity rather than inferential uncertainty.

## Figure 08 — Bootstrap uncertainty summary

Points show sampled-pixel median ΔT and percentile 95% bootstrap intervals from 1,000 deterministic resamples. Eligibility is the same as Figure 02; counts are Bare soil: 221/10,222 pixels, 2/2 images; Concrete pavement: 6,677/322,856 pixels, 5/5 images; Grass / low vegetation: 770/39,392 pixels, 5/5 images; Roof: 9,406/569,601 pixels, 5/5 images; Vegetation / tree canopy: 10,000/696,329 pixels, 5/5 images. Intervals are descriptive because ordinary pixel resampling does not account fully for neighbouring-pixel spatial correlation. One observation is one accepted finite thermal pixel with ΔT = temperature − image-level ambient temperature. Pixels were selected with spatially_thinned_stratified_pseudorandom (primary seed 20260715); original pixel ΔT values were retained. Density is normalized within each group and does not encode pixel count. Spatial thinning improves dispersion but does not remove spatial autocorrelation, so pixels are not described as independent.
