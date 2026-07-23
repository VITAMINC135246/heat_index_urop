# Part C Automation and Baseline Methods

This document records baseline and future automation options for Part C. These methods are for planning and comparison only. The current pilot outputs are still based on manually reviewed SLIC segments, not on a trained model.

## Current Baseline

The current baseline workflow is:

1. Use the accepted Part B Round 1.1 refined visible ROI.
2. Resize the refined visible ROI to the thermal grid.
3. Run SLIC superpixels on the thermal-grid-resized visible ROI.
4. Generate numbered segment ID maps and class review sheets.
5. Prefill candidate physical surface-cover classes using simple image features and heuristics.
6. Manually review `manual_class` and `shadow_status`.
7. Generate final thermal-grid physical surface-cover masks and separate binary shadow masks.

This baseline is appropriate for the five pilot pairs because it keeps the human reviewer in control and avoids presenting model output as ground truth.

## Features Available For Automation

Future automated classifiers can use features already created by Part C:

- RGB color statistics per segment
- HSV color statistics per segment
- visible ROI texture features
- superpixel shape and size features
- segment location within the thermal grid
- neighboring segment context
- LUHK broad land-use context as weak context, not as a label
- shadow flag as a separate state feature

Thermal temperature values should only be added after Part D has produced validated temperature rasters or pixel tables.

## Practical Baseline Comparisons

The following options can be compared later against the reviewed Part C pilot labels.

### QGIS SCP

QGIS Semi-Automatic Classification Plugin can provide a traditional remote-sensing baseline using manually defined training samples and a classifier such as Random Forest. This is useful as an interpretable non-deep-learning comparison.

Expected use:

- export aligned visible ROI rasters or mosaics
- define training samples from reviewed Part C labels
- train and evaluate a Random Forest or similar classifier
- compare predicted classes against reviewed segment labels and final masks

### QGIS Deepness

QGIS Deepness can run deep-learning segmentation or object-detection models inside QGIS. This may be useful for later visual experiments, but it should not replace reviewed pilot labels unless it is quantitatively validated.

Expected use:

- prepare aligned visible imagery
- run a pretrained or project-trained segmentation model
- convert model predictions to the thermal grid
- compare against reviewed Part C masks

### TorchGeo

TorchGeo is a useful Python ecosystem for geospatial deep learning. It can support dataset construction, tiling, augmentation, and model training once enough reviewed data exists.

Expected use:

- package reviewed visible ROI, surface-cover mask, and shadow mask pairs
- split pilot and later data into train/validation/test groups
- train a segmentation baseline such as U-Net only after sufficient reviewed labels exist
- evaluate per-class IoU, F1, confusion matrix, and spatial error patterns

### Pretrained Land-Cover Models

Pretrained land-cover or semantic-segmentation models can be used as weak baselines or feature generators. They should be treated cautiously because the drone oblique/near-nadir campus imagery, class scheme, season, resolution, and thermal-grid alignment differ from common public datasets.

Expected use:

- run predictions on refined visible ROI images
- map model classes to the project class scheme
- compare with reviewed Part C masks
- record which classes transfer well and which fail

## Evaluation Metrics

Future automation should be compared with reviewed labels using:

- per-class precision, recall, and F1
- per-class IoU
- confusion matrix
- pixel-area-weighted accuracy on the thermal grid
- segment-level accuracy
- performance by campus or image group
- error review overlays for visible ROI and thermal-grid previews

Shadow should be evaluated separately from physical surface cover.

## Recommended Next Automation Step

After more manual labels are reviewed, the safest next automation baseline is a segment-level Random Forest or Gradient Boosting classifier trained on the reviewed segment summary features. This keeps the label unit consistent with the manual review unit and is easier to audit than a full CNN segmentation model.

Deep-learning methods should wait until there are enough reviewed images to support train/validation/test splits without leaking near-duplicate spatial context.

## Current Restriction

No model training is part of the current Part C output. The present final masks are generated from the reviewed annotation workbook:

`data/annotations/part_c/part_c_surface_cover_annotations.xlsx`

## Version 0.1 adapters

The existing reviewed visible ROI, SLIC-assisted annotations, class mappings,
thermal-grid masks, shadow layer, and LUHK context remain the normal-route
source. The additional Part C* route is intentionally not a full-image
classifier: a user selects a physical surface-cover class and accepts a thermal
polygon. Only its interior is labelled known; its exterior is unknown and
ineligible for class-specific analysis. Cancellation produces no successful
canonical result.
