# Version 0.2 stage benchmark

Run:

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_v0_2.py
```

The benchmark writes its detailed JSON and synthetic payload under ignored
`outputs/runs/`. The 2026-07-17 representative Windows/Python 3.12 run used one
160 × 120 synthetic image and measured:

| Stage | Seconds | Python traced peak MiB |
|---|---:|---:|
| Part A metadata validation | 0.019 | 0.016 |
| Part B0 structural triage | 1.004 | 5.166 |
| Full Part B end-to-end candidates, GCP path, and review | 2.984 | 1.501 |
| Standalone preserved review-package generation | 0.070 | 0.906 |
| Part C SLIC/review preparation | 0.456 | 6.384 |
| Part D mocked native SDK extraction | 0.039 | 1.087 |
| Canonical NPY/Parquet/manifest write | 0.855 | 17.233 |
| Formal Part E sampling, statistics, KDE, and plots | 17.102 | 31.407 |

Measured canonical storage was 7,846,996 bytes (7.483 MiB) for this image. The
storage retention limit is a separate quantity:

`Y = floor(0.8 × free_storage_bytes / measured_canonical_bytes_per_image)`

The measured machine had a provisional storage-based `Y = 8,688`. This is not
a request size or a proven production retention capacity.

Operational request guidance is separate. Interactive work is recommended at
`X = 1` group because each review boundary needs attention. Unattended,
pre-reviewed work has provisional `X = 25`; this is scheduling guidance, not a
validated safety limit. Do not substitute either X for Y.

Limitations: synthetic correspondence is easier than field imagery; the Part D
path used the real command/result implementation with a fake SDK runner, so real
DJI executable latency is unmeasured; `tracemalloc` may undercount native
NumPy/OpenCV memory; interactive review time is user-dependent and explicitly
excluded; and pilot-sized measurements do not establish production capacity.
