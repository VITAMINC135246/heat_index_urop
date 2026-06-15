# Heat Index UROP

Preliminary land-use plotting work for Hong Kong LUHK 2024 data.

## Contents

- `scripts/plot_hong_kong_land_use.py`: extracts the LUHK 2024 GeoTIFF ZIP, groups LUHK codes into broader land-use categories, and generates a spatial plot.
- `data/`: source LUHK CSV and GeoTIFF ZIP data.
- `outputs/`: generated land-use figures.

## Usage

Install the Python dependencies in your environment, then run:

```bash
python scripts/plot_hong_kong_land_use.py
```

## Dataset layout

Raw drone data is stored under `data/raw/HKUST/`. Garden Hill session folders
are directly below the dataset folder, while HKUST session folders are below
`DCIM/`. The V/T inventory script scans recursively, so it handles both layouts
without assuming a fixed directory depth.

## V/T pair inventory

`scripts/01_create_vt_pairs.py` scans JPG/JPEG files whose names end in `_V` or
`_T` and builds pairs in two stages. It first pairs files in the same parent
directory whose complete base names match. Remaining files may pair by their
final sample number, such as `0071`, only within the same parent/session.
Timestamp differences are allowed and recorded. The script never pairs across
sessions, and multiple candidates are marked ambiguous instead of being chosen
arbitrarily. It writes the stable inventory to `data/metadata/vt_pairs.csv`.

Run it from the project root:

```bash
python3 scripts/01_create_vt_pairs.py
```

The output columns are:

- `pair_id`: stable project-relative identifier for the record
- `dataset_folder`: first folder below `data/raw/HKUST/`
- `location`: inferred GardenHill, HKUST, or Unknown location
- `capture_date`: session date when available, otherwise dataset date
- `session_folder`: nearest parent folder beginning with `DJI_`
- `base_name`: exact common base name, or a sample-number label for fallback pairs
- `sample_number`: final numeric sample identifier, with leading zeros preserved
- `v_path`, `t_path`: project-relative POSIX paths
- `status`: paired, missing, or duplicate state
- `match_method`: exact base-name, session sample-number, unmatched, or ambiguous
- `timestamp_difference_seconds`: absolute V/T timestamp difference when parseable
- `pilot`: whether the record matches the explicitly configured unique pilot
- `notes`: duplicate paths or scan metadata that needs attention

Pilot selection is explicit. Set `PILOT_PAIR_ID` near the top of
`scripts/01_create_vt_pairs.py` to one generated project-relative `pair_id`, then
rerun the script. When it is `None`, no record is marked as the pilot; sample
number `0016` alone does not automatically select a pilot.

## Part B classification scheme

Part B keeps broad land use and visible surface cover as separate layers.
Broad land use retains the original LUHK categories, while surface cover is
independently annotated from visible drone imagery. Shadow is stored as a
separate mask rather than a surface-cover class.

LUHK is a broad-brush, 10 m resolution context dataset and must not be treated
as pixel-level surface-cover ground truth for drone imagery. The complete
classification definitions and annotation principles are documented in
`docs/part_b_land_use_surface_cover_scheme.txt`.

## Data-management rule

Treat `data/raw/` as read-only source data. Do not move, rename, overwrite, or
write generated data into the original DJI folders. Raw data is not uploaded to
GitHub. Generated inventories such as `data/metadata/vt_pairs.csv` store only
paths relative to the project root.
