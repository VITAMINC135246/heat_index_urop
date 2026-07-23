# Version 0.3.2 workflow

## Ordinary-user entry point

From the repository root, start the program with:

```powershell
.\.venv\Scripts\python.exe scripts\run_user_workflow.py
```

This is the supported ordinary-user entry point. The launcher asks what to
explore, accepts paths and review decisions interactively, and then opens the
newest run folder. An ordinary user does not need to author JSON, choose a
configuration file, or assemble the lower-level `run_analysis.py` arguments.

The first menu offers:

1. five accepted pilot images;
2. the football field;
3. five pilots plus the football field;
4. one visible/thermal group;
5. every discoverable group in a dataset directory.

The default output is the isolated acceptance workspace. The first result to
read is `USER_RESULTS.md` in the run folder; it links the canonical images,
spectrum figures, spatial figures, statistical tables, QA, and any explicitly
requested temporal group.

## Persistent route

1. Part A validates the V/T inputs, identities, timestamps, spatial metadata,
   native dimensions, and temperature-grid compatibility.
2. Part B0 presents match, mismatch, or needs-review evidence. It never accepts
   alignment automatically. When evidence is ambiguous, the workflow pauses
   for the user's decision.
3. Full Part B requires an explicit accepted correspondence with full thermal
   support before the normal route can continue. Rejected or unusable visible
   correspondence may continue to Part C* only when the thermal input is valid.
4. Normal Part C displays the real visible image with superpixel boundaries,
   a live colour overlay, the corresponding thermal image, and read-only LUHK
   context when available. A successful result requires a completed accepted
   review; Save, closing the window, or Cancel does not create success.
5. Part C* displays the real thermal image and requires a separately drawn and
   accepted target polygon for that capture. The polygon exterior remains
   target false, cover/LUHK unknown, and analysis-ineligible.
6. Part D uses a compatible real temperature matrix from the shared DJI
   SDK/TAT3 route or an explicitly audited existing matrix. It validates native
   shape, extraction parameters, temperature definition, ambient definition,
   and QA before Part E.
7. Canonical output retains the full native grid and explicit target, known,
   eligibility, source, provenance, temperature, ambient, and QA fields.
8. Part E creates target-eligible statistics, spectrum figures, spatial maps,
   and a readable result summary. It does not silently pool incompatible
   source, measurement, target, or provenance strata.
9. Temporal analysis is offered after accepted/cached captures are known. It is
   an explicit optional branch and defaults to No.

## LUHK and surface cover are different layers

LUHK 2024 is official, read-only 10 m land-use context. The normal workflow
looks it up from the repository's official raster and records its provenance;
the user does not paint or overwrite LUHK in the Part C GUI. An unavailable
lookup remains explicitly unavailable or unknown.

Surface cover is the finer physical material reviewed from the visible image,
such as grass, roof, road, or tree vegetation. A surface-cover assignment never
changes LUHK, and a LUHK class never substitutes for surface-cover review.

For Part C*, a user-supplied LUHK value is target-scoped context and must remain
labelled `user_supplied_luhk`; it must not be presented as an official raster
lookup. Only pixels inside the accepted polygon are known for the target. The
polygon exterior remains unknown even though its thermal temperatures are
retained in the canonical source grid.

## Formal Part E population

A pixel enters formal overall, per-image, LUHK, cover, and spectrum statistics
only when all four conditions are true:

```text
pixel_accepted AND finite(delta_t_c) AND analysis_eligible AND target_mask
```

This leaves the five normal pilot images unchanged because their accepted
target is the full thermal grid. For a football-field polygon, only its accepted
interior enters formal target statistics. The exterior may be retained for
audit and spatial display, but it is not a second background comparison group.

## Temporal is opt-in, never inferred

Press Enter at the temporal question to accept the default No. Part E single-
capture statistics, spectra, spatial maps, and extremes still complete; the
temporal branch records a clean not-requested status and creates no trend.

If the answer is Yes, the user must explicitly:

- select at least two captures for one physical location or target;
- supply stable `location_id`, `target_id`, and `temporal_group_id` values;
- confirm that the selected captures show the same physical location;
- confirm that every capture uses an accepted, comparable ROI;
- review any GPS or recorded-identity conflict and provide a reason before an
  override can be accepted;
- decide whether to create another independent temporal group.

A capture cannot belong to two groups in one plan. Timestamp proximity,
directory membership, filename similarity, target display name, or nearby GPS
coordinates never creates a temporal group automatically.

Target-level temporal ranges do not require pixel registration, but they do
require comparable accepted ROIs. Pixelwise range/change maps are stricter:
they remain unavailable unless the user confirms reliable registration and
records both a registration method and stable registration ID.

## Cache and version identity

The v0.3.2 processing version is `heat-index-urop-0.3.2`; canonical schema
remains `0.2.0`. Cache identity includes source hashes, review decisions,
official LUHK dependencies, target/polygon state, temperature and ambient
definitions, capture time, configuration, implementation signatures, and
artifact hashes. A relevant change invalidates the affected downstream cache.

Temporal cache identity additionally includes the explicit group definition,
same-location/ROI confirmations, conflict overrides, registration declaration,
timezone, canonical hash, and expected group output files. A prior automatic or
directory-wide temporal result is not reused as evidence for a new explicit
group.
