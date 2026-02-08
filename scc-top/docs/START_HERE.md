# Docs Root Navigation（唯一入口 / SSOT）

本文件路径长期稳定：`docs/START_HERE.md`。

规则：任何人/任何 Agent 进入本仓库，**先读本页**；禁止创建第二个“主入口”来替代本页。

## 如何阅读（AI 拼装上下文）

按固定顺序拼装上下文（从“规则”到“事实”）：

1) 读取分区索引（本页 → SSOT Trunk）
2) 读取相关 leaf docs（规范/合约/作业手册）
   - 机器可读索引：`docs/ssot/registry.json`（alias：`docs/ssot/_registry.json`）
3) 注入外部输入（`docs/INPUTS/`）
4) 只从 `artifacts/`/`evidence/` 取事实与证据（不要把运行证据拷进规范文档）

## SSOT Trunk（7 分区固定结构）

- SCC_TOP（顶层宪法 / governance）：`docs/ssot/02_architecture/SCC_TOP.md`
- Trunk 总索引：`docs/ssot/00_index.md`
- 01 Conventions：`docs/ssot/01_conventions/index.md`
- 02 Architecture：`docs/ssot/02_architecture/index.md`
- 03 Agent Playbook：`docs/ssot/03_agent_playbook/index.md`
- 04 Contracts：`docs/ssot/04_contracts/index.md`
- 05 Runbooks：`docs/ssot/05_runbooks/index.md`
- 06 Inputs：`docs/ssot/06_inputs/index.md`
- 07 Reports & Evidence：`docs/ssot/07_reports_evidence/index.md`

## 本地融合编排（OC × SCC Local Gateway）

用于把 **OpenCode UI/Server** 与 **SCC 的任务分解/模型路由/执行器** 在本机融合成一个入口（默认端口 `18788`）。

- 代码：`tools/oc-scc-local/`
- 本地运行手册（镜像）：`docs/oc-scc-local/NAVIGATION.md`
- 配置入口（HTTP）：`GET /config`、`POST /config/set`（写入 `tools/oc-scc-local/config/runtime.env`，重启 daemon 生效）
- 队长监控：`GET http://127.0.0.1:18788/pools`、`GET http://127.0.0.1:18788/executor/debug/metrics?hours=6`

## Executor JSON Context（降低读文件成本）

执行器只消费 **Pins JSON** + 最小切片，禁止自由读仓：
- 结构规范：`docs/ssot/03_agent_playbook/exec_context/pins.schema.json`
- 示例：`docs/ssot/03_agent_playbook/exec_context/pins.example.json`
- 模块索引（给 Designer/Planner 生成 pins）：`docs/ssot/03_agent_playbook/exec_context/map.example.json`

## DocOps Governance (v0.1.0)
- `docs/ssot/02_architecture/SCC_TOP.md` — SCC 顶层宪法：目标、Top 约束、OID 治理（ULID/Postgres/内嵌/迁移/门禁）
- `docs/ssot/01_conventions/DOCFLOW_SSOT__v0.1.0.md` — 文档流 SSOT：唯一入口、规范/证据分离、主干收敛原则
- `docs/ssot/01_conventions/DOC_REGISTRY__v0.1.0.md` — 文档注册表：机器可读索引入口与上下文拼装顺序
- `docs/ssot/01_conventions/OID_SPEC__v0.1.0.md` — OID 细则：生成器接口、Postgres 权威、内嵌格式、migrate、oid_validator、CI 门禁接入
- `docs/ssot/01_conventions/UNIT_REGISTRY__v0.1.0.md` — Unit 枚举表：primary_unit/tags 的权威允许值
- `docs/ssot/02_architecture/PROJECT_GROUP__v0.1.0.md` — 工作区与项目组：多项目归类（quantsys/yme/math_modeling）与 scope gate 规则
- `docs/ssot/05_runbooks/OID_POSTGRES_SETUP__v0.1.0.md` — OID Postgres 本地启动 + 环境变量注入（DSN 无密码 + PGPASSWORD）

