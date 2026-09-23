"""Prepare ONLY an audit-owned synthetic fixture directory; never point at a research checkout."""
from pathlib import Path
import shutil,sys,pandas as pd,numpy as np
r=Path(sys.argv[1]); f=Path('/tmp/heat-index-audit-controlled-pilot')
files=['data/metadata/part_b_pilot_pairs.xlsx','data/metadata/dji_image_metadata.xlsx','data/annotations/part_c/surface_cover_class_mapping.xlsx','data/processed/grids/pilot_luhk_aligned_10m_grid_cells.xlsx','data/processed/footprints/image_footprints.xlsx','outputs/part_d/summaries/part_d_tat3_parameter_temperature_extraction_summary.csv','outputs/part_c/summaries/part_c_final_mask_manifest.xlsx']
for name in files:
 dest=f/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(r/name,dest)
id='DJI_20260107143259_0005'; masks=pd.read_excel(f/files[-1]);row=masks.loc[masks.image_id.eq(id)].iloc[0]
for col in ('class_mask_thermal_grid_npy_path','shadow_mask_thermal_grid_npy_path'):
 name=str(row[col]);dest=f/name;dest.parent.mkdir(parents=True,exist_ok=True);np.save(dest,np.load(r/name)[:16,:20])
summary=pd.read_csv(f/files[-2]);name=summary.loc[summary.image_id.eq(id),'npy_path'].iloc[0];dest=f/name;dest.parent.mkdir(parents=True,exist_ok=True)
np.save(dest,np.linspace(-10,40,320,dtype=np.float32).reshape(16,20))
(f/'SYNTHETIC_ONLY.txt').write_text('Controlled adapter probe: cropped masks and SYNTHETIC temperatures, never real pilot regression evidence.')
