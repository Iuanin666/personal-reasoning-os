---
name: profile-review
description: 用户主动要求重新认识自己、比较 Self View 与 System View、分析个人变化或变化原因时，生成有证据且默认只读的 Profile Review；只有用户逐项明确确认后才提交。
---

# Personal OS Profile Review

读取 `references/runtime.json`，调用固定 release 的 `profile_evolution.py`。本 Skill 不在后台运行，不因新增 Experience 自动修改 Profile。

1. 用户说“重新认识现在的我”“分析这些年的变化”“比较我怎么看自己与你的观察”时，运行 `prepare` 生成只读 dossier。不要扫描 Source Evidence 或整本 Knowledge。
2. 从 dossier 生成符合 [proposal-schema.md](references/proposal-schema.md) 的 proposal。Self View 只能来自用户明确表达、自写材料或 personal reflection；行为不能升级成 Self View。
3. System View 至少需要两条不同证据，优先跨时间、跨场景；必须执行反例搜索并写明适用边界。单一事件只能保留为低置信度候选，不能形成稳定人格结论。
4. 变化原因使用 `explicit_cause`、`supported_hypothesis`、`possible_influence`、`unknown`。没有用户明确因果陈述时不得使用 `explicit_cause`。
5. 先调用 `validate-proposal`，向用户展示 Review proposal：仍成立内容、Self/System View、一致与冲突、支持证据、反例、Evolution、变化原因等级和写入建议。此阶段不得修改 Vault。
6. 只有用户明确说“确认沉淀/更新”或逐项选择后，才以选中的 item ID 调用 `commit --confirm`。模糊认可不构成提交授权。
7. commit 使用 dossier 中读取时 hash 做 CAS；冲突时停止，不覆盖 Obsidian 新内容，并报告 conflict artifact。成功后检查增量索引和 validate。

用户不同意 System View 时保留历史观察，设置 `user_review_status: disagree`；Current Profile 不把它表达为确定事实。Profile 只承载当前 Self View，Model 承载 System View，Profile_History 承载 checkpoint、变化和冲突。

措辞强度遵守 [language-policy.md](references/language-policy.md)。不得输出或保存隐藏推理链。
