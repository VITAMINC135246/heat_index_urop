# Version 0.3 polygon GUI and soccer-field workflow

## What the historical conversation establishes

Accessible text from the conversation titled exactly
`UROP进度更新与会议改期` establishes:

- the full-day dataset is **2026-02-02**, not June 2;
- the primary target is the HKUST soccer field, approximately 09:00–17:00;
- the professor described an ad-hoc soccer-field ΔT that peaked at up to about
  +26°C around noon, despite winter conditions;
- the professor referred to the field as natural turf, which still requires a
  visible-evidence verification record;
- 7 or 9 January may be a later winter validation date; no summer HKUST data
  was available in the described files.

The accessible text does **not** uniquely define whether +26°C is a point,
region, polygon mean, median, percentile, q99, or maximum. It also does not
preserve the email screenshots, exact ambient source/definition, or TAT3
parameters. Version 0.3 therefore calculates all declared descriptive
statistics and records these unknowns; it does not guess or hard-code 26°C.

## Per-capture Part C* workflow

For every real capture:

1. select the real visible and thermal files and inspect Part A pairing/time
   warnings;
2. inspect Part B0 evidence and explicitly reject unusable correspondence;
3. enter Part C* only with valid thermal input;
4. draw most of the soccer-field turf on that capture, excluding running track,
   buildings, stands, trees, people, equipment, and obvious unrelated areas;
5. set `target_id=hkust-soccer-field-natural-turf`, target display name, the
   controlled cover, LUHK category/provenance, confidence, and notes;
6. inspect the overlay and accept. Draft/cancelled annotations cannot create a
   successful canonical result;
7. repeat for every capture. Do not copy coordinates unless a validated
   registration/transfer record is supplied.

The template `config/acceptance/v0_3_soccer_polygon_template.json` is a draft
with no coordinates and cannot be a scientific success by itself.

## Real temperature and ambient input

Use a compatible temperature matrix produced with real per-image DJI/TAT3
parameters, or an explicitly audited real NPY matrix. Record the temperature
source and definition. Ambient JSON must contain the actual value, source,
air-temperature definition, source record, and timezone. Never reuse the v0.2
synthetic soccer matrix or route-test ambient for the scientific result.

## Result inspection

Inspect canonical extreme Min/Max/q99 outputs, each capture's spatial target
boundary and eligibility mask, `temporal_capture_summary.csv`, and the temporal
figures. Compare the professor's ad-hoc +26°C only after confirming which
reported statistic and ambient definition match his original procedure.

Completion means the real workflow is reproducible and its definition is
auditable. It does not mean this repository has already reproduced +26°C.
