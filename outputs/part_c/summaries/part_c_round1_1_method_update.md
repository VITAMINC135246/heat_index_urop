# Part C Round 1.1 Method Update

Part C uses a semi-automatic, manually reviewed workflow.

Primary method:

1. Use the accepted refined visible ROI from Part B.
2. Generate candidate regions using SLIC superpixels on the refined ROI resized to the thermal grid.
3. Manually review and label each segment.
4. Convert reviewed labels into thermal-grid-aligned physical surface-cover masks.
5. Treat shadow as a separate binary `shadow_flag`, not as physical surface cover.
6. Combine physical surface-cover labels with LUHK broad land-use context.
7. Preserve uncertainty with confidence, review_status, notes, no_data_unreviewed, and unclear_ignore.

No temperature extraction, delta T calculation, or supervised model training is part of this step.

Baseline and automation methods are planning/comparison options only and are documented in `docs/part_c_automation_and_baseline_methods.md`.
