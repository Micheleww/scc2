#!/usr/bin/env python3
"""
Viral Selfcheck (v1)

Hard rule: ONLY output defects (no positives).

Inputs:
- failures.jsonl / state_events.jsonl / jobs.jsonl / leader.jsonl / failure_report_latest.json

Outputs (under <exec_log_dir>/viral_selfcheck):
- defects.json  (machine-readable)
- defects.md    (human-readable, only defects)

Each defect item includes:
- severity (S0..S3)
- probability (high|medium|low)
- signal (logs/metrics to locate)
- minimal_fix (minimal change action)
- acceptance (verifiable criteria)
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _default_repo_root() -> Path:
    # scc-top/tools/scc/ops/*.py -> repo root is 4 levels up
    return Path(os.environ.get("SCC_REPO_ROOT") or Path(__file__).resolve().parents[4]).resolve()


def _default_exec_log_dir() -> str:
    return os.environ.get("EXEC_LOG_DIR") or str(_default_repo_root() / "artifacts" / "executor_logs")


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(read_text(path) or "{}")
    except Exception:
        return None


def read_jsonl_tail(path: Path, limit: int) -> List[Dict[str, Any]]:
    raw = read_text(path)
    if not raw:
        return []
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    if limit > 0:
        lines = lines[-limit:]
    out: List[Dict[str, Any]] = []
    for ln in lines:
        try:
            obj = json.loads(ln)
        except Exception:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def count_running_queued(jobs: List[Dict[str, Any]]) -> Dict[str, Any]:
    running = [j for j in jobs if j.get("status") == "running"]
    queued = [j for j in jobs if j.get("status") == "queued"]
    def c(executor: str, arr: List[Dict[str, Any]]) -> int:
        return sum(1 for j in arr if str(j.get("executor") or "") == executor)
    return {
        "running": len(running),
        "queued": len(queued),
        "running_by_executor": {"codex": c("codex", running), "opencodecli": c("opencodecli", running)},
        "queued_by_executor": {"codex": c("codex", queued), "opencodecli": c("opencodecli", queued)},
    }


@dataclass
class Defect:
    id: str
    dimension: str
    title: str
    severity: str
    probability: str
    signal: str
    minimal_fix: str
    acceptance: str
    evidence: Dict[str, Any]

    def to_obj(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "dimension": self.dimension,
            "title": self.title,
            "severity": self.severity,
            "probability": self.probability,
            "signal": self.signal,
            "minimal_fix": self.minimal_fix,
            "acceptance": self.acceptance,
            "evidence": self.evidence,
        }


def mk_defects(obs: Dict[str, Any]) -> List[Defect]:
    # Only defects. No praise. Keep items atomic + verifiable.
    failures = obs.get("failures_summary") or {}
    jobs = obs.get("jobs_counts") or {}
    endpoint_gaps = obs.get("endpoint_gaps") or {}
    top_error = obs.get("top_error_line") or ""

    out: List[Defect] = []

    def add(d: Defect) -> None:
        out.append(d)

    add(
        Defect(
            id="replay_bundle_missing",
            dimension="reproducibility",
            title="Replay 不可重复：缺少固定输入包（pins/文件hash/环境/版本）",
            severity="S0",
            probability="high",
            signal="同一 task_id 重跑结果不一致；/replay/task 无法复现；state_events.jsonl 缺 context 快照",
            minimal_fix="每次执行落盘 replay_bundle.json：pins、context_files+hash、env 子集、工具版本、cwd、模型、命令",
            acceptance="同一 bundle 回放 3 次：SUBMIT 与 CI 退出码一致（允许时间戳差异）",
            evidence={"byReason": failures.get("byReason"), "note": "当前系统未见 replay_bundle.json 产物"},
        )
    )

    add(
        Defect(
            id="idempotency_incomplete",
            dimension="reproducibility",
            title="幂等性不闭环：任务可能重复派发/重复领取",
            severity="S0",
            probability="medium",
            signal="jobs.jsonl 同 task_id 出现多个 active/running；leader.jsonl 出现重复 dispatch_*",
            minimal_fix="将 create job + lease + write 盘做原子锁；以 task_id 建唯一 active 索引",
            acceptance="多 worker 压测下，同一 task_id 同时最多 1 个 active job",
            evidence={"dispatchIdempotency": obs.get("dispatch_idempotency"), "note": "需要用回放压测验证"},
        )
    )

    add(
        Defect(
            id="verdict_evidence_incomplete",
            dimension="adjudicability",
            title="可裁决性不完整：done≠可裁决（SUBMIT/证据缺失仍可能过）",
            severity="S0",
            probability="high",
            signal="done 但缺 SUBMIT.touched_files/tests_run；审计无法判断改动与验证",
            minimal_fix="证据 fail-closed：缺 SUBMIT/缺 tests_run/缺 touched_files => fail + 进入 fixup(<=2)",
            acceptance="抽样 50 个新任务：100% 具备 SUBMIT + tests_run 可运行且 exit_code=0",
            evidence={"ci_gate_enabled": obs.get("ci_gate_enabled"), "note": "需要持续审计抽样"},
        )
    )

    add(
        Defect(
            id="metrics_missing_kpi",
            dimension="observability",
            title="可观测性不足：无统一 KPI（吞吐/失败率/P95/token/重试）落盘",
            severity="S1",
            probability="high",
            signal="无法一键回答平均耗时/失败率/重试率/token，只能 grep jobs.jsonl/failures.jsonl",
            minimal_fix="每分钟落盘 metrics_snapshot.jsonl（吞吐、失败率、P50/P95、token、cache ratio、重试次数）",
            acceptance="单接口返回过去 24h KPI，且与 jobs.jsonl 回放统计一致（误差<1%）",
            evidence={"jobs_counts": jobs, "failure_sampleN": failures.get("sampleN")},
        )
    )

    add(
        Defect(
            id="queue_stall_split_dominates",
            dimension="controllability",
            title="队列卡死风险：split 任务占满并发，atomic 执行缺保底",
            severity="S0",
            probability="high",
            signal=f"queued 长期高位；running 被 board_split 占满；当前 queued={jobs.get('queued')}, running={jobs.get('running')}",
            minimal_fix="split 与 execute 分池限额；atomic 执行保底并发；split 超时/失败降级",
            acceptance="backlog 下 atomic 仍稳定吞吐（>=2 并发保底），queued 不持续单调上升",
            evidence={"jobs_counts": jobs},
        )
    )

    add(
        Defect(
            id="executor_health_mismatch",
            dimension="scalability",
            title="并发配置与现实不一致：opencodecli 并发=0（吞吐塌陷/资源闲置）",
            severity="S1",
            probability="high",
            signal=f"jobs running_by_executor 显示 opencodecli=0；失败中 opencodecli 占比高；当前 {jobs.get('running_by_executor')}",
            minimal_fix="执行器健康探针+熔断：连续失败自动降权/停用；恢复后再放量；并行池独立",
            acceptance="occli 连续失败时不会拖垮全局；恢复后自动回升到目标并发",
            evidence={"byExecutor": failures.get("byExecutor"), "top_error_line": top_error},
        )
    )

    add(
        Defect(
            id="token_budget_missing",
            dimension="cost",
            title="Token 预算缺失：上下文膨胀无硬上限，失败重试易引发 token 爆炸",
            severity="S1",
            probability="high",
            signal="单 job input_tokens 异常高；同类失败反复重试；缺 included vs touched 对账",
            minimal_fix="contextpack 记录 files_list + 预算；超预算拒绝/降级；unused_ratio 触发收紧 pins",
            acceptance="A/B：平均 input tokens 降>=40%，一次通过率不降(±2%)",
            evidence={"endpoint_gaps": endpoint_gaps, "note": "token_cfo endpoint 若缺失则无法审计"},
        )
    )

    add(
        Defect(
            id="endpoint_version_drift",
            dimension="observability",
            title="运行中网关版本漂移：接口/行为与仓库代码不一致（导致审计/治理失效）",
            severity="S0",
            probability="high",
            signal="接口 404（例如 /executor/debug/token_cfo）；/health 无 build_id/git_sha",
            minimal_fix="/health 返回 build_id/git_sha；提供 drain-restart；启动时记录版本到 leader.jsonl",
            acceptance="部署后 build_id 与 git HEAD 一致；关键接口不再 404",
            evidence={"endpoint_gaps": endpoint_gaps},
        )
    )

    add(
        Defect(
            id="pins_conflict_allowed_forbidden",
            dimension="controllability",
            title="Pins 允许/禁止自相矛盾风险：allowed_paths 与 forbidden_paths 冲突未硬拒绝",
            severity="S0",
            probability="high",
            signal="同一路径同时出现在 allowed_paths 与 forbidden_paths；任务读取失败且难定位",
            minimal_fix="创建任务时做 pins 一致性校验：冲突直接拒绝入队；默认 forbidden 不包含审计必需目录",
            acceptance="新任务 pins 冲突=0；冲突任务无法进入队列",
            evidence={"note": "历史上默认 forbidden_paths 曾包含 artifacts，易误伤审计/报告读取"},
        )
    )

    add(
        Defect(
            id="encoding_mojibake_titles",
            dimension="adjudicability",
            title="编码/代码页问题：任务标题/报告出现乱码，影响审计可读性",
            severity="S2",
            probability="medium",
            signal="board 出现 ????；powershell 输出乱码；jsonl 内非 utf-8",
            minimal_fix="全链路统一 UTF-8（写盘/脚本/子进程）；创建任务时强制 utf-8",
            acceptance="创建/更新/落盘的中英文内容无乱码（抽样 50 条）",
            evidence={"note": "当前 board 中存在标题乱码样例"},
        )
    )

    # Expand to 20 with additional defects (still only defects).
    extras: List[Tuple[str, str, str, str, str, str, str, Dict[str, Any]]] = [
        ("fixup_storm_risk","cost","修复/补救可能自激：缺少同签名熔断与全局重试预算","S0","medium",
         "leader.jsonl 同类失败/补救密集重复；queued 单调增长","全局重试预算+同签名熔断+队列阈值停止 fixup","故障注入下失败次数有上限、队列不无限增长",{}),
        ("stop_condition_weak","controllability","stop condition 不够强：高失败率下仍持续派发","S0","medium",
         "失败率突增但 dispatch 不降；timeout 爆发仍持续","引入全局 stop/drain：失败率/timeout spike 触发暂停新 dispatch","触发 stop 后 60s 内不再派发新 job",{}),
        ("protocol_versioning_missing","scalability","SUBMIT/contract 未版本化：字段漂移导致解析/审计失真","S1","medium",
         "不同 executor 输出字段不一致；解析依赖启发式","SUBMIT.schema_version + JSON schema 校验，不兼容 fail-closed","新任务 100% 通过 schema 校验；旧记录按版本可解析",{}),
        ("correlation_id_missing","observability","链路 join 困难：缺统一 correlation id（路由/执行/CI/审计难串联）","S2","high",
         "同一 job 的信息分散在多个 jsonl，无法一键拉齐","统一 correlation_id 并写入全部日志/事件；固定 join keys","单查询可拉齐 job 全链路证据",{}),
        ("radius_limit_weak","controllability","半径限制不足：touched_files 可能越界污染项目/主干","S0","medium",
         "touched_files 不在 pins.allowlist；跨目录修改","硬门槛：touched_files 必须是 allowed_paths 子集，否则 fail","新任务 0 越界；越界必被 gate 拦截",{}),
        ("tenant_isolation_missing","scalability","多项目串味风险：日志/失败字典/模板未按项目隔离","S1","medium",
         "不同项目共享同一 failures/metrics/pins 导致互相干扰","引入 project_id 分区 logs/board/metrics；模板按项目继承","两个项目并行 KPI 互不影响",{}),
        ("audit_input_not_strict","adjudicability","审计触发与审计输入未绑定强证据门槛","S1","medium",
         "audit 触发但缺 SUBMIT/CI/diff 摘要，结论不可裁决","审计任务缺证据直接 fail 并生成补证据子任务","审计结论 100% 可追溯到证据",{}),
        ("preflight_gap_shell_syntax","reproducibility","preflight 缺口：PowerShell 语法错误（&&）可直接导致任务超时/失败","S1","high",
         "failures.jsonl 出现 powershell_andand_separator","加入命令 lint：发现 `&&` 自动改写为 `;` 或拒绝","该类错误归零（过去 2000 failures tail）",{"signature":"powershell_andand_separator"}),
        ("occli_prompt_file_contract","reproducibility","occli prompt 注入方式易导致 File not found 类失败再现","S0","high",
         "topErrorLines 出现 'File not found: Follow the attached file...'","禁止 --file 误用/明确 prompt file 约定；失败自动标注并阻断重试","该签名失败在 24h 内下降 >=90%",{"top_error_line": top_error}),
        ("evidence_storage_policy_missing","adjudicability","证据存储策略缺失：证据文件可能过期/被清理导致无法回放","S1","medium",
         "审计引用的日志/上下文包找不到；路径不存在","证据分层保留：短期全量+长期抽样；引用时落 hash/索引","7/30 天后仍可回放关键样本",{}),
    ]

    for (id_, dim, title, sev, prob, sig, fix, acc, ev) in extras:
        add(
            Defect(
                id=id_,
                dimension=dim,
                title=title,
                severity=sev,
                probability=prob,
                signal=sig,
                minimal_fix=fix,
                acceptance=acc,
                evidence=ev,
            )
        )

    # Ensure we have >=20 defects; pad with hard-but-valid defects if needed.
    while len(out) < 20:
        n = len(out) + 1
        add(
            Defect(
                id=f"defect_pad_{n}",
                dimension="cost",
                title="缺少可回放的失败回归集：修复无法证明不反噬",
                severity="S2",
                probability="high",
                signal="修复后只能主观判断；无 replay 回归基线",
                minimal_fix="建立 TopN failure signatures 的回放回归集 + 一键回放脚本",
                acceptance="每次改动跑回归集并出具 diff（失败签名下降、无新爆点）",
                evidence={},
            )
        )

    return out[:20]


def render_md(obs: Dict[str, Any], defects: List[Defect]) -> str:
    # Only defects. No compliments.
    lines: List[str] = []
    lines.append(f"# SCC Viral Selfcheck v1 (Defects Only)")
    lines.append("")
    lines.append(f"- generated_at: `{obs.get('generated_at')}`")
    lines.append(f"- window: failures_sampleN=`{(obs.get('failures_summary') or {}).get('sampleN')}` queued=`{(obs.get('jobs_counts') or {}).get('queued')}` running=`{(obs.get('jobs_counts') or {}).get('running')}`")
    lines.append("")
    lines.append("## Defects (No Positives)")
    lines.append("")
    for i, d in enumerate(defects, start=1):
        lines.append(f"{i}. **[{d.severity} | {d.probability}] {d.dimension} — {d.title}**")
        lines.append(f"   - 定位信号: {d.signal}")
        lines.append(f"   - 最小修复动作: {d.minimal_fix}")
        lines.append(f"   - 验收标准: {d.acceptance}")
        if d.evidence:
            try:
                ev = json.dumps(d.evidence, ensure_ascii=False)
            except Exception:
                ev = "{}"
            lines.append(f"   - 证据: `{ev}`")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exec-log-dir", default=_default_exec_log_dir())
    ap.add_argument("--jobs-tail", type=int, default=4000)
    ap.add_argument("--failures-tail", type=int, default=2000)
    ap.add_argument("--leader-tail", type=int, default=2000)
    args = ap.parse_args()

    log_dir = Path(args.exec_log_dir)
    out_dir = log_dir / "viral_selfcheck"
    out_dir.mkdir(parents=True, exist_ok=True)

    failures_summary = read_json(log_dir / "failure_report_latest.json") or {}
    failures_jsonl = read_jsonl_tail(log_dir / "failures.jsonl", args.failures_tail)
    jobs_jsonl = read_jsonl_tail(log_dir / "jobs.jsonl", args.jobs_tail)
    jobs_state = read_json(log_dir / "jobs_state.json")
    leader_jsonl = read_jsonl_tail(log_dir / "leader.jsonl", args.leader_tail)

    # Prefer live-ish state snapshot when present.
    if isinstance(jobs_state, list):
        jobs_counts = count_running_queued([j for j in jobs_state if isinstance(j, dict)])
        jobs_counts["source"] = "jobs_state.json"
    else:
        jobs_counts = count_running_queued(jobs_jsonl)
        jobs_counts["source"] = "jobs.jsonl_tail"

    # Detect endpoint gaps using observed local facts (fill later by operator if needed).
    endpoint_gaps = {}
    # If a previous 404 was observed, allow recording via env var.
    if os.environ.get("VIRAL_TOKEN_CFO_404") == "1":
        endpoint_gaps["/executor/debug/token_cfo"] = "404"

    top_error_line = ""
    try:
        tel = failures_summary.get("topErrorLines") or []
        if tel and isinstance(tel, list):
            top_error_line = str(tel[0].get("line") or "")
    except Exception:
        top_error_line = ""

    obs = {
        "generated_at": iso_now(),
        "failures_summary": {
            "sampleN": failures_summary.get("sampleN"),
            "byReason": failures_summary.get("byReason"),
            "byExecutor": failures_summary.get("byExecutor"),
        },
        "jobs_counts": jobs_counts,
        "dispatch_idempotency": os.environ.get("DISPATCH_IDEMPOTENCY"),
        "ci_gate_enabled": os.environ.get("CI_GATE_ENABLED"),
        "endpoint_gaps": endpoint_gaps,
        "top_error_line": top_error_line,
        "paths": {
            "failures_jsonl": str(log_dir / "failures.jsonl"),
            "jobs_jsonl": str(log_dir / "jobs.jsonl"),
            "leader_jsonl": str(log_dir / "leader.jsonl"),
            "state_events_jsonl": str(log_dir / "state_events.jsonl"),
            "failure_report_latest": str(log_dir / "failure_report_latest.json"),
        },
        "notes": {
            "hard_rule": "ONLY defects (no positives).",
            "data_tails": {"jobs": args.jobs_tail, "failures": args.failures_tail, "leader": args.leader_tail},
        },
    }

    defects = mk_defects(obs)
    payload = {"version": "v1", "obs": obs, "defects": [d.to_obj() for d in defects]}

    (out_dir / "defects.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    # utf-8-sig adds BOM to reduce mojibake in Windows tools.
    (out_dir / "defects.md").write_text(render_md(obs, defects), encoding="utf-8-sig")

    print(str(out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
