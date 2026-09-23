"""Regenerate native LUHK from tracked pilot grid and footprint metadata, without thermal extraction."""
from pathlib import Path
import sys,json,numpy as np,pandas as pd
root=Path(sys.argv[1]);sys.path.insert(0,str(root))
from scripts.workflow.luhk_context import load_native_luhk_result
pairs=pd.read_excel(root/'data/metadata/part_b_pilot_pairs.xlsx');out=[]
for row in pairs.itertuples():
 id=str(row.image_id); l=load_native_luhk_result(root,image_id=id,pair_id=str(row.pair_id),shape=(512,640))
 mask=np.load(root/f'outputs/part_c/masks/{id}/{id}_physical_surface_cover_class_id_thermal_grid.npy')
 def counts(a):
  v,c=np.unique(a,return_counts=True);return {str(x):int(y) for x,y in zip(v,c)}
 out.append({'image_id':id,'shape':[512,640],'luhk_status':l.status,'luhk_counts':counts(l.labels),'luhk_known':int(l.known_mask.sum()),'cover_counts':counts(mask),'spatial_uncertainty':l.spatial_uncertainty})
Path(sys.argv[2]).write_text(json.dumps(out,indent=2))