## Agent Manuals（说明书体系 / SSOT）
- RoleSpec：`docs/ssot/03_agent_playbook/ROLE_SPEC__v0.1.0.md`
- SkillSpec：`docs/ssot/03_agent_playbook/SKILL_SPEC__v0.1.0.md`
- WorkspaceSpec：`docs/ssot/03_agent_playbook/WORKSPACE_SPEC__v0.1.0.md`
- Capability Catalog：`docs/ssot/03_agent_playbook/CAPABILITY_CATALOG__v0.1.0.md`
- Dispatch Runbook（组长/组员链路）：`docs/ssot/03_agent_playbook/DISPATCH_RUNBOOK__v0.1.0.md`
- Role Packs（角色包 + 角色记忆引用）：`docs/ssot/03_agent_playbook/roles/index.md`
- Handoff Templates（交接物模板）：`docs/ssot/03_agent_playbook/handoff_templates/index.md`

## Manager Tools（组长验收工具）
- Delegation audit（汇总 CodexCLI 批次改动）：`python tools/scc/ops/delegation_audit.py --automation-run-id <run_id>`
- Leader Board（队长信息板：瀑布流汇总 + 错误码 + token）：`python tools/scc/ops/leader_board.py`
- OID registry bootstrap（把 SSOT canonical 的 inline OID 导入 Postgres；CI 前置）：`powershell -File tools/scc/ops/oid_registry_bootstrap.ps1`
  - PS1 可能被禁用时：`python tools/scc/ops/oid_registry_bootstrap.py --report-dir docs/REPORT/control_plane/artifacts/OID_REGISTRY_BOOTSTRAP_V010`
- Scope gate：批量派发建议用 `configs/scc/*.json` 并为每个 parent 指定 `allowed_globs[]` + `isolate_worktree: true`（越权变更会被拒绝应用）
- Dispatch config from task_tree（从任务树生成安全派发配置）：`python tools/scc/ops/dispatch_from_task_tree.py --taskcode <TaskCode> --limit 5 --area control_plane --emit-report`
- Task ledger sync（task_tree → artifacts/scc_tasks）：`python tools/scc/ops/sync_task_tree_to_scc_tasks.py --only-missing --emit-report --taskcode TASKTREE_SYNC_V010 --area control_plane`
- Task tree backfill（artifacts/scc_tasks → task_tree）：`python tools/scc/ops/backfill_task_tree_from_scc_tasks.py --only-with-verdict --emit-report --taskcode TASKTREE_BACKFILL_V010 --area control_plane`
- Review job wrapper（progress+feedback+metrics + verdict gate）：`python tools/scc/ops/review_job_run.py --taskcode REVIEW_JOB_V010 --area control_plane --run-mvm`
- TaskCode guard（技能调用/三件套门禁）：`powershell -File tools/scc/ops/taskcode_verify.ps1 -TaskCode <TaskCode> -Area <area>`
- OID generator（唯一发号）：`python tools/scc/ops/oid_generator.py new --path <path> --kind md --layer DOCOPS --primary-unit V.OID_VALIDATOR`
- OID mint placeholders（批量替换占位符）：`python tools/scc/ops/oid_mint_placeholders.py --apply`
- OID validator（Postgres 权威校验，fail-closed）：`powershell -File tools/scc/ops/oid_validator.ps1 -ReportDir docs/REPORT/<area>/artifacts/<TaskCode>`
- OID Postgres（本地 18777，OID registry 专用）：`powershell -File tools/scc/ops/pg_oid_18777_start.ps1` / `powershell -File tools/scc/ops/pg_oid_18777_stop.ps1`
- Dispatch watchdog（监控并自动终止卡住的 CLI）：`python tools/scc/ops/dispatch_watchdog.py --base http://127.0.0.1:18788 --poll-s 60 --stuck-after-s 60`
- Deterministic snippet pack（确定性抽取上下文，减少 token）：`python tools/scc/ops/deterministic_snippet_pack.py --allowed-glob <glob> --task-text "<task>" --json`
- SSOT deterministic search（基于 registry.json 选取权威上下文）：`python tools/scc/ops/ssot_search.py --task-text "<task>" --limit 12`
- Dispatch helper（RoleSpec 路由 + 安全 config 生成）：`python tools/scc/ops/dispatch_task.py --goal "<goal>" --parents-file <parents.json> --out-config <config.json>`
- Dispatch wrapper（watchdog + 批量派发一键）：`powershell -File tools/scc/ops/dispatch_with_watchdog.ps1 -Config <config.json> -Model gpt-5.2`
- SCC_TOP validator（Top/SSOT 最小闭环校验）：`powershell -File tools/scc/ops/top_validator.ps1`

