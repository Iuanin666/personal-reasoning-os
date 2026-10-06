# Third-party notices

Personal OS original code is MIT licensed. Third-party software keeps its own license.

| Project | Pinned/audited version | Classification | License | Copied code |
|---|---:|---|---|---|
| [kepano/defuddle](https://github.com/kepano/defuddle) | 0.19.4 | Direct CLI dependency for web extraction | MIT | No |
| [docling-project/docling](https://github.com/docling-project/docling) | 2.133.0 | Direct Python dependency for document extraction | MIT | No |
| [kepano/obsidian-skills](https://github.com/kepano/obsidian-skills) | audited commit `3ccff533` | Design/format reference | MIT | No |
| [robabby/claude-skills](https://github.com/robabby/claude-skills) | audited repository main | Design reference for reflect/recall/hydrate/glean | MIT | No |
| [kkonstvol-lab/obsidian-memory](https://github.com/kkonstvol-lab/obsidian-memory) | audited repository main | Design reference for bounded context and qualification gates | MIT | No |
| [dengrish/obsidian-skills](https://github.com/dengrish/obsidian-skills) | audited repository main | Design reference only | No repository-level license confirmed during audit | No |
| [paraphrase-multilingual-MiniLM-L12-v2](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2) | revision recorded at setup | Downloaded local model | Apache-2.0 | No redistribution |

Direct runtime packages include NumPy (BSD/0BSD/MIT/Zlib/CC0 components), PyYAML (MIT), ONNX Runtime (MIT), Hugging Face Hub (Apache-2.0), and Tokenizers (Apache-2.0). Exact transitive versions are recorded in the lock files. The local embedding model is Apache-2.0 and is downloaded during setup; this repository does not redistribute its weights.

The clean-install package metadata inventories are published in [DEPENDENCY_LICENSES.md](DEPENDENCY_LICENSES.md) and [NODE_DEPENDENCY_LICENSES.md](NODE_DEPENDENCY_LICENSES.md). Package metadata is an audit aid; upstream license files remain authoritative.

No code or prose from the unlicensed `dengrish/obsidian-skills` repository is included.
