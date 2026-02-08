# Flow: Feature Patch v1

适用：小功能/小修复，目标是“改动小、验证最小、快速合并”。

## 输入

- `goal`：一句话目标 + 明确验收标准（DoD）
- `files`：预计触碰的文件列表（尽量 1-3 个）
- `allowedTests`：允许运行的最小测试命令（必须有；从现在开始所有新任务都走 CI gate）

## 约束

- Executor 只读 pins/切片范围；不扫仓库。
- 成功即结束，不自动扩展范围；失败就 fail，让上游决定是否升级/拆分。

## 原子任务输出格式（Executor）

- `REPORT:` 一句话结果
- `SELFTEST.LOG:` 运行了哪些命令（或 `none`）
- `EVIDENCE:` 证据路径（文件、日志、截图路径等）
- `SUBMIT:` JSON（必须含 `touched_files` 与 `tests_run`）

## 最小闭环步骤

1. Designer 生成 pins + assumptions + allowedTests
2. Executor patch-only 完成改动
3. CI gate（exit code=0）通过才算 done
4. 审计/回放：至少能从日志看出“改了哪里、测了什么、证据在哪”

