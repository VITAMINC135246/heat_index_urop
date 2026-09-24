# Phase 2 Mac owner acceptance — 2026-09-24

## Source and recovered reference

- Candidate branch and starting commit: `stabilize/phase2-final` at `1deee85c581af1572dcc9c655dc433152be2f4a0`.
- Accepted reference: `main`, run `run_20260722T055625Z`, normal-route image `DJI_20260107143259_0005`.
- Transfer package: `phase2_mac_step6_accepted_fixture_20260924.zip`, SHA-256 `08cc1368a8c6abec794b0e7bafa928c412782cc5aa0cc1ebb92281d4baf89be6`.
- The ZIP, 59 internal checksums, and 53 inventoried artifact hashes passed before installation. The installed normal temperature matrix has accepted SHA-256 `814ef8337c79ab6646c7ccc3be6c1fd14b3323079a3c984bcba647d87627b80a`.
- The default configured data root was `<checkout>/data`. The accepted normal fixture, historical Part D matrix and sidecar, raw V/T pair, reviewed masks, TAT3 report, and supporting data were restored without overwriting any differing user files. The two tracked Part D CSVs had identical parsed rows and were kept with Mac line endings.
- The active `tests/fixtures/accepted_real/manifest.json` was populated from the tracked template with hashes of the copied accepted files and the original reviewed Part A/B0/B records. This active manifest and all bulk payloads remain ignored and local.

## Mac Step 6 real regression

From the checkout root, with the existing `.venv` activated:

```sh
MPLBACKEND=Agg MPLCONFIGDIR="$(mktemp -d)" python -m pytest -ra -p no:cacheprovider --basetemp "$(mktemp -d)" tests/test_accepted_real_regression.py
```

- Interpreter: CPython 3.12.5; pytest 9.1.1.
- Final result: **1 passed, 0 failed, 0 skipped**.
- The first run exposed a missing replay input: the standalone pilot adapter did not receive the accepted Part B review record, so its manifest contained `{}` for `part_b`. The generated temperature, masks, and every pixel-table column already matched the accepted reference. The adapter and test now pass the original, hash-checked Part A/B0/B review records through the replay. No accepted output or tolerance was changed.
- Actual comparison: one native 512×640 float32 temperature grid, 327,680 unique pixel coordinates, ambient 11.0 °C, and eligible mean ΔT 3.2802686942042785 °C. The replay checked every accepted pixel-table column, all accepted masks, the accepted manifest provenance fields, and the three reviewed records.
- Existing bounds: temperature matrix and pixel-level numeric fields use absolute `2e-6 °C` with zero relative tolerance; grouped mean ΔT uses absolute `1e-6 °C` with zero relative tolerance. Categorical fields, counts, masks, image identity, review records, and accepted file hashes require exact agreement.

## Other Mac checks

- `python -m pip check`: no broken requirements; Tk 8.6 available.
- Data-root default and temporary override resolved correctly; the override left `config/...` under the checkout.
- Responsibility-package imports and both documented CLI `--help` commands succeeded.
- Portable suite: **124 passed, 1 skipped, 6 deselected**. The sole skip was the documented Windows Tcl bootstrap.
- Formal Part E test: **1 passed**. The recorded synthetic cross-branch comparison remains 97/97 exact outputs in `phase2_synthetic_regression_result.json`.
- The recovered historical matrix and sidecar loaded through `load_legacy_temperature` with 512×640 float32 data, ambient 11.0 °C, and the accepted matrix hash. The legacy sidecar predates the versioned `thermal-artifact-v1` binding, so that newer reader correctly rejects it. The Windows-produced v1 artifact and cross-machine replay remain Windows acceptance tasks.

**Mac normal-route owner acceptance: PASS.** This result does not certify the accepted Part C* polygon route or the full six-image pipeline. Full scientific certification remains blocked pending the controlled Windows DJI/TAT3 extraction, Windows fixture replay, and cross-machine comparison in `phase2_owner_acceptance.md`.
