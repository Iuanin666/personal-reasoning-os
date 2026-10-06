---
name: analyze
description: 基于 Personal OS 的个人历史、当前状态和外部知识，只读分析用户本人或他人的问题；支持 perspective、analysis、advice、critique、decision，不负责沉淀或修改长期记忆。
---

# Personal OS Analyze

使用 `references/runtime.json` 中固定 release 的 `analyze.py`。本 Skill 默认只读，不调用 `$reflect`、不更新任何 Markdown，也不保存推断。

1. 根据自然语言选择模式：个人思维视角用 `perspective`；梳理问题但不替用户决定用 `analysis`；给建议用 `advice`；主动找盲点/反例用 `critique`；明确选项选择用 `decision`。
2. 明确 `subject`：用户本人为 `self`；朋友、同事、家人为 `other`；一般问题为 `general`。生成 analysis plan 和有界 Context Pack。
3. `context_status: insufficient` 时先说明缺失信息，不编造“用户一直认为”。`subject: other` 时，用户历史只用于表达“按照你的历史视角”，不得成为他人的事实。
4. 输出语义上区分三种声音：
   - **你的历史视角**：只引用 Personal Evidence / 当前 Core，并标注 note ID 与 heading。
   - **外部证据**：保留原始来源、第三方总结、AI 摘要、个人理解的身份。
   - **AI 分析 / 挑战**：明确这是当前推导，不是用户已经表达的观点。
5. 不以“过去选 A”直接推出“现在选 A”。比较过去关注点、Outcome、当前差异、Goals/Constraints 变化、外部支持与反例、信息缺口；decision 模式再给 options、trade-offs、reversibility、downside、recommendation 和 confidence。
6. 只输出简要、可审计 rationale，不输出或持久化隐藏推理链。新观察只能标为 candidate observation。用户之后明确要求沉淀时，才另行使用 `$reflect`。

详细输出契约见 [response-policy.md](references/response-policy.md)。
