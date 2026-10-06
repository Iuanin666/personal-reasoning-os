from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parent.parent
excluded={'.git','.venv','.venv-ingest','node_modules','models','work','__pycache__'}
files={}
for p in sorted(ROOT.rglob('*')):
 if p.is_file() and not any(x in excluded for x in p.relative_to(ROOT).parts) and p.name!='PUBLIC_RELEASE_MANIFEST.json':
  files[p.relative_to(ROOT).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
out={'public_version':'0.1.0','file_count':len(files),'files':files}
(ROOT/'PUBLIC_RELEASE_MANIFEST.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'file_count':len(files)},indent=2))
