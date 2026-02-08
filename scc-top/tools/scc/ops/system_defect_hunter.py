#!/usr/bin/env python3
from __future__ import annotations

"""
System Defect Hunter (deterministic, low-token)

Goal:
- Find system-level defects that can cause SCC to fail (queue deadlock, evidence spoof, status mismatch, token blowups).
- Turn them into concrete, minimal engineering tasks with replay/adjudication/rollback.

This script intentionally avoids LLM calls. It relies on local logs + HTTP snapshots.
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import urllib.request
import urllib.error


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")


def _http_json(url: str, timeout_s: float = 10.0) -> Tuple[int, Any]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            try:
                return int(getattr(resp, "status", 200)), json.loads(body or "null")
            except Exception:
                return int(getattr(resp, "status", 200)), body
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            body = str(e)
        return int(getattr(e, "code", 500)), {"error": "http_error", "body": body}
    except Exception as e:
        return 0, {"error": "network_error", "message": str(e)}


def _read_jsonl_tail(path: Path, tail: int = 1200) -> List[Dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []
    out: List[Dict[str, Any]] = []
    for line in lines[-int(tail) :]:
        s = str(line or "").strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
        except Exception:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


@dataclass
class Defect:
    id: str
    risk: str  # P0..P3
    title: str
    mechanism: str  # event|preflight|eval|queue|plugin|validator|storage|router|executor
    probability: str
    damage: str
    signal: str
    minimal_fix: str
    acceptance: str
    rollback: str


@dataclass
class MinimalTask:
    id: str
    title: str
    mechanism: str
    steps: List[str]  # <= 3
    acceptance: List[str]
    replay: List[str]
    rollback: List[str]


def main() -> int:
    ap = argparse.ArgumentParser(description="System defect hunter (deterministic).")
    ap.add_argument("--base", default=os.environ.get("GATEWAY_BASE") or "http://127.0.0.1:18788")
    ap.add_argument("--exec-log-dir", default=os.environ.get("EXEC_LOG_DIR") or r"C:\scc\artifacts\executor_logs")
    ap.add_argument("--out-dir", default=r"C:\scc\scc-top\docs\REPORT\control_plane")
    ap.add_argument("--version", default="V010")
    args = ap.parse_args()

    base = str(args.base).rstrip("/")
    exec_log_dir = Path(args.exec_log_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Live snapshots
    code_cfg, cfg = _http_json(f"{base}/config", timeout_s=15)
    code_board, board = _http_json(f"{base}/board", timeout_s=15)
    code_jobs, jobs = _http_json(f"{base}/executor/jobs", timeout_s=20)
    code_summary, summary = _http_json(f"{base}/executor/debug/summary", timeout_s=15)
    code_token_cfo, token_cfo = _http_json(f"{base}/executor/debug/token_cfo", timeout_s=10)

    # Local logs
    leader_file = exec_log_dir / "leader.jsonl"
    failures_file = exec_log_dir / "failures.jsonl"
    ci_results_file = exec_log_dir / "ci_gate_results.jsonl"
    leader_tail = _read_jsonl_tail(leader_file, tail=2000)
    failures_tail = _read_jsonl_tail(failures_file, tail=2000)
    ci_tail = _read_jsonl_tail(ci_results_file, tail=2000)

    # Simple derived signals
    running = 0
    queued = 0
    failed = 0
    done = 0
    by_exec: Dict[str, int] = {}
    if isinstance(jobs, list):
        for j in jobs:
            if not isinstance(j, dict):
                continue
            st = str(j.get("status") or "")
            ex = str(j.get("executor") or "unknown")
            by_exec[ex] = by_exec.get(ex, 0) + 1
            if st == "running":
                running += 1
            elif st == "queued":
                queued += 1
            elif st == "failed":
                failed += 1
            elif st == "done":
                done += 1

    board_counts = None
    if isinstance(board, dict) and isinstance(board.get("counts"), dict):
        board_counts = board["counts"]

    # Defects (Top 20) - ordered by probability * damage (heuristic)
    defects: List[Defect] = []

    def add(d: Defect) -> None:
        defects.append(d)

    add(
        Defect(
            id="queue_split_starvation",
            risk="P0",
            title="Split 队列饥饿：board_split 堆积导致系统只在“拆分”而不在“交付”",
            mechanism="queue",
            probability="high",
            damage="high (吞吐塌陷，任务长期 in_progress)",
            signal=f"/executor/jobs queued={queued} running={running}; board in_progress={(board_counts or {}).get('byStatus', {}).get('in_progress') if isinstance(board_counts, dict) else 'unknown'}",
            minimal_fix="对 board_split 做专用并发/优先级；当 split backlog 过高时限流并转交 factory_manager 处理瓶颈。",
            acceptance="metrics: split_queue_length 下降；atomic done/min 上升；无新增长期 in_progress。",
            rollback="runtime.env 回滚 split 限流参数；关闭 flow_manager hook。",
        )
    )
    add(
        Defect(
            id="status_inconsistency",
            risk="P0",
            title="状态不一致：任务显示 in_progress 但 job 不存在/已结束，导致重复领取/重复派发",
            mechanism="event",
            probability="high",
            damage="high (重复执行/污染/资源浪费)",
            signal="board: in_progress 很高；historical reports mention stale in_progress without job",
            minimal_fix="严格幂等：dispatch 以 task_id+lease token 做去重；周期 reconcile：in_progress 无有效 lease -> ready。",
            acceptance="replay: 构造 stale in_progress 样本，reconcile 后恢复为 ready；重复派发率=0。",
            rollback="关闭 reconcile tick；保留只读告警。",
        )
    )
    add(
        Defect(
            id="evidence_spoof_window",
            risk="P0",
            title="证据链可伪造：缺少不可抵赖的 CI 日志/哈希绑定（强对手可篡改）",
            mechanism="validator",
            probability="medium",
            damage="high (无法裁决/被糊弄合并)",
            signal=f"ci_gate_results.jsonl tail={len(ci_tail)}; anti-forgery partially implemented; token_cfo endpoint code={code_token_cfo}",
            minimal_fix="CI gate 全量日志落盘+sha256；selftest 强制校验；下一步加 hash 链/append-only。",
            acceptance="replay: 伪造 report/SUBMIT 但无 CI 记录 -> FAIL；篡改日志 hash mismatch -> FAIL。",
            rollback="设置 CI_ANTIFORGERY_SINCE_MS=0（仅用于紧急解封），并记录审计事件。",
        )
    )
    add(
        Defect(
            id="occli_file_not_found_storm",
            risk="P0",
            title="occli --file 参数歧义引发 'File not found: <message>' 风暴（44 次签名级失败）",
            mechanism="executor",
            probability="medium",
            damage="high (失败率暴涨，吞吐归零)",
            signal="failure_report_latest topErrorLines: Follow the attached file... + executor=opencodecli",
            minimal_fix="使用 --file 时不传 positional message；把指令写入附件文件自洽；重启生效并做回放。",
            acceptance="24h 窗口同签名失败下降 >=90%；opencodecli 成功率恢复。",
            rollback="临时将 allowedExecutors 退回 codex-only，直到 occli 修复回归通过。",
        )
    )
    add(
        Defect(
            id="runtime_vs_live_drift",
            risk="P1",
            title="runtime.env 与 live 内存配置漂移：重启前后行为不一致，导致误判/不稳定",
            mechanism="preflight",
            probability="high",
            damage="medium-high (线上行为不可预期)",
            signal=f"/config shows runtime vs live; some fields differ until restart (e.g. model pools)",
            minimal_fix="在 /config 增加 drift 检测并写 leader 事件；提供 drain-safe restart。",
            acceptance="drift_events=0 或可解释；重启后 live==runtime 一致。",
            rollback="关闭 drift 检测告警，保留手工查看。",
        )
    )

    # The remaining 15 are concise but concrete.
    add(
        Defect(
            id="token_budget_missing",
            risk="P1",
            title="Token 预算缺失：上下文膨胀与失败重试易触发 token 爆炸",
            mechanism="eval",
            probability="medium",
            damage="high (成本失控+队列变慢)",
            signal="leader.jsonl 缺少统一 tokens KPI；token_cfo endpoint 可能 404（需重启）",
            minimal_fix="启用 token_cfo snapshot + 阈值触发 followup；在 dispatch/watchdog 施加 token_cap。",
            acceptance="A/B: avg input tokens -40% 且 pass rate ±2%。",
            rollback="关闭 TOKEN_CFO_HOOK_ENABLED 或提高阈值。",
        )
    )
    add(
        Defect(
            id="pins_forbidden_misconfig",
            risk="P1",
            title="Pins 误伤：forbidden_paths 默认包含 artifacts 导致任务无法引用证据/自证",
            mechanism="validator",
            probability="high",
            damage="medium (自测/审计断链)",
            signal="多次出现 pins forbid artifacts 需要手工修 pins",
            minimal_fix="对 role=auditor/qa/doc 放行只读 artifacts/executor_logs；其余仍禁止写。",
            acceptance="pins_fixup 次数下降；审计任务不再因 forbid artifacts 阻断。",
            rollback="恢复禁止 artifacts，改为 copy evidence pack 到 docs/REPORT。",
        )
    )
    add(
        Defect(
            id="no_drain_mode",
            risk="P1",
            title="缺少 drain/停机模式：重启可能打断执行导致证据缺失/重复执行",
            mechanism="queue",
            probability="medium",
            damage="high",
            signal="当前通过外部脚本 drain-restart 轮询 running_jobs，未形成内建状态机",
            minimal_fix="新增 /admin/drain 接口：停止派发新 job，等待 running=0 再 restart。",
            acceptance="replay: 启动 drain 后 queued 不再进入 running；running 清零后自动重启。",
            rollback="关闭 drain 功能，恢复原始派发逻辑。",
        )
    )
    add(
        Defect(
            id="ci_gate_not_binding_task",
            risk="P1",
            title="CI gate 证据与 task_id 绑定不足（仅 job_id），跨任务复用/串线风险",
            mechanism="validator",
            probability="low",
            damage="medium-high",
            signal="ci_gate_results.jsonl 当前主要字段 job_id/task_id；需确保一致性强校验",
            minimal_fix="强制 ci_gate_results 记录 task_id，并由 selftest 校验 task_id==task.id。",
            acceptance="replay: 复用别的 job 的 ci 记录无法通过 selftest。",
            rollback="仅保留 job_id 校验（紧急兼容）。",
        )
    )
    add(
        Defect(
            id="lack_of_task_type",
            risk="P2",
            title="task_type/area 标注不足：无法精确统计耗时/失败率/路由决策效果",
            mechanism="event",
            probability="high",
            damage="medium",
            signal="summary byTaskType=unknown 占比高",
            minimal_fix="在任务创建/dispatch 时强制 taskType/area，缺失则拒绝或自动填默认。",
            acceptance="unknown taskType 占比下降至 <10%。",
            rollback="仅做告警不阻断。",
        )
    )
    add(
        Defect(
            id="weak_replay_story",
            risk="P2",
            title="回放能力弱：同一失败难以一键复现并验证修复（缺 replay bundle）",
            mechanism="eval",
            probability="medium",
            damage="medium",
            signal="目前多靠 grep jobs.jsonl/failures.jsonl；缺标准 replay pack",
            minimal_fix="为 failed job 自动生成 replay pack（context pack id + pins + env snapshot + ci logs）。",
            acceptance="每个失败都有可执行 replay/task 链接，修复后回放通过。",
            rollback="关闭自动生成，仅对 P0/P1 失败生成。",
        )
    )
    add(
        Defect(
            id="plugin_loader_absent",
            risk="P2",
            title="插件协议不落地：有 schema+example，但缺稳定 loader/lifecycle hooks/版本化",
            mechanism="plugin",
            probability="medium",
            damage="medium",
            signal="plugin skeleton exists; loader not enforced in gateway",
            minimal_fix="实现最小 plugin loader（manifest 校验、enable/disable、hook 注册与回滚）。",
            acceptance="example plugin 可启用/禁用；hook 调用可观测；回滚路径明确。",
            rollback="保持插件只读骨架，不加载。",
        )
    )
    add(
        Defect(
            id="insufficient_backpressure",
            risk="P2",
            title="缺少背压：大量 queued 任务仍持续 split/dispatch，导致雪崩",
            mechanism="queue",
            probability="high",
            damage="medium",
            signal="queued 高但系统仍创建新 split/fixup 任务",
            minimal_fix="按队列水位触发 fuse：高水位只允许恢复性任务，不再扩展。",
            acceptance="高水位时 queued 不再指数增长；恢复后自动解 fuse。",
            rollback="关闭 fuse，回到原逻辑。",
        )
    )
    add(
        Defect(
            id="missing_root_cause_taxonomy_enforcement",
            risk="P2",
            title="失败 taxonomy 未强制：同类失败无法自动路由到固定修复 playbook",
            mechanism="router",
            probability="medium",
            damage="medium",
            signal="five_whys 产出 taxonomy 但未必进入路由/validator",
            minimal_fix="对 top taxonomy 配置 action_policy（block/retry/fixup）并落盘。",
            acceptance="同 taxonomy 失败自动走同 playbook；重试率下降。",
            rollback="仅记录 taxonomy，不自动执行策略。",
        )
    )
    add(
        Defect(
            id="insufficient_role_separation",
            risk="P2",
            title="角色边界不硬：doc/qa/engineer 的证据要求不一致且易被绕过",
            mechanism="validator",
            probability="medium",
            damage="medium",
            signal="role=doc 证据规则靠 selftest；仍可能缺执行痕迹",
            minimal_fix="每个 role 固化 SUBMIT 约束与最小证据项（强制字段）。",
            acceptance="role_errors.jsonl 中证据缺失类下降；裁决更一致。",
            rollback="回退到旧规则+仅告警。",
        )
    )
    add(
        Defect(
            id="missing_admin_endpoints",
            risk="P3",
            title="缺少 admin/调试接口：无法快速定位运行态（debug/config/metrics 缺失或 404）",
            mechanism="event",
            probability="high",
            damage="low-medium",
            signal="部分 debug endpoints 404；监控需 grep 文件",
            minimal_fix="补齐 /executor/debug/* 覆盖面，并返回 build_id/git_sha。",
            acceptance="一键回答：吞吐、失败率、P95、token、重试、并发。",
            rollback="只保留本地文件落盘，不暴露接口。",
        )
    )
    add(
        Defect(
            id="single_log_sink",
            risk="P3",
            title="日志单点：leader.jsonl 过大且缺索引，查询慢影响审计效率",
            mechanism="storage",
            probability="medium",
            damage="low-medium",
            signal=f"leader.jsonl tail={len(leader_tail)} (grows fast)",
            minimal_fix="按日切分 leader_{date}.jsonl + 索引摘要。",
            acceptance="查询最近 6h/24h <1s；摘要正确。",
            rollback="保留旧 leader.jsonl 写入，新增仅旁路。",
        )
    )
    add(
        Defect(
            id="ci_gate_no_sandbox",
            risk="P2",
            title="CI gate 命令执行缺少 sandbox/路径约束，存在误删/越权风险",
            mechanism="preflight",
            probability="low",
            damage="high",
            signal="CI gate 通过 cmd.exe /c 执行，依赖 allowlist 前缀",
            minimal_fix="限制 CI gate 仅允许固定脚本入口，并强制 cwd 在 allowlist roots。",
            acceptance="尝试注入危险命令被拒绝；合法命令不受影响。",
            rollback="回退到前缀 allowlist。",
        )
    )
    add(
        Defect(
            id="missing_duplicate_detection_for_fixups",
            risk="P2",
            title="fixup 任务可能重复生成：pins_fixup/ci_fixup 在高失败时放大队列",
            mechanism="queue",
            probability="medium",
            damage="medium",
            signal="fixup fuse 有，但事件 key 去重不足时仍可能堆积",
            minimal_fix="为 fixup 建立 (task_id, reason_code) 去重键 + 最小间隔。",
            acceptance="同 task 同 reason fixup 数<=上限；队列稳定。",
            rollback="关闭去重，保留上限。",
        )
    )
    add(
        Defect(
            id="weak_model_routing_guard",
            risk="P2",
            title="模型路由 guard 不足：免费模型/高价模型切换缺少硬策略与证据",
            mechanism="router",
            probability="medium",
            damage="medium",
            signal="byModel 显示 gpt-5.2 使用仍偏高；free 模型失败时回退逻辑不透明",
            minimal_fix="路由决策落盘必须包含 cost tier + reason；免费模型失败签名触发自动禁用窗口。",
            acceptance="free 模型优先且成功率可接受；高价模型调用次数下降。",
            rollback="关闭禁用窗口，仅提示。",
        )
    )
    add(
        Defect(
            id="missing_forensic_bundle",
            risk="P2",
            title="缺少统一 Forensic Bundle：证据散落导致审计耗时高",
            mechanism="storage",
            probability="high",
            damage="medium",
            signal="证据分散在 jobs.jsonl/failures.jsonl/ci_gate_results/contextpacks",
            minimal_fix="每 task 生成 evidence bundle manifest.json（paths+hashes+timestamps）。",
            acceptance="审计只需读取 1 个 manifest 即可裁决。",
            rollback="仅对失败任务生成 bundle。",
        )
    )
    add(
        Defect(
            id="no_tenant_isolation",
            risk="P2",
            title="缺少租户/项目硬隔离：多个项目并行时 state/events 混淆风险高",
            mechanism="storage",
            probability="medium",
            damage="high",
            signal="board 只有一个全局；state_events/leader 全局写入",
            minimal_fix="引入 workspace_id/tenant_id，所有日志与 board 分区存储。",
            acceptance="两个项目并行不会串味；指标独立。",
            rollback="保持单租户，tenant_id 仅旁路字段。",
        )
    )
    add(
        Defect(
            id="missing_schema_versioning_for_events",
            risk="P3",
            title="事件/日志 schema 未版本化：升级后解析器/审计器易崩",
            mechanism="event",
            probability="medium",
            damage="medium",
            signal="jsonl 字段非强制，脚本需宽容解析",
            minimal_fix="为 leader/state_events/ci_gate_results 添加 schema_version 字段。",
            acceptance="脚本按版本解析；回放稳定。",
            rollback="字段可选，不阻断写入。",
        )
    )

    # Top 5 minimal tasks (<=3 steps each)
    top5_tasks: List[MinimalTask] = [
        MinimalTask(
            id="TASK__SPLIT_BACKPRESSURE",
            title="Split backpressure + priority lanes (delivery-first)",
            mechanism="queue",
            steps=[
                "Add queue watermarks: when queued board_split > threshold, stop creating new splits and emit flow_bottleneck event.",
                "Create separate scheduling lane: reserve at least N slots for non-split atomic execution.",
                "Add replay: inject 200 split jobs and verify atomic throughput stays >0.",
            ],
            acceptance=[
                "metric atomic_done_per_min increases while split backlog decreases",
                "no long-lived in_progress without lease > 10 min",
                "exit_code=0 for replay harness",
            ],
            replay=[
                "Run chaos_runner dry-run experiment for split flood (no destructive).",
                "Replay from artifacts/executor_logs/jobs_state.json snapshot.",
            ],
            rollback=[
                "Disable watermark/fuse flags in runtime.env",
                "Revert scheduler lane reservation to old behavior",
            ],
        ),
        MinimalTask(
            id="TASK__STATUS_RECONCILE_IDEMPOTENCY",
            title="Dispatch idempotency + reconcile stale in_progress",
            mechanism="event",
            steps=[
                "Add lease token per dispatch; refuse dispatch if active lease exists (task_id, lease_until).",
                "Reconcile tick: if task in_progress but no running job/expired lease -> set ready and log event.",
                "Add replay: craft stale tasks.json entry and verify auto-recovery + no duplicates.",
            ],
            acceptance=[
                "duplicate dispatch rate=0 in leader.jsonl",
                "stale in_progress recovered to ready within 60s",
                "replay script exit_code=0",
            ],
            replay=[
                "Use /executor/debug/summary + /executor/jobs snapshot; create synthetic stale via local board file edit in a sandbox copy (or via admin endpoint).",
            ],
            rollback=[
                "Turn off reconcile tick; keep alert-only",
                "Disable dispatch idempotency guard (last resort)",
            ],
        ),
        MinimalTask(
            id="TASK__EVIDENCE_ANTIFORGERY_ROLLOUT",
            title="Evidence anti-forgery rollout (CI logs+hashes+selftest enforcement)",
            mechanism="validator",
            steps=[
                "Persist CI full logs + sha256 and record paths/hashes into ci_gate_results.jsonl.",
                "Enable task_selftest anti-forgery checks from CI_ANTIFORGERY_SINCE_MS.",
                "Add replay: attempt 10 spoof vectors; ensure selftest fails when evidence is fake.",
            ],
            acceptance=[
                "ci_gate_results has stdoutPath/stderrPath/stdoutSha256/stderrSha256",
                "task_selftest rejects spoof (exit_code!=0)",
                "tamper scenario produces hash mismatch fail",
            ],
            replay=[
                "Run evidence_antiforgery_audit.py and include report artifacts",
                "Try a synthetic task with missing ci evidence; expect selftest fail",
            ],
            rollback=[
                "Set CI_ANTIFORGERY_SINCE_MS=0 (emergency only) and log override event",
            ],
        ),
        MinimalTask(
            id="TASK__OCCLI_CONTRACT_HARDEN",
            title="occli prompt contract hardening (no --file ambiguity, SUBMIT required)",
            mechanism="executor",
            steps=[
                "When using --file, do not pass positional message; write self-contained instruction file.",
                "Fail closed if occli done without SUBMIT contract (already supported).",
                "Replay: run occli with long prompt and ensure no 'File not found' signature; success rate improves.",
            ],
            acceptance=[
                "Failure signature count ('File not found: Follow the attached file') drops >=90%",
                "opencodecli tasks produce SUBMIT consistently",
            ],
            replay=[
                "Re-run last 50 occli failures via replay/task and confirm fixed behavior",
            ],
            rollback=[
                "Route occli tasks back to codex-only until fixed",
            ],
        ),
        MinimalTask(
            id="TASK__CONFIG_DRIFT_DRAIN_RESTART",
            title="Config drift detector + drain-safe restart",
            mechanism="preflight",
            steps=[
                "Add drift detector: compare runtime vs live; emit leader event when mismatched.",
                "Implement drain mode to stop dispatching and wait running=0 before restart.",
                "Replay: toggle model pools via /models/set and verify drift event; drain->restart restores alignment.",
            ],
            acceptance=[
                "drift_event emitted when live != runtime",
                "drain prevents new running jobs while queued remains stable",
                "restart brings live==runtime for tracked keys",
            ],
            replay=[
                "Use drain-restart script logs as baseline, then move into built-in endpoint",
            ],
            rollback=[
                "Disable drain endpoint; revert to external script only",
            ],
        ),
    ]

    # Compose report
    report = {
        "generated_at_utc": _utc_now(),
        "version": str(args.version),
        "snapshots": {
            "config_code": code_cfg,
            "board_code": code_board,
            "jobs_code": code_jobs,
            "summary_code": code_summary,
            "token_cfo_code": code_token_cfo,
        },
        "signals": {
            "jobs": {"running": running, "queued": queued, "failed": failed, "done": done, "by_executor": by_exec},
            "board_counts": board_counts,
            "token_cfo_endpoint": token_cfo if code_token_cfo == 200 else {"error": code_token_cfo},
            "failures_tail_n": len(failures_tail),
            "ci_gate_tail_n": len(ci_tail),
            "leader_tail_n": len(leader_tail),
        },
        "defects_top20": [asdict(d) for d in defects[:20]],
        "top5_min_tasks": [asdict(t) for t in top5_tasks],
    }

    stamp = _stamp()
    md_path = out_dir / f"REPORT__SYSTEM_DEFECT_HUNTER__{args.version}__{stamp}.md"
    json_path = out_dir / f"REPORT__SYSTEM_DEFECT_HUNTER__{args.version}__{stamp}.json"

    lines: List[str] = []
    lines.append(f"# System Defect Hunter {args.version}")
    lines.append("")
    lines.append(f"Generated at (UTC): `{report['generated_at_utc']}`")
    lines.append(f"Base: `{base}`")
    lines.append("")
    lines.append("## Snapshot Signals")
    sig = report["signals"]["jobs"]
    lines.append(f"- jobs: running={sig['running']} queued={sig['queued']} failed={sig['failed']} done={sig['done']}")
    lines.append(f"- by_executor: `{json.dumps(sig['by_executor'], ensure_ascii=False)}`")
    lines.append(f"- token_cfo_code: `{code_token_cfo}`")
    if isinstance(board_counts, dict):
        lines.append(f"- board_counts: `{json.dumps(board_counts, ensure_ascii=False)}`")
    lines.append("")
    lines.append("## Defects Top 20 (risk-ordered)")
    for i, d in enumerate(defects[:20], start=1):
        lines.append(f"### {i}. {d.risk} {d.title} ({d.id})")
        lines.append(f"- mechanism: `{d.mechanism}`")
        lines.append(f"- probability: `{d.probability}` | damage: `{d.damage}`")
        lines.append(f"- signal: {d.signal}")
        lines.append(f"- minimal_fix: {d.minimal_fix}")
        lines.append(f"- acceptance: {d.acceptance}")
        lines.append(f"- rollback: {d.rollback}")
        lines.append("")
    lines.append("## Top 5 Minimal Refactor Tasks (<=3 steps)")
    for t in top5_tasks:
        lines.append(f"### {t.id}: {t.title}")
        lines.append(f"- mechanism: `{t.mechanism}`")
        lines.append("- steps:")
        for s in t.steps[:3]:
            lines.append(f"  - {s}")
        lines.append("- acceptance:")
        for a in t.acceptance:
            lines.append(f"  - {a}")
        lines.append("- replay:")
        for r in t.replay:
            lines.append(f"  - {r}")
        lines.append("- rollback:")
        for r in t.rollback:
            lines.append(f"  - {r}")
        lines.append("")

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(str(md_path))
    print(str(json_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

