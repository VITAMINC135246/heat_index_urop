"""Compare audit replay outputs, keeping path differences visible; no tolerance relaxation."""
from pathlib import Path
import numpy as np,pandas as pd,json,sys
from PIL import Image
r=Path('/tmp/heat-index-audit-probes');a=r/'main-formal';b=r/'phase2-formal';res={'comparisons':[]}
for p in sorted(a.rglob('*')):
 if not p.is_file():continue
 rel=p.relative_to(a);q=b/rel
 if not q.is_file():continue
 entry={'path':str(rel)}
 if p.suffix=='.npy':
  x,y=np.load(p),np.load(q);entry.update(kind='array',shape=list(x.shape),exact_equal=bool(np.array_equal(x,y,equal_nan=True) if np.issubdtype(x.dtype,np.number) else np.array_equal(x,y)))
 elif p.suffix in ('.csv','.parquet'):
  try:
   x=pd.read_csv(p) if p.suffix=='.csv' else pd.read_parquet(p);y=pd.read_csv(q) if q.suffix=='.csv' else pd.read_parquet(q)
  except pd.errors.EmptyDataError:
   entry.update(kind='empty_table',exact_equal=p.read_bytes()==q.read_bytes());res['comparisons'].append(entry);continue
  changed=[c for c in x if c not in y or not x[c].equals(y[c])]; entry.update(kind='table',rows=len(x),columns=len(x.columns),exact_equal=x.equals(y),changed_columns=changed)
  if changed:entry['difference_examples']={c:{'main':x[c].astype(str).head(1).tolist(),'phase2':y[c].astype(str).head(1).tolist()} for c in changed if c in y}
 elif p.suffix=='.png':
  with Image.open(p) as x,Image.open(q) as y:entry.update(kind='figure',size=list(x.size),exact_equal=bool(np.array_equal(np.asarray(x),np.asarray(y))))
 else:continue
 res['comparisons'].append(entry)
res['counts']={k:sum(x['kind']==k for x in res['comparisons']) for k in ('array','table','empty_table','figure')}
res['nonidentical']=[x for x in res['comparisons'] if not x['exact_equal']]
Path('/tmp/heat-index-audit-evidence/synthetic-formal-comparison.json').write_text(json.dumps(res,indent=2))
print(json.dumps({k:v for k,v in res.items() if k!='comparisons'},indent=2))
