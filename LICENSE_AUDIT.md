# License audit

Audit date: 2026-10-07.

## Conclusion

MIT is suitable for Personal OS original code. Direct runtime dependencies are used as separate packages or CLIs under permissive licenses. No audited third-party source code or prose was copied into this repository. The project with unclear repository-level licensing, `dengrish/obsidian-skills`, remains a design reference only.

## Classification

- **Direct dependencies:** Defuddle 0.19.4 (MIT), Docling 2.133.0 (MIT), NumPy 2.5.3 (BSD-3-Clause plus bundled permissive components), PyYAML 6.0.3 (MIT), ONNX Runtime 1.30.0 (MIT), Tokenizers 0.23.2 (Apache-2.0), Hugging Face Hub 1.33.0 (Apache-2.0), and the MiniLM model (Apache-2.0).
- **Design references only:** kepano/obsidian-skills (MIT), robabby/claude-skills (MIT), kkonstvol-lab/obsidian-memory (MIT), and dengrish/obsidian-skills (license not confirmed).
- **Directly reused or modified third-party code:** none identified.

The exact Python and Node dependency graphs are locked in repository files. Their packages retain their own copyright and license notices. Because model weights are downloaded rather than redistributed, no model binary is part of the public release artifact.
