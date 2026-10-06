# CLI 输入协议

CLI：`python personal_os.py [--config 路径] <command>`。Python 和 CLI 绝对路径见 runtime.json。命令：index、rebuild、search、core、validate、reflect --input、recover。不要用默认系统 Python 代替配置虚拟环境。

输入 JSON 示例（仅虚构说明，不导入正式库）：

```json
{
  "mode": "current",
  "import_id": "IMP-demo-2026-10-05-career-choice",
  "material": {
    "material_id": "MAT-demo-current-chat",
    "source_type": "current_conversation",
    "source_ref": "当前 Codex 对话中用户明确表达的内容"
  },
  "experience": {
    "event_date": "2026-10-05",
    "title": "在两份工作之间选择",
    "source": "用户在本次对话主动讲述的职业选择",
    "facts": "用户比较两个工作机会，并明确选择 B。",
    "thoughts": "用户表示现在更看重成长空间。",
    "tradeoffs": "收入稳定性与学习机会之间存在取舍。",
    "action": "选择 B。",
    "domains": ["工作"],
    "confidence": 1.0,
    "projects": [],
    "links": []
  },
  "decision": {
    "title": "工作机会选择",
    "question": "选 A 还是 B？",
    "options": ["A：熟悉岗位", "B：新方向"],
    "choice": "B",
    "reason": "用户认为 B 更符合当前成长目标。",
    "confidence": 0.8
  },
  "core_updates": [{
    "target": "profile",
    "key": "career-priority",
    "value": "当前职业选择更重视成长。",
    "provenance": "user_explicit",
    "change": "changed"
  }],
  "models": [{
    "title": "面对不确定性的流程偏好",
    "provenance": "ai_observation",
    "observation": "可能倾向通过明确流程降低不确定性；这是 AI 观察，不是用户自我定义。",
    "confidence": 0.55,
    "status": "observing",
    "evidence": []
  }]
}
```

新 Experience 必填 title/facts。mode 默认 current，也可由 request_text 保守判断自然语言；明确 mode 优先。只有 current 的 event_date 可默认当前上海日期。backfill/update 必填 source，描述原文件/聊天及定位。

时间有三种写法：精确日期用 `event_date: YYYY-MM-DD`；模糊日期用 `event_date: null`、`event_date_precision: approximate`、`event_date_raw: "2025年暑假左右"`；完全未知用 `event_date: null`、`event_date_precision: unknown`，可在 event_date_raw 保留“无日期旧日记”等原话。recorded_at 是首次写入时间，updated_at 是最后修改时间，绝不把二者当作 event_date。兼容字段 date/created_at/source_key 仍会保留。

每个 packet 必须有稳定 `import_id`；同一次失败重试复用它。material 包含 `material_id/source_type/source_ref`，可选 content_hash；content_hash 只校验材料，不参与事件合并。source_type 可用 current_conversation/chat_history/diary/document/project_record/user_recollection/system_record/external_source/other。旧调用的 source_key 暂作为 import_id 别名。

Experience 可选 background/thoughts/tradeoffs/action/outcome/questions/reflection/behavior_inferred/ai_observation/external_source，均为字符串。projects/links/evidence 使用真实已存在 ID（不含 Wikilink 括号）。空章节不输出。

更新 Experience 传 experience.id，可只给需要补充的 facts/reflection 等字段。修正原发生日期时给 experience.date 和 date_correction_reason；旧日期与理由留在正文，ID 不变。仅补充另一日期形成的证据时，把该日期放在本次 import 的 event_date，不改 Experience 本身。新操作用新 import_id；同一事件复用 event_key/Experience ID。Material 相同、hash 相同或语义相似都不会自动合并事件。

update 不自动创建 Experience/Decision/Model，给出的 ID 必须存在。可完全省略 experience，仅更新 decision/core_updates/models；证据可以放 packet.evidence。不新增记忆壳来满足格式。不存在的 ID 或 core key 会在写入前报错。

core target 枚举 profile/goal/constraint/principle。key 使用已存在的稳定键，新键只能是英文小写、数字、下划线或短横线。证据自动加入本次 Experience。value 改变时必须指定 change: refine/changed。

无新 Experience 时复用 packet.evidence 或目标记录作为关联，并在 Markdown reflection_sources 中直接保留来源。backfill 的 core_updates 只写 Profile_History；update 的 `state: historical` 也只写历史。update 的当前状态写入使用 confirmed_on（不填为本次确认日），旧值仍进入 Profile_History。update 不新增 core key；全新长期条目使用 current + 对应独立经历。

更新 Model 传 id，仍提供 title/observation/confidence/status/provenance；旧观察正文保留。更新 Decision 传 `{"id":"DEC-YYYY-NNNN","outcome":"实际结果……","review":"复盘……"}`。关联目标必须已经存在，否则写入前失败。新 Experience/Decision/Model ID 由程序分配，不由 AI 猜测。

相同 import_id 重试返回 duplicate，不再次写入。批量写入前有 Markdown 恢复日志，recover 回滚该批后可重试。若返回 optimistic write conflict，目标笔记没有被覆盖，拟写内容保存在错误给出的 `.personal-os/conflicts/*.json`；先人工合并，再用新的 import_id 重试。

三种模式的可执行输入示例和自然语言路由见 [modes-examples.md](modes-examples.md)。
