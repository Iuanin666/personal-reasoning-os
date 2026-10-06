# Architecture

Personal OS has four separable layers: canonical Markdown, disposable retrieval, bounded context selection, and client-side reasoning. Memory writes are explicit and safe; analysis is read-only.

`reflect` writes personal history. `ingest` writes compact Knowledge notes and managed sources. Retrieval builds local SQLite/FTS5/embedding caches. Context selects evidence under budgets. Analyze reasons over the Context Pack. Profile Review proposes changes and commits only selected, confirmed items with CAS.

No MCP, cloud vector database, paid API, automatic session loading, or background memory writer is required.
