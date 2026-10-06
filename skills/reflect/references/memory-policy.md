# 保存策略

事实与推断分开：facts/thoughts 只能来自用户明确表达；behavior_inferred 是行为推导；ai_observation 是 AI 观察；external_source 须说明资料来源。单次推断不提升为 Profile。Model 默认 observing，可因新证据更新、降低 confidence、refuted 或 obsolete。

Profile 是当前快照。先搜索再决定 key。表达同义时保留原 value，仅增加 evidence；合理细化指定 refine；观点明确转变指定 changed。旧值进入 Profile_History，旧 Experience / Decision 不删除。真实冲突不得静默覆盖。

历史材料的发生日期与导入时间严格分开。backfill 的 Profile 内容只追加历史，不改变当前快照，即便当时的表述很确定。update 中 `state: historical` 同样只进入历史。确认当前状态时用独立 update；`confirmed_on` 表示确认当前状态的日期，不是旧材料日期。

补充按已有 ID 定位；没有 ID 时先搜索、读候选，确认同一事件再传 id 或复用 event_key。不要仅靠标题相似、source hash 或向量相似自动合并。Event ID 是事件，Material ID 是来源材料，Import ID 是一次幂等写入操作。同一材料可包含多个事件；同一事件也可由多份材料补充。同一事件的新材料使用新 import_id/material_id 和原 event_key/id。只有实质独立事件才创建 Experience。

所有修改在 `source_materials`、`reflection_imports`（并保留兼容字段 reflection_sources）中记录来源、事件时间和导入时间；这些信息在 Markdown 中，不依赖数据库。精确时间用 event_date；模糊时间保留 event_date_raw；完全未知用 null + unknown。recorded_at 只表示首次写入，绝不代替事件时间。

Decision 的 choice 必须是已经做出的明确选择。用户只是讨论方案时不要伪造选择。对已有 Decision 的 Outcome 通过 decision.id/outcome/review 追加，并以本次 Experience 为依据。

配置和数据库都是技术资料；真正记忆必须在 Markdown。索引只返回候选证据，不能把高相似度当作事实确认。敏感内容允许保存，但只读取完成本次任务所需的少量片段。
