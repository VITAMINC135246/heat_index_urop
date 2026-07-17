# Version 0.3 benchmark notes

The pre-change v0.2 automated baseline was `48 passed in 45.65s` on the local
Windows `.venv`. v0.3 adds eight PNG/PDF spatial products per eligible canonical
unit and three PNG/PDF temporal products per run, so plotting dominates small
synthetic integrations.

Spatial memory scales with one native image/source unit at a time plus the
loaded canonical frame. Temporal computation reduces rows to capture summaries
before cross-time statistics; it does not construct a pixel × time matrix.

Formal resume avoids sampling, statistics, spectrum, and spatial regeneration
when the canonical hash, generated config, implementation dependency signature,
and every listed output remain valid. Spatial and temporal resume also check
their method hashes; temporal checks timezone configuration.

Measured local v0.3 evidence on 2026-07-18:

- Complete suite: `60 passed in 102.07s`.
- Explicit five-pilot numeric regression: `6 passed in 2.03s`.
- Persistent non-scientific benchmark root:
  `outputs/runs/benchmark_v0_3_20260717T180758Z/`.
- 5,120 canonical rows; one normal plus three polygon images.
- Canonical spatial generation: 21.01 s for four units and 64 PNG/PDF files.
- Temporal generation: 1.61 s; validated resume cache hit: 0.012 s.
- Benchmark output size before the formal integration: 6,779,714 bytes.
- Normal-plus-polygon formal Part E completed sampling, statistics/effects,
  eight spectrum PNG/PDF pairs, four spatial units, and temporal QA under
  `formal_part_e/`; the final dependency-invalidated invocation took 38.2 s.
- Formal resume skipped sample/analyse/spectrum/spatial and returned temporal
  cache hit. The subsequent resume plus formal QA command took 4.8 s; formal QA
  passed.
- Real local TAT3 ambient-only parsing wrote
  `outputs/runs/v0_3_tat3_ambient_only/`: image 0058, 2026-02-02 09:11:28,
  ambient/reflected 10.8°C, distance 5 m, emissivity 0.95, reported humidity
  50%, zero manual measurements, and no persistent-index mutation.

These timings are observations, not service-level guarantees. Real DJI SDK
throughput is environment-dependent and remains an optional local integration.
No SDK binary or local SDK configuration is committed.
