"""Explicit setup only: download public model files, never upload vault content."""
from pathlib import Path
import hashlib
import json
import os
os.environ['HF_HUB_DISABLE_XET'] = '1'
from huggingface_hub import HfApi, hf_hub_download

ROOT = Path(__file__).resolve().parent.parent
REPO = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
FILES = ['onnx/model_quint8_avx2.onnx', 'tokenizer.json', 'tokenizer_config.json', 'config.json', 'README.md']
if __name__ == '__main__':
    dest = ROOT / 'models' / 'multilingual-minilm'
    revision = HfApi().model_info(REPO).sha
    manifest = {'repo': REPO, 'revision': revision, 'files': {}}
    for name in FILES:
        path = Path(hf_hub_download(REPO, name, revision=revision, local_dir=dest))
        manifest['files'][name] = {'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        print(name, path.stat().st_size, flush=True)
    (dest / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print('Local model ready:', dest)
