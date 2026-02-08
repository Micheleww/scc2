# Mission（总目标）

## 总目标

**SCC 成为一个全自动的代码生成工厂**：可以自动拆解任务、路由模型、并行调度 CLI、执行/验证、记录证据与文档，并持续迭代。

## 当前父任务（Phase 0）

**SCC × OpenCode 融合**（本地使用，原生感）：

- 统一入口：端口 `18788`
- 保留 OpenCode UI/Server 架构与风格
- 抽取并融入 SCC 独有能力：
  - 任务分配/分解
  - 模型路由
  - CLI 执行器（并行）
  - 文档 / Git 管理
  - MCP 工具链（去重后整合）

## 当前状态入口

- 网关导航：`http://127.0.0.1:18788/nav`
- 队长日志：`http://127.0.0.1:18788/executor/leader`
- 文档索引：`http://127.0.0.1:18788/docs`
- SCC SSOT 主导航（权威）：`C:\scc\scc-top\docs\START_HERE.md`

