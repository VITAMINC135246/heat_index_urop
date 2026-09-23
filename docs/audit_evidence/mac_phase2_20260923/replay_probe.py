"""Audit-only branch characterization. Synthetic temperatures are never accepted pilot data.
Usage: python replay_probe.py BRANCH_ROOT OUTPUT_DIRECTORY [formal|pilot|spatial]
"""
import json,sys
from pathlib import Path
root=Path(sys.argv[1]); out=Path(sys.argv[2]); mode=sys.argv[3]
sys.path.insert(0,str(root)); out.mkdir(parents=True,exist_ok=True)
if mode=='formal':
 from tests.test_v02_part_e_formal import FormalPartEV02IntegrationTests
 from scripts.workflow.part_e_runner import run_formal_part_e
 manifests=FormalPartEV02IntegrationTests()._write_results(out)
 result=run_formal_part_e(manifests,output_root=out/'formal',resume=False)
 (out/'result.json').write_text(json.dumps(result,default=str,indent=2))
elif mode=='spatial':
 from tests.test_v03_spatial_figures import V03CanonicalSpatialFigureTests
 V03CanonicalSpatialFigureTests()._results(out)
elif mode=='pilot':
 import numpy as np,pandas as pd,shutil
 from scripts.workflow.pilot_adapter import adapt_pilot_image
 import scripts.run_analysis as runner
 fixture=Path('/tmp/heat-index-audit-controlled-pilot')
 image_id='DJI_20260107143259_0005'
 # Setup performed once, before invoking the branch probes.
 runner.PROJECT_ROOT=fixture
 configs=[('legacy',{})]
 if 'temperature_result' in __import__('inspect').signature(adapt_pilot_image).parameters:
  configs.append(('runtime',{'temperature_result':runner.legacy_temperature(image_id)}))
 for name,kwargs in configs:
  manifest,path=adapt_pilot_image(fixture,image_id,output_root=out/name,**kwargs)
  (out/f'{name}-manifest-path.txt').write_text(str(path))
