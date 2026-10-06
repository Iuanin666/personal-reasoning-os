# Ingest packet

```json
{
  "import_id": "IMP-KNOW-可选稳定重试ID",
  "source_id": "SRC-可选，更新时必需",
  "resolution": "update",
  "input": {"kind": "url | file | text", "value": "URL、绝对文件路径或正文", "name": "文本输入的可选文件名"},
  "knowledge": {
    "knowledge_type": "book | article | paper | case | framework",
    "source_type": "original_book | original_paper | article | case | third_party_summary | AI_summary | personal_reflection",
    "title": "可选；缺省使用提取标题",
    "author": "可选",
    "source_scope": "full | partial | excerpt",
    "derived_from": ["KNOW-... 或 SRC-..."],
    "citation_mode": "page | chapter | section | none",
    "quality": "unassessed | low | medium | high",
    "completeness": "full | partial | excerpt",
    "verified_against_original": false,
    "tags": []
  }
}
```

新建和精确重复不需要 `source_id`。更新必须使用已有稳定 `source_id` 并明确设置 `resolution: update`。重试同一操作应复用 `import_id`。

命令形式由 `runtime.json` 提供：

```text
<python> <cli> --config <config> --defuddle <defuddle> --docling-python <docling_python> plan --input <packet>
<python> <cli> --config <config> --defuddle <defuddle> --docling-python <docling_python> apply --plan <plan> --index-python <index_python> --index-cli <index_cli>
```
