#!/usr/bin/env python3
"""
Five Whys Root Cause (v1)

Input:
- state_events.jsonl (recent tail)
- failures.jsonl (optional enrichment: stderrPreview/stdoutPreview/reason)

Output (under <exec_log_dir>/five_whys):
- report.json  (machine-readable)
- report.md    (human-readable; only "why" chains + prevention changes)

Goal:
- For each recent failure event: produce Five Whys, fixed taxonomy, and a system-level change to prevent recurrence.
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


def norm_sig(s: str) -> str:
    s = s or ""
    s = re.sub(r"[A-Z]:[\\/][^\s\"']+", "<PATH>", s, flags=re.I)
    s = re.sub(r"https?://\S+", "<URL>", s, flags=re.I)
    s = re.sub(r"\b\d+\b", "<N>", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s[:1600]


def classify_taxonomy(reason: str, enriched: Dict[str, Any]) -> str:
    r = (reason or "unknown").strip()
    msg = " ".join(
        [
            r,
            str(enriched.get("failure_stderr") or ""),
            str(enriched.get("failure_stdout") or ""),
            str(enriched.get("top_error_line") or ""),
        ]
    )
    s = norm_sig(msg)

    if r in ("ci_failed", "ci_skipped"):
        return "ci.gate.failed"
    if r in ("missing_pins", "missing_pins_template", "pins_insufficient"):
        return "pins.quality.insufficient"
    if r in ("missing_submit_contract",):
        return "executor.contract.submit"
    if r == "timeout":
        return "infra.process.timeout"
    if r == "rewrite_parent_goal_ascii":
        return "infra.encoding.non_ascii_payload"
    if "file not found: follow the attached file" in s:
        return "executor.occli.file_instruction_bug"
    if "not a valid statement separator" in s and "&&" in s:
        return "infra.shell.powershell_syntax"
    if "rate limit" in s or "too many requests" in s:
        return "model.throttle.rate_limited"
    if "unauthorized" in s or "401" in s:
        return "model.auth.unauthorized"
    if "econnreset" in s or "network" in s:
        return "infra.network.error"
    if r == "executor_error":
        if "file not found" in s or "no such file" in s:
            return "infra.fs.missing_file"
        return "executor.runtime.error"
    return "unknown"


def prevention_change_for_taxonomy(taxonomy: str) -> Dict[str, Any]:
    # System-level prevention changes. Must be verifiable + rollbackable.
    if taxonomy == "executor.occli.file_instruction_bug":
        return {
            "change": "occli prompt contract hardening: forbid --file misusage; require SUBMIT contract; preflight rejects 'Follow the attached file' meta-prompt injection.",
            "verification": [
                "Replay a known failing task signature and confirm failure disappears.",
                "CI gate exit_code=0 with SUBMIT present.",
            ],
            "rollback": ["Disable the new preflight via env flag; restart daemon."],
        }
    if taxonomy == "infra.process.timeout":
        return {
            "change": "Introduce phase timings + early timeout warnings; add split/execution pool separation so board_split cannot starve atomic execution.",
            "verification": ["Backlog test: atomic maintains >=2 concurrent; P95 duration decreases; timeouts drop."],
            "rollback": ["Revert pool separation flags; restart."],
        }
    if taxonomy == "ci.gate.failed":
        return {
            "change": "Fail-closed CI evidence: missing tests_run/touched_files cannot be done; add CI fixup loop (<=2) that patches tests/evidence then reruns CI.",
            "verification": ["Sample 50 new tasks: 100% have SUBMIT.tests_run and CI exit_code=0."],
            "rollback": ["Set CI_GATE_STRICT=false or disable CI_FIXUP; restart."],
        }
    if taxonomy == "pins.quality.insufficient":
        return {
            "change": "Pins quality gate + pins_fixup: enforce pins consistency (allowed vs forbidden) and auto-generate pins patches when insufficient (<=2).",
            "verification": ["Pins-related failure signatures drop by >=80% in 24h window."],
            "rollback": ["Disable pins_fixup env; restart."],
        }
    if taxonomy == "infra.encoding.non_ascii_payload":
        return {
            "change": "UTF-8 transport enforcement for board APIs: always send/accept UTF-8; store build_id; reject invalid JSON payloads; add BOM for md outputs.",
            "verification": ["Create/update tasks with Chinese titles; no mojibake; JSON parse errors disappear."],
            "rollback": ["Fallback to ASCII-only titles (temporary)."],
        }
    if taxonomy == "infra.shell.powershell_syntax":
        return {
            "change": "Command preflight linter: detect '&&' in PowerShell commands and rewrite to ';' (or fail fast with actionable error).",
            "verification": ["Signature powershell_andand_separator failures drop to 0."],
            "rollback": ["Disable linter env flag; restart."],
        }
    if taxonomy == "infra.fs.missing_file":
        return {
            "change": "Path existence preflight: before dispatch, validate pinned paths exist; if not, fail fast + create pins_fixup task instead of executing.",
            "verification": ["Missing-file failures drop; preflight rejects invalid pins in <1s."],
            "rollback": ["Disable preflight env flag; restart."],
        }
    return {
        "change": "Add replay_bundle.json (pins + context files + hashes + env subset) + correlation_id to all logs to make failures reproducible and prevent silent recurrence.",
        "verification": ["Same bundle replay 3x yields same CI result; join across logs works by correlation_id."],
        "rollback": ["Disable bundle writing; restart."],
    }


def five_whys(reason: str, taxonomy: str, enriched: Dict[str, Any]) -> Dict[str, str]:
    direct = f"直接原因：{reason or 'unknown'}"
    mech = ""
    missed_preflight = ""
    missed_autofix = ""
    recurrence = ""

    if taxonomy == "executor.occli.file_instruction_bug":
        mech = "机制原因：occli 被喂入了“按附件文件执行”的元指令，但实际没有对应文件路径/内容，导致立即报 File not found。"
        missed_preflight = "缺失的 preflight：未检测到该元指令/未校验 prompt file 真实存在/未对 occli 输入合同做 schema 校验。"
        missed_autofix = "缺失的 hook/路由：未将该签名失败路由到 pins_fixup/contract_fixup；重试只会重复失败。"
        recurrence = "缺失的回归/lesson：没有对该错误行建立签名回放回归集；升级/改动后无法证明已消除。"
    elif taxonomy == "ci.gate.failed":
        mech = "机制原因：CI gate 要求 exit_code=0，但任务未提供可运行的 tests_run/或改动未被测试覆盖，导致 gate 判失败。"
        missed_preflight = "缺失的 preflight：任务创建/派发阶段未强制 allowedTests；未检查 SUBMIT 证据字段完整。"
        missed_autofix = "缺失的 hook/路由：CI fixup 覆盖不足/未在失败时自动生成补证据子任务并重跑。"
        recurrence = "缺失的回归/lesson：没有把失败用例写入回归集（最小测试/证据），导致相同失败周期性重现。"
    elif taxonomy == "infra.process.timeout":
        mech = "机制原因：单 job 超过超时阈值或被长时间阻塞（例如 split 队列占满并发），导致 timeout。"
        missed_preflight = "缺失的 preflight：缺 phase timings/预算；无法提前识别卡点（install/build/test）并降级或拆分。"
        missed_autofix = "缺失的 hook/路由：超时后未自动切换策略（收紧 pins、缩短上下文、拆分任务、降级验证）"
        recurrence = "缺失的回归/lesson：没有对超时任务类型做固定回放与基准（P95），回归后无法及时发现。"
    elif taxonomy == "pins.quality.insufficient":
        mech = "机制原因：pins 过宽/过窄或自相矛盾（allowed vs forbidden），导致执行器读不到必要文件或读太多失败。"
        missed_preflight = "缺失的 preflight：pins 一致性校验缺失；未验证 pinned paths 存在；未做最小上下文预算。"
        missed_autofix = "缺失的 hook/路由：pins_fixup 未覆盖所有失败原因/未自动生成补 pins 并回填后重试(<=2)。"
        recurrence = "缺失的回归/lesson：缺 pins 模板回归（同类 task_class 的 pins 质量指标），导致反复踩坑。"
    else:
        mech = f"机制原因：taxonomy={taxonomy} 的系统缺口触发了失败（详见 error signature/日志）。"
        missed_preflight = "缺失的 preflight：没有在派发前对输入合同/路径/预算做硬校验。"
        missed_autofix = "缺失的 hook/路由：失败未被路由到对应 fixup（CI/pins/contract/health）而是直接终止或盲重试。"
        recurrence = "缺失的回归/lesson：未建立签名化回放回归集与可回滚规则，导致同类失败再次发生。"

    return {
        "why1_direct": direct,
        "why2_mechanism": mech,
        "why3_missed_preflight": missed_preflight,
        "why4_missed_autofix": missed_autofix,
        "why5_recurrence": recurrence,
    }


def render_md(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Five Whys Report v1")
    lines.append("")
    meta = report.get("meta") or {}
    lines.append(f"- generated_at: `{meta.get('generated_at')}`")
    lines.append(f"- events_tail: `{meta.get('events_tail')}` failures_tail: `{meta.get('failures_tail')}`")
    lines.append(f"- failures_selected: `{meta.get('failures_selected')}`")
    lines.append("")
    lines.append("## Taxonomy Summary")
    lines.append("")
    for row in report.get("taxonomy_summary") or []:
        lines.append(f"- `{row.get('taxonomy')}`: {row.get('count')}")
    lines.append("")
    lines.append("## Five Whys (Per Failure Event)")
    lines.append("")
    for i, it in enumerate(report.get("items") or [], start=1):
        ev = it.get("event") or {}
        lines.append(f"{i}. **{it.get('taxonomy')} | reason={ev.get('reason')} | task_id={ev.get('task_id')}**")
        fw = it.get("five_whys") or {}
        lines.append(f"   - 1) {fw.get('why1_direct')}")
        lines.append(f"   - 2) {fw.get('why2_mechanism')}")
        lines.append(f"   - 3) {fw.get('why3_missed_preflight')}")
        lines.append(f"   - 4) {fw.get('why4_missed_autofix')}")
        lines.append(f"   - 5) {fw.get('why5_recurrence')}")
        pc = it.get("prevention_change") or {}
        lines.append(f"   - 防复发系统改动: {pc.get('change')}")
        ver = pc.get("verification") or []
        if ver:
            lines.append(f"   - 验证: {', '.join(str(x) for x in ver)}")
        rb = pc.get("rollback") or []
        if rb:
            lines.append(f"   - 回滚: {', '.join(str(x) for x in rb)}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exec-log-dir", default=_default_exec_log_dir())
    ap.add_argument("--events-tail", type=int, default=400)
    ap.add_argument("--failures-tail", type=int, default=2000)
    ap.add_argument("--max-items", type=int, default=30)
    args = ap.parse_args()

    log_dir = Path(args.exec_log_dir)
    out_dir = log_dir / "five_whys"
    out_dir.mkdir(parents=True, exist_ok=True)

    events = read_jsonl_tail(log_dir / "state_events.jsonl", args.events_tail)
    failures = read_jsonl_tail(log_dir / "failures.jsonl", args.failures_tail)
    failure_by_task: Dict[str, Dict[str, Any]] = {}
    for f in failures:
        tid = f.get("task_id")
        if tid and tid not in failure_by_task:
            failure_by_task[str(tid)] = f

    # Select recent failures from state_events.
    fail_events = [e for e in reversed(events) if str(e.get("status") or "") == "failed"]
    fail_events = list(reversed(fail_events))[-args.max_items :]

    items: List[Dict[str, Any]] = []
    taxonomy_counts: Dict[str, int] = {}

    for e in fail_events:
        tid = str(e.get("task_id") or "")
        reason = str(e.get("reason") or "unknown")
        f = failure_by_task.get(tid) or {}
        enriched = {
            "failure_reason": f.get("reason"),
            "failure_stderr": f.get("stderrPreview") or f.get("stderr"),
            "failure_stdout": f.get("stdoutPreview") or f.get("stdout"),
            "top_error_line": None,
        }
        taxonomy = classify_taxonomy(reason, enriched)
        taxonomy_counts[taxonomy] = taxonomy_counts.get(taxonomy, 0) + 1

        fw = five_whys(reason, taxonomy, enriched)
        pc = prevention_change_for_taxonomy(taxonomy)

        items.append(
            {
                "taxonomy": taxonomy,
                "event": {
                    "t": e.get("t"),
                    "task_id": e.get("task_id"),
                    "parent_id": e.get("parent_id"),
                    "role": e.get("role"),
                    "area": e.get("area"),
                    "executor": e.get("executor"),
                    "model": e.get("model"),
                    "task_class": e.get("task_class"),
                    "reason": reason,
                    "ci_gate_ok": e.get("ci_gate_ok"),
                    "ci_gate_required": e.get("ci_gate_required"),
                },
                "enrichment": {
                    "failure": {
                        "job_id": f.get("id"),
                        "reason": f.get("reason"),
                        "stderrPreview": f.get("stderrPreview"),
                        "stdoutPreview": f.get("stdoutPreview"),
                        "durationMs": f.get("durationMs"),
                    }
                },
                "five_whys": fw,
                "prevention_change": pc,
            }
        )

    taxonomy_summary = [{"taxonomy": k, "count": v} for k, v in sorted(taxonomy_counts.items(), key=lambda kv: kv[1], reverse=True)]

    report = {
        "version": "v1",
        "meta": {
            "generated_at": iso_now(),
            "events_tail": args.events_tail,
            "failures_tail": args.failures_tail,
            "failures_selected": len(items),
            "paths": {
                "state_events": str(log_dir / "state_events.jsonl"),
                "failures": str(log_dir / "failures.jsonl"),
            },
        },
        "taxonomy_summary": taxonomy_summary,
        "items": items,
    }

    (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    # utf-8-sig to reduce mojibake in Windows viewers
    (out_dir / "report.md").write_text(render_md(report), encoding="utf-8-sig")
    print(str(out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

