from pathlib import Path
import zipfile
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import ListedColormap, BoundaryNorm
import rasterio

#file paths
zip_path = Path("data/2024_Raster_Grids_on_Land_Utilization_GEOTIFF.zip")
extract_dir = Path("data/LUHK2024_extracted")
output_path = Path("outputs/figures/hong_kong_land_use_preliminary_aggregated.png")

# unzip the file
extract_dir.mkdir(parents=True, exist_ok=True)

with zipfile.ZipFile(zip_path, "r") as zf:
    zf.extractall(extract_dir)
    
    
tif_files = list(extract_dir.rglob("*.tif"))
if not tif_files:
    raise FileNotFoundError("No .tif file found after extracting the ZIP file.")
raster_path = tif_files[0]

with rasterio.open(raster_path) as src:
    data = src.read(1)
    bounds = src.bounds
    crs = src.crs
    
print("Raster file:", raster_path)
print("CRS:", crs)
print("Bounds:", bounds)
print("Shape:", data.shape)
print("Unique LUHK codes:", sorted(np.unique(data).tolist()))

""" checked output on 29/05/2026: Raster file: data/LUHK2024_extracted/LUMHK_RasterGrid_2024/BLU.tif
CRS: PROJCS["Hong Kong 1980 Grid System",GEOGCS["Hong Kong 1980",DATUM["Hong_Kong_1980",SPHEROID["International 1924",6378388,297.000000000005,AUTHORITY["EPSG","7022"]],AUTHORITY["EPSG","6611"]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],AUTHORITY["EPSG","4611"]],PROJECTION["Transverse_Mercator"],PARAMETER["latitude_of_origin",22.3121333333333],PARAMETER["central_meridian",114.178555555556],PARAMETER["scale_factor",1],PARAMETER["false_easting",836694.05],PARAMETER["false_northing",819069.8],UNIT["metre",1,AUTHORITY["EPSG","9001"]],AXIS["Easting",EAST],AXIS["Northing",NORTH],AUTHORITY["EPSG","2326"]]
Bounds: BoundingBox(left=800000.0, bottom=800000.0, right=863750.0, top=848000.0)
Shape: (4800, 6375)
Unique LUHK codes: [0, 1, 2, 3, 11, 21, 22, 23, 31, 32, 41, 42, 43, 44, 51, 52, 53, 54, 61, 62, 71, 72, 73, 74, 81, 83, 91, 92]
"""

# Define the catogory, and combine all LUHK codes into 11 catogories;

category_groups = {
    0: "Sea / non-land",
    1: "Residential",
    2: "Commercial",
    3: "Industrial / warehouse",
    4: "GIC / open space",
    5: "Transport",
    6: "Other urban / built-up",
    7: "Agriculture / fishpond",
    8: "Vegetation / wetland",
    9: "Barren / rocky shore",
    10: "Inland water",
}

code_to_group = {
    0: 0,
    1: 1, 2: 1, 3: 1,
    11: 2,
    21: 3, 22: 3, 23: 3,
    31: 4, 32: 4,
    41: 5, 42: 5, 43: 5, 44: 5,
    51: 6, 52: 6, 53: 6, 54: 6,
    61: 7, 62: 7,
    71: 8, 72: 8, 73: 8, 74: 8,
    81: 9, 83: 9,
    91: 10, 92: 10,
}

grouped = np.full(data.shape, -1, dtype=np.int16)
for original_code, group_id in code_to_group.items():
    grouped[data == original_code] = group_id
    

# color preparing
group_ids = sorted(category_groups.keys())

default_colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]
base_cmap = plt.colormaps["tab20"].resampled(len(group_ids))
colors = [base_cmap(i) for i in range(len(group_ids))]

cmap = ListedColormap([colors[i] for i in group_ids])
norm = BoundaryNorm([i - 0.5 for i in group_ids] + [group_ids[-1] + 0.5], cmap.N)

# plot, basiclly
fig, ax = plt.subplots(figsize=(12, 9))

ax.imshow(
    grouped,
    extent=[bounds.left, bounds.right, bounds.bottom, bounds.top],
    origin="upper",
    cmap=cmap,
    norm=norm,
    interpolation="nearest",
)

ax.set_title("Preliminary Land-use Spatial Plot of Hong Kong (LUHK 2024)")
ax.set_xlabel("Easting (Hong Kong 1980 Grid, EPSG:2326)")
ax.set_ylabel("Northing (Hong Kong 1980 Grid, EPSG:2326)")

#create legend
legend_handles = [
    mpatches.Patch(color=colors[group_id], label=category_groups[group_id])
    for group_id in group_ids
]

ax.legend(
    handles=legend_handles,
    title="Aggregated land-use category",
    loc="center left",
    bbox_to_anchor=(1.02, 0.5),
    borderaxespad=0,
)

ax.set_aspect("equal")

fig.tight_layout()

fig.savefig(output_path, dpi=300, bbox_inches="tight")
plt.show()