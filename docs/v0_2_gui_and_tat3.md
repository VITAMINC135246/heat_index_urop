# Version 0.2 GUI and temporary TAT3 instructions

## Superpixel review GUI

Run the persistent workflow with `--launch-part-c-gui` after supplying final
accepted Part B evidence. The GUI uses the preserved reviewed visible ROI and
SLIC segments.

Manual smoke-test checklist:

1. Confirm the visible ROI, superpixel boundaries, thermal panel, class colors,
   legend, and visibly unreviewed regions.
2. Click one segment, then Ctrl-click additional segments; assign a physical
   cover and confirm every selected segment changes.
3. Mark a region unknown/unclear and confirm it remains ineligible.
4. Toggle shadow on selected regions and confirm cover does not change.
5. Exercise undo, redo, and clear selected labels.
6. Add notes, reviewer identity, and confidence; save a draft, close, resume,
   and confirm state is identical.
7. Attempt acceptance with an unreviewed segment and confirm validation blocks
   it. Finish review and accept; verify the auditable JSON and native-grid masks.
8. In a separate draft, cancel and confirm no successful canonical result is
   created.

Prefill values are suggestions, not reviewed labels. The GUI never silently
labels an unreviewed region.

## Temporary TAT3 point/region analysis

Example:

```powershell
.\.venv\Scripts\python.exe scripts\run_tat3_manual_analysis.py `
  --report C:\path\measurement_report.docx `
  --thermal-image C:\path\DJI_20260202091128_0058_T.JPG `
  --target-name "HKUST soccer field" `
  --luhk "GIC / open space" `
  --luhk-provenance user_supplied_luhk `
  --surface-cover grass_low_vegetation `
  --screenshot C:\path\annotated_screenshot.png
```

The parser distinguishes ambient/parameter-only reports from point and region
measurements, validates image identity and Celsius units, rejects duplicate IDs,
and preserves report parameters, source/screenshot hashes, target, LUHK, cover,
ambient, and notes. Point coordinates and region geometry are used only when
the report supplies them. Otherwise the value plot and analysis report state
that spatial location is unavailable; no coordinate is invented.

The bundle contains a temporary manifest, Parquet measurements, extreme summary
and coordinate tables, PNG/PDF plot when measurements exist, and an
interpretation note. Region min/max/mean are summaries of one region and
clicked points in one image are within-image spatial observations. No temporal
or generalizable significance test is run from one capture.

Default output is ignored under `outputs/runs/<run>/temporary_tat3/` and has
`persistence_scope = temporary_session`. It is not written to
`data/processed/images`, the persistent index, or the main Part E warehouse.
`--output-dir` exports a temporary bundle only; v0.2 has no implicit promotion.
