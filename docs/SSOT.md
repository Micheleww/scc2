# SSOT (L0 原文层)

此文档是 Designer 的唯一 L0 原文层，用于生成 `SSOT_AXIOMS_JSON`。

维护规范：
- 只允许 Designer 阅读
- Executor 禁止直接读取
- 每次修改必须同步更新 `docs/AI_CONTEXT.md` 中的 `SSOT_AXIOMS_JSON`

当前原则（示例）：
- Executor never reads SSOT directly
- All tasks must use pins-first constraints
