# Retrieval

The disposable index stores file hashes, note metadata, heading-aware chunks, FTS text, and local embeddings. Incremental indexing updates only changed files and removes deleted files.

`optimized_v1` combines keyword and semantic candidates with reciprocal-rank fusion, authority/type intent, note diversity, and one-hop explicit relationship expansion. It reports `supported`, `weak`, or `no_relevant_evidence` while retaining diagnostic candidates.

Layers are `core`, `personal`, `knowledge`, and `source_evidence`. Full source text is available for quotation and page verification but does not compete equally with personal memory in ordinary questions.
