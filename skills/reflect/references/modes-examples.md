# 模式示例（均为虚构材料）

## current

用户：“今天我完成了面试，沉淀本次对话。” → 默认 current。用户没有要求保存时不执行。

```json
{"import_id":"IMP-chat-today-interview","material":{"material_id":"MAT-chat-today","source_type":"current_conversation","source_ref":"当前对话"},"experience":{"title":"一次面试","facts":"用户今天参加了一次面试。"}}
```

## backfill：同一历史事件

用户：“这是 2020 年的旧日记，把这段也沉淀进去。” → 搜索发现 EXP-2020-0001 是同一事件，补原记录。

```json
{"mode":"backfill","import_id":"IMP-diary-page8-event1-v1","event_key":"career-choice-2020","source":"用户提供的旧日记，第8页","event_date":"2020-02-03","material":{"material_id":"MAT-diary-page8","source_type":"diary","source_ref":"旧日记第8页"},"experience":{"id":"EXP-2020-0001","facts":"当时还考虑了通勤距离。"}}
```

以后同事件的第9页使用新 import_id/material_id、同 event_key；experience.id 也可直接沿用。不再创建第二条 Experience。未找到同事件时，去掉 id、提供 title/facts，独立事件才新建。完全不知时间使用 `event_date_precision: "unknown"`；只知道“2025年暑假左右”使用 approximate + event_date_raw，不补造 1 月 1 日。同一页若含两个事件，使用同一个 material_id、两个不同 import_id/Experience。

## update：给旧 Decision 补证据

用户：“补充之前 DEC-2020-0001，旧聊天里还有一个原因。” → update；仅改 Decision。

```json
{"mode":"update","import_id":"IMP-decision-old-evidence-1","source":"用户提供的2019年旧聊天，第8段","event_date":"2019-12-20","material":{"material_id":"MAT-old-chat-8","source_type":"chat_history","source_ref":"旧聊天第8段"},"decision":{"id":"DEC-2020-0001","reason":"家人当时需要用户留在本地。","review":"补充原决策依据，不是今天做了新选择。"}}
```

原 Decision 的 date、created_at、选择和理由保留；新理由以补充/修正段落追加，并记录本次 imported_at。不创建 Experience。

## update：当前 Profile 修正

用户：“之前更看重成长，现在更重视自主性，修正那条偏好。” → 检索确认原 key 后 update。

```json
{"mode":"update","import_id":"IMP-current-preference-correction","source":"用户本次明确确认当前偏好","material":{"material_id":"MAT-current-confirmation","source_type":"current_conversation","source_ref":"当前对话"},"core_updates":[{"key":"career-priority","value":"当前更重视自主性。","provenance":"user_explicit","change":"changed"}]}
```

旧值进入 Profile_History。若用户仅说“旧日记里当时更重视稳定”，使用 backfill，或 update 条目指定 `state: historical`，不改变当前 Profile。

## update：修正已有 Experience 或 Model

Experience 传已有 id 和补充字段；日期有误时需 date_correction_reason。Model 传已有 id、observation、confidence、status；旧观察保留。旧材料只是观察证据，不自动把当年的观察状态当成当前定论。

模式优先由 Skill 结合上下文判断并写进 JSON；CLI 也提供保守关键词 fallback，但不会用相似度擅自决定事件身份。它负责校验目标、避免重复写入、保留时间和修改轨迹。
