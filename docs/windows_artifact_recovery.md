# Recover accepted Windows artifacts for Phase 2

The Mac checkout contains the tracked pilot parameter and summary tables, reviewed Part C masks, and Phase 1 baseline manifest. It does **not** contain the original thermal matrices, their per-image metadata JSON, raw visible/thermal pairs, TAT3 DOCX exports, or the immutable accepted run directories. The tracked summary is evidence of earlier extraction, not a substitute for those payloads. Recover a small selected set from the original Windows project; do not copy the whole roughly 40 GB dataset.

The accepted scientific reference is [phase_1_baseline_manifest.json](baseline/phase_1_baseline_manifest.json), especially run `run_20260722T055625Z`. It records hashes for selected frozen files. The later shared football-field canonical cache has 21,748 target pixels, while the accepted run has 21,047; preserve the accepted run as the golden source and label any later cache separately. Never generate an “accepted” matrix or expected table with the Phase 2 branch.

## Search and record first

On Windows, in PowerShell, set `$originalRoot` to the **existing** original project folder and `$candidateRoot` to the new stabilization checkout. Search by basename and inspect timestamps, associated manifests, and SHA-256 before copying. For example:

```powershell
$originalRoot = 'E:\path\to\original\heat_index_urop'
$candidateRoot = 'E:\path\to\stabilization\heat_index_urop'
Get-ChildItem -LiteralPath $originalRoot -Recurse -File -Filter '*temperature_celsius.npy' |
  Select-Object FullName, Length, LastWriteTime
Get-ChildItem -LiteralPath $originalRoot -Recurse -File -Filter 'combined_report__*.docx' |
  Select-Object FullName, Length, LastWriteTime
Get-FileHash -Algorithm SHA256 -LiteralPath 'E:\path\to\selected\file'
```

Replace these example locations with actual local paths. Keep a recovery log with source path, destination path, size, SHA-256, source machine, and whether the item matches the accepted run. Inspect local-only branches/commits before assuming a missing file was never created:

```powershell
git -C $originalRoot status --short
git -C $originalRoot branch -avv
git -C $originalRoot log --all --oneline -- data/processed/part_d outputs/runs
```

Do not reset or clean the original project to perform this search. Copy selected files; keep its working tree and Git history intact.

## Priority inventory

| What to find and how to recognize it | Why it matters | Destination in stabilization checkout | Git treatment |
|---|---|---|---|
| TAT3 batch-export DOCX reports, especially `combined_report__2026_07_15_22_43_23.docx` (five-pilot parameter source; accepted SHA-256 `50fa623f…2a86023`) and `combined_report__2026_07_17_18_12_48.docx` (09:11 football source; `7959faef…b4dee9`). The named parser test also looks for `combined_report__2026_07_16_20_19_15.docx` and `combined_report__2026_07_17_01_05_05.docx`. | Establish image-specific distance, emissivity, humidity, ambient and reflected settings, plus report identity. The report parser and full named test need actual reports. | `data/local_external/tat3_reports/raw/<original basename>` or an equivalent ignored local root configured for the test. | Keep report payload local/ignored; track only an approved sanitized manifest/hash. |
| Five `DJI_20260107143259_0005`, `...143320_0007`, `...143328_0008`, `...143344_0009`, `...143401_0011` `*_temperature_celsius.npy` files and matching `*_temperature_metadata.json`. Each matrix is expected to be native 512×640 float32 Celsius. | Existing real numeric tests and a pilot thermal handoff need original values and their provenance. The tracked Part D summary names each path. | `data/processed/part_d/temperature_matrices/<image_id>_temperature_celsius.npy` and `<image_id>_temperature_metadata.json`. | Large matrices local/ignored. Keep metadata coupled to the matrix and record hashes in a compact manifest. |
| `outputs/part_d/summaries/part_d_tat3_parameter_temperature_extraction_summary.csv`, pilot parameter CSV, local Part D SDK config, any source manifests, QA/validation logs, and TAT3-vs-DJI comparison record. Check whether local files differ from tracked copies. | Distinguish actual effective per-image parameters from old local defaults; verify tool identity, QA, and TAT3 agreement. The tracked summary has five rows with 5 m, 50% humidity, 0.95 emissivity and image-specific ambient/reflection values. | Preserve selected original evidence under its documented `outputs/part_d/…` path; keep local SDK paths in ignored `config/part_d_sdk.local.json`. | Reviewed small summaries may be proposed for Git after diff/review; machine paths, binaries, sensitive reports and large payloads stay local. |
| The original raw `_V.JPG` and `_T.JPG` pair for normal image `DJI_20260107143259_0005`, plus the polygon image `DJI_20260202091128_0058`; include the paired visible files, full R-JPEGs, and image identity/hash. | Needed to validate V/T pairing, dimensions, alignment/ROI and a genuine DJI extraction. Previews or crops do not prove the source geometry. | Keep the original relative `data/raw/HKUST/...` tree for selected pairs under the configured data root, or record a stable mapping in the fixture manifest. | Local/ignored raw data. |
| Accepted run directory `outputs/runs/v0_3_user_acceptance/workflow_runs/run_20260722T055625Z/`, including run summary and the selected groups' Part A/B/B0/review decisions; the polygon group includes `part_c_star/polygon_gui_result.json`. | Proves which human reviews, ROI and source context produced the accepted result. | Same `outputs/runs/...` path, copied as an immutable snapshot. | Local/ignored snapshot; track only an approved small redacted fixture subset and manifest. |
| Accepted canonical normal/polygon records under `outputs/runs/v0_3_user_acceptance/canonical/images/<image_id>/`, including manifests, native-grid arrays and `pixels.parquet`. | Allows direct matrix → mask → pixel-table comparison, including categorical labels, ambient and ΔT. | Same run-scoped `outputs/runs/...` hierarchy; preserve names and hashes. | Payloads local/ignored; selected compact fixture only after approval. |
| Accepted Part E `outputs/runs/v0_3_user_acceptance/part_e/schema_0_2/run_20260722T055625Z/`, especially `part_e_schema_0_2_pixels.parquet`, QA stage state, sampling manifest, summaries and selected figures. | Frozen six-image reference (1,966,080 rows); includes the 21,047-pixel accepted polygon scope. This is the real scientific comparison target. | Same run-scoped path. | Local/ignored bulk; small metrics/checksum manifest may be tracked. |
| Explicit temporal runs `run_20260722T053855Z` and `run_20260722T064301Z`, if the temporal acceptance gate is exercised. | Protects the recorded three-capture and “not requested” behaviors. | Same `outputs/runs/v0_3_user_acceptance/part_e/schema_0_2/<run-id>/` path. | Local/ignored except selected manifest. |
| Reviewed Part B correspondence/ROI, Part C annotations and thermal-grid cover/known/target/shadow arrays for the two selected images. | Connects temperature pixels to accepted surfaces. The five tracked pilot cover/shadow masks already exist; verify against the Windows copy and recover any missing polygon route arrays/reviews. | Their existing `data/annotations/`, `outputs/part_c/masks/`, and accepted run paths. | Keep reviewed small source records intentionally; do not replace tracked versions without a comparison. |
| Local-only Git commits/branches, ignored `data/processed` and `outputs/runs` files, old regression fixture folders or archive exports. | An accepted artifact may exist only in the Windows working copy. | Inventory first; copy only files necessary for the selected fixture. | Never rewrite history or bulk-add ignored outputs. |