备注（Windows 脚本策略可能禁用 ps1）：
- top_validator 纯 Python：`python tools/scc/ops/top_validator.py --registry docs/ssot/registry.json --out-dir artifacts/scc_state/top_validator`
- oid_validator 纯 Python：`python tools/scc/ops/oid_validator.py --report-dir docs/REPORT/<area>/artifacts/<TaskCode>`

## 事实源（不要当入口用）

- `docs/`：只放规范/索引/输入（可读可引用）
- `docs/INPUTS/`：外部输入（网页对话/需求原文/共享记忆）
- `artifacts/`：运行产物与证据（SQLite/jsonl/logs/状态文件）
- `evidence/`：审计证据（append-only）

## Changelog（只记录入口结构变化）

- 2026-02-01：建立 `docs/ssot/` 主干结构；将 Runbook/Observability/Docflow 收敛到 SSOT Trunk。
- 2026-02-01：建立 SCC 顶层宪法 `docs/ssot/02_architecture/SCC_TOP.md` 与 DocOps 治理文档（OID Spec / Unit Registry），并在入口页加入 DocOps Governance 小节。

## Dedup Map (2026-02-04)
- architecture.md -> docs/ssot/02_architecture/architecture.md
- aws_connection_guide.md -> docs/ssot/05_runbooks/aws_connection_guide.md
- core_assets.md -> docs/ssot/01_conventions/core_assets.md
- data_source_of_truth.md -> docs/ssot/01_conventions/data_source_of_truth.md
- entrypoints_checklist.md -> docs/ssot/07_reports_evidence/entrypoints_checklist.md
- execution_engineering_design.md -> docs/ssot/02_architecture/execution_engineering_design.md
- factor_library_ranking.md -> docs/ssot/07_reports_evidence/factor_library_ranking.md
- quantsys_repo_archaeology_report.md -> docs/ssot/07_reports_evidence/quantsys_repo_archaeology_report.md
- replay_consistency.md -> docs/ssot/02_architecture/replay_consistency.md
- taskhub_system_manifest.md -> docs/ssot/02_architecture/taskhub_system_manifest.md
- taskhub_system_overview.md -> docs/ssot/02_architecture/taskhub_system_overview.md
- unified_market_data_downloader_README.md -> docs/ssot/05_runbooks/unified_market_data_downloader_README.md
- ????.md -> docs/ssot/01_conventions/????.md

Archived originals: docs/arch/dedup_20260204/

## Content Dedup (2026-02-04)
- INPUTS/quant_finance/project_navigation.md -> docs/arch/project_navigation__v0.1.0__ACTIVE__20260115.md
- INPUTS/quant_finance/PROJECT_NAVIGATION__legacy.md -> docs/ssot/02_architecture/legacy/PROJECT_NAVIGATION__v0.1.0__20260115.md
- REPORT/control_plane/LEADER_BOARD__LATEST.md -> docs/REPORT/control_plane/LEADER_BOARD__20260202-071930Z.md

- oc-scc-local/MISSION.md -> docs/oc-scc-local/archive/MISSION.md
- oc-scc-local/RUNBOOK.md -> docs/oc-scc-local/archive/RUNBOOK.md

Archived originals: docs/arch/dedup_content_20260204/oc-scc-local/

## Dedup Reports
- docs/REPORT/dedup_report_20260204.md
