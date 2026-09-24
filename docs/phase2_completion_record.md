# Phase 2 completion record

Completion date: 2026-09-24 (Asia/Hong_Kong). **Phase 2 is complete and its scientific baseline is frozen on `phase2-Completed`.** The certified scientific acceptance commit is `0a097b28d0cfd17c8907dedfdfbbfe4d3c13f688`. This record is a subsequent documentation and CI-trigger cleanup commit on that branch; use `git rev-parse phase2-Completed` to identify its current frozen tip. No scientific source code changed after the certified acceptance commit. Historical `main` remains at `06c61b499e9c3e2f30daaeddc29fa4e98d61066e` and was not merged or force-updated.

## Final gates

| Gate | Result | Evidence |
|---|---|---|
| Architecture | **PASS** | Responsibility packages and compatibility entry points in [architecture.md](architecture.md) and the migration map. |
| Mac owner acceptance | **PASS** | [Mac record](phase2_mac_acceptance_20260924.md) and the repeated accepted-real test: 1 passed, 0 fixture skip. |
| Windows owner acceptance | **PASS** | [Windows record](phase2_windows_acceptance_20260924.json): portable 123 passed, local integration 6 passed, accepted-real 1 passed, and controlled real DJI extraction. |
| Synthetic scientific regression | **PASS** | Formal Part E test passed on Mac and Windows; the preserved [comparison](phase2_synthetic_regression_result.json) has 97/97 exact outputs. |
| Real thermal regression | **PASS** | Five new Windows 512×640 float32 matrices were byte-identical to the accepted matrices; maximum temperature difference 0.0 °C. |
| TAT3 validation | **PASS** | All 25 available parameter comparisons were exact and accepted matrices matched; no nonexistent manual point/region values were invented. |
| Real downstream regression | **PASS** | Five normal routes exact; accepted six-image aggregate replay reproduced 17 tables/samples and 56 PNGs, including the immutable 21,047-pixel polygon result. |
| Polygon-path owner acceptance | **OWNER-ACCEPTED VIA AGGREGATE** | Route-specific polygon replay was waived by owner acceptance decision because the accepted frozen aggregate regression is considered sufficient for Phase 2 closure. No route-specific replay is claimed. |
| Thermal provenance | **PASS** | Source/tool/report hashes, v1 matrix/sidecar binding, radiometric parameter fingerprint, and tamper rejection were verified. |
| Windows-to-Mac replay | **PASS** | The unchanged new Windows v1 pair was consumed by the Mac Phase 2 adapter; defined downstream metrics matched Windows exactly. See [Mac replay evidence](phase2_cross_machine_mac_acceptance_20260924.json). |
| Hosted CI | **PASS** | [Run 36006285038](https://github.com/VITAMINC135246/heat_index_urop/actions/runs/36006285038) on `phase2-Completed` at the certified acceptance commit created macOS and Windows jobs, and both succeeded. The record-only tip must also receive green branch CI before final task closure. |
| Data-root portability | **PASS** | Mac and Windows resolved the configured data roots; the transferred v1 artifact was installed in the ignored Mac data root without replacing the accepted fixture. |
| Git/data boundary | **PASS** | No raw data, transfer ZIP, local configuration, ignored accepted fixture, or generated large output was committed. |

## Cross-machine result

The transferred archive `phase2_windows_to_mac_cross_machine_20260924.zip` matched SHA-256 `8267448505297939bfc9a7af72a18f71121f76aac4f8da78a8d9872bb0c94a35`; all six internal payload hashes passed. The matrix hash was `814ef8337c79ab6646c7ccc3be6c1fd14b3323079a3c984bcba647d87627b80a`, and the sidecar hash was `f45e95f28f33fa8af66bce6370cc254c2124f0f99760b65c82ea360364a4f57a`. The original Mac source image matched the sidecar's source hash. With the project Python 3.12.5 environment active, the successful replay command was:

```sh
PYTHONPATH="$PWD" python data/local_external/phase2_cross_machine_20260924/run_mac_replay.py
```

Windows and Mac returned the same 327,680 native and eligible rows, four cover counts, ambient 11.0 °C, verified provenance, and mean ΔT `3.280268430709839 °C`. The Windows-to-Mac numeric difference was 0.0 °C. The accepted float64 mean differed by `2.6349443960071994e-7 °C`, within the existing `1e-6 °C` tolerance. A separate Mac comparison to the fixed accepted fixture found all seven arrays and all scientific pixel values exact. Fifty of 51 historical pixel-table columns matched exactly; the sole difference was the v1 Celsius unit token `degC` versus the older descriptive Celsius phrase. The package's defined cross-machine comparison passed without changing any artifact or tolerance.

## Branch freeze and limitations

Before cleanup, remote branches were `main`, `phase-2-safety-net`, `stabilize/phase2-final`, and the newly pushed `phase2-Completed`. The two obsolete tips had zero commits not reachable from `main` or `phase2-Completed`. After a green run on the new permanent branch, the obsolete remote and local stabilization branches were deleted and remote tracking refs pruned. The final remote and local branch names are exactly `main` and `phase2-Completed`. The permanent branch was pushed normally with its upstream; no merge or force-push was performed.

The standalone historical polygon canonical array bundle remains unrecovered. The accepted TAT3 DOCX does not bind an independently verifiable historical standalone application version; the installed Windows executable version was recorded separately. Both are non-blocking historical evidence limitations under the owner's acceptance decision. The accepted ambient value remains a provisional TAT3 exported parameter rather than an independently validated meteorological air temperature.

Future development should start from `phase2-Completed`. Continue literature-driven Shadow research first, create a dedicated Shadow development branch later, implement and validate Shadow independently, then rerun the established Phase 2 regressions before integration. **Shadow has not been implemented in this Phase 2 closure.**
