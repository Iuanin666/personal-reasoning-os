# Contributing

Open an issue with a minimal synthetic reproduction before a large change. Pull requests should include focused tests and preserve backward compatibility for existing Markdown.

Schema changes must document migration behavior, provenance impact, and whether older clients continue to read the data. Retrieval changes require a baseline, dev-only tuning, and a held-out evaluation.

Never attach a real Personal Vault, Knowledge source, index, log, screenshot, or personal evaluation fixture to an issue or pull request. Use `examples/demo-vault` or create new fictional data.
