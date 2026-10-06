# Public synthetic evaluation

The public evaluation set demonstrates schemas, categories, evidence labels, hard negatives, and dev/holdout separation using only fictional Lin Chen records. It does not contain scores or answer keys from a private Personal OS.

`dev.jsonl` is safe for iteration. `holdout.queries.jsonl` is safe to run during a formal evaluation; `holdout.answers.jsonl` should be opened only by the formal evaluator.

Run the dev set after creating and indexing the demo vault:

```powershell
./.venv/Scripts/python.exe evaluation/evaluate_retrieval.py
```

Use `--formal-holdout` only for a frozen formal evaluation. The runner reports required-evidence Recall@5/10, reciprocal rank of the first required note, hard-negative cleanliness in Top-5, `no_relevant_evidence` classification accuracy, and median query latency. These metrics evaluate retrieval and evidence-status behavior; they do not claim to measure final answer quality.

The public cases were authored from synthetic notes by reading their content and recording stable note IDs. They demonstrate Golden Set methodology without disclosing the private 18-case internal baseline or its answers.
