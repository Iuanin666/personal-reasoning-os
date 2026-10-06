from __future__ import annotations
import hashlib,json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'src'))
import personal_os as pos
def main():
 errors=[]
 forbidden={'.sqlite3','.db','.onnx','.pdf','.epub','.docx','.pptx','.log'}
 private_config_names={'.private-patterns.json','private-patterns.json','private-denylist.json','publisher-private-patterns.json','local-private-patterns.json'}
 ignored={'.git','.venv','.venv-ingest','node_modules','models','work','.setup-tmp','.test-tmp','__pycache__'}
 for p in ROOT.rglob('*'):
  if not p.is_file() or any(x in p.parts for x in ignored):continue
  if p.suffix.lower() in forbidden:errors.append('forbidden_artifact:'+p.relative_to(ROOT).as_posix())
  if p.name.lower() in private_config_names:errors.append('forbidden_private_config:'+p.relative_to(ROOT).as_posix())
 demo=ROOT/'examples/demo-vault/PersonalOS';notes=[]
 for p in demo.rglob('*.md'):
  if p.name=='SYNTHETIC_DATA.md':continue
  try:meta,body=pos.parse(p.read_text(encoding='utf-8-sig'));pos.check_note(meta,body);notes.append(meta.get('id'))
  except Exception as e:errors.append(f'invalid_note:{p.relative_to(ROOT)}:{e}')
 required={'SYS-Profile','SYS-Current_Goals','SYS-Constraints','SYS-Principles','SYS-Profile_History','EXP-2030-0001','DEC-2030-0001','PROJ-SKYLINE-SEED-LAB','KNOW-2030-0001','MOD-2030-0001'}
 errors += ['missing_demo_id:'+x for x in sorted(required-set(notes))]
 result={'passed':not errors,'errors':errors,'demo_notes':len(notes)};print(json.dumps(result,indent=2));return 0 if not errors else 1
if __name__=='__main__':raise SystemExit(main())
