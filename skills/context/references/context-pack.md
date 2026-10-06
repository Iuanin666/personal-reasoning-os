# Context Pack v0.4.1

Context Pack 是客户端中立的只读 JSON 派生物，不是长期个人事实。

顶层字段：`question`、`task_type`、`subject`、`as_of`、`context_status`、`core_context`、`personal_evidence`、`external_knowledge`、`source_evidence`、`conflicts`、`missing_information`、`provenance_summary`、`budget`、`metrics`。

每条 Evidence 保留 `note_id`、`note_type`、`path`、`heading`、`layer`、`temporal_status`、`effective_date`、`origin`、`provenance`、`perspective`、`evidence_basis`、`user_review_status`、`authority`、`relevance`、`excerpt`、`selection_reasons` 和 `subject_scope`。

Profile 默认是 `perspective: self`；Model 默认是 `perspective: system`。用户明确 disagree 的 System View 仍可作为历史观察返回，但会降低 authority，并带明确状态，客户端不得表述成确定事实。

`origin` 允许：`user_explicit`、`behavior_inferred`、`ai_observation`、`system_record`、`self_authored`、`external_original`、`third_party_summary`、`ai_summary`、`personal_reflection`。

`context_status`：

- `sufficient`：至少一类相关证据达到现有检索器的 supported 口径。
- `partial`：存在候选，但时间、主体或证据强度仍有缺口。
- `insufficient`：没有足以支持个人化断言的相关证据。
