# SCC 控制面（sccctl）

目标：把“启动/停止/重启/状态/诊断”收敛成**唯一入口**，避免多实例、端口占用与 UI 误判导致的反复折腾。

## 使用

在仓库根目录或任意目录运行：

- 启动：`tools\scc\sccctl.cmd start`
- 停止：`tools\scc\sccctl.cmd stop`
- 重启：`tools\scc\sccctl.cmd restart`
- 状态：`tools\scc\sccctl.cmd status`
- 诊断：`tools\scc\sccctl.cmd doctor`（输出到 `artifacts\scc_state\reports\doctor_*.md`）
- 一键扫+隔离（默认 dry-run）：`tools\scc\sccctl.cmd sweep`
- 一键扫+隔离（实际执行）：`tools\scc\sccctl.cmd sweep apply`
- 仅做 artifacts 回收（默认 dry-run）：`tools\scc\sccctl.cmd gc`
- 仅做 artifacts 回收（实际执行）：`tools\scc\sccctl.cmd gc apply`
- 看日志：`tools\scc\sccctl.cmd logs`

## 设计约束（大公司做法）

- **单一入口**：UI/快捷方式/后台守护最终都应调用 `sccctl`，不要再直接点多个脚本。
- **单实例**：watchdog/daemon 都用锁端口硬拦截（18789/18790），避免重复拉起。
- **可观测**：`doctor` 产出结构化排障信息，用于复现问题与回溯。
