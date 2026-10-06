# Profile Evolution Proposal v0.6

顶层字段：`schema_version`、`review_id`、`review_date`、`question`、`self_view`、`system_view`、`alignments`、`tensions`、`evolution`、`change_attribution`、`profile_updates`。

- `self_view[]`：`id`、`statement`、`source_kind`、`evidence`、`confidence`。source_kind 仅允许 user_explicit/self_authored/personal_reflection。
- `system_view[]`：`id`、`title`、`statement`、`perspective: system`、`evidence_basis: inferred`、`evidence`、`counter_evidence`、`counter_search_summary`、`scope`、`confidence`、`status`、`user_review_status`，可选 `model_id`。
- `tensions[]`：`id`、`self_view_id`、`system_view_id`、`interpretation`、`status`。
- `evolution[]`：`id`、`from_checkpoint`、`to`、`change_type`、`evidence`。change_type 为 new/strengthened/weakened/reframed/stable/contradicted/retired。
- `change_attribution[]`：`id`、`change_id`、`level`、`explanation`、`evidence`、`counter_evidence`；explicit_cause 还必须有 `explicit_statement`。
- `profile_updates[]`：`id`、`self_view_id`、`action`、`key`、`value`、`evidence`。只能由 Self View 驱动。

Proposal 是待用户确认的派生物，不是事实源。提交后，checkpoint 和被确认条目进入 Markdown。
