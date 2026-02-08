# Flow: Doc Update v1

适用：文档/规范/Runbook/接口说明更新。

## 输入

- `goal`：需要补齐/更新的内容点（必须可验收）
- `files`：明确要改的文档路径（尽量单文件）
- `allowedTests`：至少包含“自检/审计证据”命令（可以是 `task_selftest.py`）

## 约束

- 不做“顺手重构/顺手整理全库文档”，只改目标文件。
- 必须留下证据：让审计能回答“你改了哪里？”

## 必须产出（用于审计）

- `SUBMIT.touched_files`：必须包含改动文件路径
- `SUBMIT.tests_run`：至少写明自测/自检命令（即使是 `none` 也要写）
- `EVIDENCE`：列出改动文件路径（以及任何生成的报告路径）

## 最小闭环步骤

1. Designer 给出精确文件 pins（或至少 files 列表）
2. Doc Executor 只改指定文档
3. CI gate 通过（exit code=0）
4. 可回放：`/replay/task?task_id=...` 能看到 touched_files + tests_run

