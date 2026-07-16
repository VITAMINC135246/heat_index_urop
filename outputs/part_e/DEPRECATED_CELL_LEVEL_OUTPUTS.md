# Deprecated exploratory Part E cell outputs

The pre-existing `scripts/part_e/01_build_cell_delta_t_dataset.py` through
`06_create_clear_spectrum_figures.py` and the older local outputs they produced
are retained as research history only. They aggregate thermal pixels to LUHK
10 m cells and are not part of the formal Part E pipeline.

The four unnumbered historical PNGs in `outputs/part_e/figures/spectrum/` with
names beginning `luhk_delta_t_`, `surface_cover_delta_t_`, or
`gic_surface_cover_delta_t_` are also deprecated cell/cell-cover figures. The
formal sampled-pixel family uses numbered `fig00_` through `fig08_` names with
PNG and PDF counterparts plus `part_e_spectrum_figure_captions.md`.

The formal default entry point is:

```text
python scripts/part_e/run_part_e_pipeline.py --config config/part_e_delta_t_analysis.json
```

Every formal Part E observation is one original thermal pixel. Spatial sampling
tiles disperse selected pixels but are never averaged and are not statistical
observation units.
