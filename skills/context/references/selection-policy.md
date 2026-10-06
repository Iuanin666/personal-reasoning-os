# Selection policy

- Core：按问题检索 Profile、Goals、Constraints、Principles，不整文件加载。
- Personal：Experience、Decision、Outcome、Model、Project 与个人历史；每个 note 最多两个 chunk。
- Knowledge：书籍、论文、文章、案例、第三方总结和个人理解。
- Source Evidence：默认关闭；原文/页码核验或 Knowledge 不足时按需进入。
- 历史任务排除当前 Profile/Goals/Constraints，优先当时 Decision、Experience 和明确关系。
- `as_of` 排除边界后的已知日期证据；日期未知会明确标记，不伪造时间。
- `subject: other` 保留用户历史作为 perspective，不把他人描述写成用户事实。
- 普通问题优先当前 Profile 和相关 Model；只有变化、过去与现在、变化原因等 evolution intent 才定向加入 Profile_History。

默认字符预算：core 3200、personal 6200、knowledge 3000、source evidence 1800、总计 12000；估算 token 总预算 7000。预算、每 note chunk 上限与每 bucket 条数均硬限制。

参考实现：robabby/claude-skills 的 current-state → topic recall 顺序；kkonstvol-lab/obsidian-memory 的 L0/L1/L2/L3 有界上下文、证据优先、golden/holdout Gate 和 advisory-only 约束。未复制 SessionStart、PreCompact、MCP、私有 agent memory 或其 taxonomy。