The old local `config/part_d_sdk.local.json` is a path/tool configuration, **not** the authority for accepted image-specific thermal parameters. TAT3-derived values and their source report are the authority where present. The original report records humidity for SDK reproducibility but marks the exported humidity as unreliable for field-humidity interpretation. Preserve that qualification. No missing parameter should be guessed.

## Package the minimum fixture and verify it

Start with the normal and polygon representatives, their accepted run-scoped records, five small pilot matrices/sidecars for existing tests, and only the TAT3 reports needed for the chosen parsing and extraction checks. Keep the original and copied SHA-256 lists. Compare recorded hashes in [phase_1_baseline_manifest.json](baseline/phase_1_baseline_manifest.json) where available; investigate a mismatch before using the file as a golden reference. A folder with a later timestamp or a matching image ID is not automatically the accepted run.

The optional automated real replay uses ignored `tests/fixtures/accepted_real/manifest.json`, created from the tracked [manifest.template.json](../tests/fixtures/accepted_real/manifest.template.json). For the normal pilot case, copy the *accepted `main`* `manifest.json`, `temperature.npy`, `surface_cover_labels.npy`, `surface_cover_known_mask.npy`, `target_mask.npy`, `luhk_labels.npy`, `luhk_known_mask.npy`, optional `shadow_mask.npy`, and `pixels.parquet` into `tests/fixtures/accepted_real/<image_id>/accepted/`. Set each `accepted_sha256` entry to the hash of that original copied file, and protect the temperature/ambient metadata keys that have genuine accepted values. The input files the adapter reads still belong at their original logical `data/` or `outputs/` paths; the fixture directory holds the frozen expected result. An active but incomplete manifest fails its test; leaving only the template makes the real test skip and leaves certification blocked. The present automated adapter is the normal-pilot route; recovering the polygon and six-image artifacts is still required for separate Windows owner acceptance and full scientific certification.

Copy a **complete** thermal artifact pair (matrix plus metadata) across machines; do not send only an `.npy` file. Copy through an approved local medium or controlled storage, preserving bytes. On both machines, verify its SHA-256 and load it through the repository's thermal artifact reader. Then compare the same downstream pixel table and summary for the selected image. [phase2_owner_acceptance.md](phase2_owner_acceptance.md) gives the Mac, Windows, and cross-machine acceptance procedure.
