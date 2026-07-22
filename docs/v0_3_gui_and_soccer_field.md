# Version 0.3.2 GUI and football-field workflow

## Ordinary-user start

Start the program from the repository root:

```powershell
.\.venv\Scripts\python.exe scripts\run_user_workflow.py
```

Choose football field for one capture, five pilots plus football field for the
mixed-source acceptance run, one V/T group for a normal Part C GUI review, or a
dataset directory when several real repeated captures must be processed. The
launcher collects paths, target fields, confidence, and review decisions in the
terminal; an ordinary user does not author workflow/review/ambient JSON.

## What the historical conversation establishes

Accessible text from the conversation titled exactly
`UROP进度更新与会议改期` establishes:

- the campaign date is **2026-02-02**, not June 2;
- the primary target is the HKUST soccer field, sampled approximately
  09:00–17:00; this is a daytime observation window, not a complete daily cycle;
- the professor described an ad-hoc soccer-field ΔT that peaked at up to about
  +26°C around noon, despite winter conditions;
- the professor referred to the field as natural turf, which still requires a
  visible-evidence verification record;
- 7 or 9 January may be a later winter validation date; no summer HKUST data
  was available in the described files.

The accessible text does **not** uniquely define whether +26°C is a point,
region, polygon mean, median, percentile, q99, or maximum. It also does not
preserve the email screenshots, exact ambient source/definition, or TAT3
parameters. Version 0.3.2 therefore calculates all declared descriptive
statistics and records these unknowns; it does not guess or hard-code 26°C.

## Per-capture Part C* workflow

For every real capture:

1. select the real visible and thermal files and inspect Part A pairing/time
   warnings;
2. inspect Part B0 evidence and explicitly reject unusable correspondence;
3. enter Part C* only with valid thermal input;
4. when revising an accepted result, answer Yes to the redraw prompt so Part C*
   reopens without deleting caches by hand;
5. draw most of the soccer-field turf on that capture, excluding running track,
   buildings, stands, trees, people, equipment, and obvious unrelated areas;
6. confirm the stable `target_id=hkust-soccer-field-natural-turf`, target
   display name, controlled cover, target-scoped LUHK context/provenance,
   confidence, and notes in the interactive prompts;
7. inspect the overlay and accept. Draft/cancelled annotations cannot create a
   successful canonical result;
8. repeat for every capture. Do not copy coordinates unless a validated
   registration/transfer record is supplied.

For the real 2026-02-02 series, the repository contains candidate football-
field captures around 09:11, 14:08, and 17:04. They show strongly overlapping
field footprints, but only a separately accepted polygon on each image can
establish a comparable target ROI. The 09:11 polygon coordinates must not be
copied to the later images.

## LUHK versus surface cover

In normal Part C, LUHK is official read-only 10 m context looked up from the
repository raster. It is displayed as a separate panel and cannot be changed by
Assign, unknown, shadow, or surface-cover controls.

In Part C*, the entered football-field LUHK category is target-scoped user
context unless a defensible official lookup is recorded. Only polygon-interior
pixels receive that accepted context. Polygon-exterior surface cover and LUHK
remain unknown, and those pixels do not enter formal target statistics.

## Real temperature and ambient input

Use the real per-image TAT3 DOCX selected in the launcher so the shared DJI SDK
route can produce a compatible native temperature matrix. The result must
record the temperature source/definition and the report's actual ambient value,
source, definition, source record, and timezone. Never reuse a synthetic soccer
matrix or route-test ambient for a scientific result.

The currently inspected local TAT3 reports for the 09:11, 14:08, and 17:04
captures use 5 m distance, emissivity 0.95, and reported humidity 50%, with
ambient/reflected parameters 10.8°C, 11.8°C, and 15.8°C respectively. These are
per-image TAT3 extraction parameters, not independently validated
meteorological air-temperature observations. Their definitions and source
records therefore remain part of every ΔT compatibility check.

## Result inspection

Inspect canonical extreme Min/Max/q99 outputs, each capture's spatial target
boundary and eligibility mask, and `USER_RESULTS.md`. If an explicit repeated-
capture group was confirmed, inspect that group's `temporal_summary.md`,
`tables/per_capture_statistics.csv`, temperature/ΔT peak-to-trough tables, and
sampling-coverage table. Compare the professor's ad-hoc +26°C only after
confirming which reported statistic and ambient definition match his original
procedure.

Completion means the real workflow is reproducible and its definition is
auditable. It does not mean this repository has already reproduced +26°C.
