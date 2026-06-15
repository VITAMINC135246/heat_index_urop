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
`_T`, groups them by parent directory and base name, and marks paired, missing,
or duplicate images. It writes the stable inventory to
`data/metadata/vt_pairs.csv`.

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
- `base_name`: common filename after removing the `_V` or `_T` suffix
- `v_path`, `t_path`: project-relative POSIX paths
- `status`: paired, missing, or duplicate state
- `pilot`: whether the base name ends in `_0016`
- `notes`: duplicate paths or scan metadata that needs attention

## Data-management rule

Treat `data/raw/` as read-only source data. Do not move, rename, overwrite, or
write generated data into the original DJI folders. Raw data is not uploaded to
GitHub. Generated inventories such as `data/metadata/vt_pairs.csv` store only
paths relative to the project root.
