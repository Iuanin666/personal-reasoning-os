from __future__ import annotations
import argparse,json,subprocess
from pathlib import Path

PROBE="""import importlib.metadata as m,json
out=[]
for d in m.distributions():
 name=d.metadata.get('Name')
 if not name: continue
 classifiers=[x.split('::')[-1].strip() for x in d.metadata.get_all('Classifier') or [] if x.startswith('License ::')]
 lic=d.metadata.get('License-Expression') or d.metadata.get('License') or ', '.join(classifiers) or 'NOT DECLARED IN PACKAGE METADATA'
 out.append({'name':name,'version':d.version,'license':' '.join(lic.split())})
print(json.dumps(out))
"""
def inspect(python):
 return json.loads(subprocess.check_output([str(python),'-c',PROBE],text=True))
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--core',required=True);ap.add_argument('--ingest',required=True);ap.add_argument('--output',required=True);a=ap.parse_args()
 combined={}
 for env,exe in [('core',a.core),('ingest',a.ingest)]:
  for item in inspect(exe):
   key=(item['name'].lower(),item['version']);combined.setdefault(key,item|{'environments':[]})['environments'].append(env)
 lines=['# Installed dependency license metadata','','Generated from the clean-install Python package metadata. This inventory complements, and does not replace, the upstream license texts.','', '| Package | Version | Environment | Declared license |','|---|---:|---|---|']
 for item in sorted(combined.values(),key=lambda x:x['name'].lower()):
  license_text=item['license'].replace('|','\\|')[:300]
  lines.append(f"| {item['name']} | {item['version']} | {', '.join(item['environments'])} | {license_text} |")
 Path(a.output).write_text('\n'.join(lines)+'\n',encoding='utf-8')
 print(json.dumps({'packages':len(combined),'output':str(Path(a.output).name)}))
