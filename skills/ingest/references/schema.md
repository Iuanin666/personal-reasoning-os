# Knowledge V0.3.1 来源语义

Knowledge Note ID 表示一条可读知识记录；`source_id` 表示原始材料；`import_id` 表示一次导入操作。三者不得混用。一份 Source 可以派生多条不同来源层的 Knowledge Note。

核心字段：

- `content_origin`: `original`、`third_party_summary`、`ai_summary`、`personal_reflection`。
- `source_id`, `source_format`, `source_hash`, `source_path`：稳定来源身份与 managed source。
- `source_evidence_path`: 完整 extraction 的 managed source 路径。
- `content_storage`: original 来源必须为 `managed_source`；派生文本为 `knowledge_note`。
- `canonical_url`, `retrieved_at`：网页追溯。
- `source_scope`: `full`、`partial`、`excerpt`。
- `derived_from`: 派生内容所依据的 Source 或 Knowledge ID。
- `citation_mode`: `page`、`chapter`、`section`、`none`。
- `extractor`, `extractor_version`：提取工具追溯。
- `source_history`: 来源版本变化；旧版本不覆盖。
- `derived_status.ai_summary`: 来源更新后可以是 `needs_review`。

Original Knowledge Note 不再包含完整 `可核验提取内容`，只保存来源、文档结构和 Source Evidence 引用。第三方总结、`AI 摘要`、`我的理解` 仍是独立派生内容。PDF 页码来自 Docling provenance；EPUB/DOCX 没有可靠页码时使用章节或 section，不能伪造页码。

Managed source 路径：

```text
04_Knowledge/_Sources/<source_id>/versions/<sha256-prefix>/
  原始文件或网页 extracted.md
  metadata.json / citation-index.json（按格式存在）
  source-manifest.yaml
```

`_Sources` 的二进制文件不索引；`extracted.md` 以 `source_evidence` 层建立可删除索引。默认查询不扫描该层，页码/原文意图或显式 `--layer source_evidence` 才进入。网页提取快照和 source manifest 长期保留；SQLite、提取 staging 和 plan cache 可删除。
