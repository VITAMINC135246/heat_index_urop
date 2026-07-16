# Part E formal pixel-level ΔT spectrum generation summary

- Status: complete.
- Formal observation: one accepted finite thermal pixel.
- Primary sampling seed: 20260715.
- Sampling method: `spatially_thinned_stratified_pseudorandom`.
- KDE: SciPy `gaussian_kde`, `scott` bandwidth, evaluated only within each group's observed sampled range.
- Shadow comparison: not estimable because no valid `shadow_flag=1` pixels occur.
- Spatial limitation: thinning disperses selected pixels but does not eliminate spatial autocorrelation.

## Written figures

- `outputs/part_e/figures/spectrum/fig00_pixel_delta_t_spectrum_overall.png` and PDF counterpart
- `outputs/part_e/figures/spectrum/fig01_pixel_delta_t_spectrum_by_luhk_facets.png` and PDF counterpart
- `outputs/part_e/figures/spectrum/fig02_pixel_delta_t_spectrum_by_surface_cover_facets.png` and PDF counterpart
- `outputs/part_e/figures/spectrum/fig03_pixel_delta_t_spectrum_within_gic_by_cover_facets.png` and PDF counterpart
- `outputs/part_e/figures/spectrum/fig04_pixel_delta_t_spectrum_within_gic_overlay.png` and PDF counterpart
- `outputs/part_e/figures/spectrum/fig05_pixel_delta_t_spectrum_by_image_facets.png` and PDF counterpart
- `outputs/part_e/figures/spectrum/fig07_pixel_delta_t_sampling_stability.png` and PDF counterpart
- `outputs/part_e/figures/spectrum/fig08_pixel_delta_t_surface_cover_bootstrap_ci.png` and PDF counterpart

Figure 06 was intentionally not created. The not-estimable status is documented in the caption and source-summary files.

## KDE exceptions

- `luhk` / `51 | Other urban / built-up land`: `insufficient_sample` — sampled n < 100.
- `surface_cover_shadow` / `bare_soil | shadow=0`: `not_estimable_as_contrast` — no valid shadow_flag=1 pixels.
- `surface_cover_shadow` / `concrete_pavement | shadow=0`: `not_estimable_as_contrast` — no valid shadow_flag=1 pixels.
- `surface_cover_shadow` / `grass_low_vegetation | shadow=0`: `not_estimable_as_contrast` — no valid shadow_flag=1 pixels.
- `surface_cover_shadow` / `roof | shadow=0`: `not_estimable_as_contrast` — no valid shadow_flag=1 pixels.
- `surface_cover_shadow` / `vegetation_tree | shadow=0`: `not_estimable_as_contrast` — no valid shadow_flag=1 pixels.
