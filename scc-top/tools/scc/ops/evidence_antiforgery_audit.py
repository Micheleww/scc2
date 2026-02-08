#!/usr/bin/env python3
from __future__ import annotations

"""
Evidence Anti-Forgery Audit (deterministic, no LLM)

Purpose:
- Enumerate common evidence-chain spoofing vectors.
- Check whether SCC adjudication/CI gate/selftest have machine-verifiable defenses.
- Output an audit report (MD + JSON) for the control plane.

This is intentionally "cheap": it relies on local file inspection and lightweight heuristics.
"""

import argparse
import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


@dataclass
class VectorCheck:
    id: str
    spoof: str
    expected_attack: str
    current_defense: str
    detectable: str  # yes|partial|no
    validator_fix: str
    machine_checks: List[str]


def _has(s: str, needle: str) -> bool:
    return needle in s


def main() -> int:
    ap = argparse.ArgumentParser(description="Evidence anti-forgery audit (deterministic).")
    ap.add_argument("--repo", default=r"C:\scc", help="Repo umbrella root (default: C:\\scc)")
    ap.add_argument("--gateway", default=r"C:\scc\oc-scc-local\src\gateway.mjs")
    ap.add_argument("--gateway_top", default=r"C:\scc\scc-top\tools\oc-scc-local\src\gateway.mjs")
    ap.add_argument("--selftest", default=r"C:\scc\scc-top\tools\scc\ops\task_selftest.py")
    ap.add_argument("--runtime_env", default=r"C:\scc\oc-scc-local\config\runtime.env")
    ap.add_argument("--out_dir", default=r"C:\scc\scc-top\docs\REPORT\control_plane")
    ap.add_argument("--version", default="V010")
    args = ap.parse_args()

    repo = Path(args.repo)
    gw = Path(args.gateway)
    gw2 = Path(args.gateway_top)
    st = Path(args.selftest)
    env = Path(args.runtime_env)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    gw_txt = _read_text(gw)
    gw2_txt = _read_text(gw2)
    st_txt = _read_text(st)
    env_txt = _read_text(env)

    antiforge_env = "CI_ANTIFORGERY_SINCE_MS" in env_txt
    ci_gate_hashes = ("stdoutSha256" in gw_txt and "stderrSha256" in gw_txt) or ("stdoutSha256" in gw2_txt and "stderrSha256" in gw2_txt)
    ci_gate_paths = ("stdoutPath" in gw_txt and "stderrPath" in gw_txt) or ("stdoutPath" in gw2_txt and "stderrPath" in gw2_txt)
    selftest_ci_rows = "ci_gate_results.jsonl" in st_txt and "missing CI gate evidence" in st_txt
    selftest_mtime = "mtime_outside_job_window" in st_txt and "startedAt" in st_txt and "finishedAt" in st_txt

    vectors: List[VectorCheck] = []

    def add(v: VectorCheck) -> None:
        vectors.append(v)

    # 1) Report-only success (no CI)
    add(
        VectorCheck(
            id="spoof_report_only",
            spoof="写一份漂亮 report，声称 CI/selftest 通过，但实际上根本没跑",
            expected_attack="交付物只包含 prose/报告；证据链无法复核；裁决者被说服",
            current_defense="CI gate + task_selftest（严格模式）应 fail-closed；新增 anti-forgery 要求 CI 记录/哈希/日志文件存在",
            detectable="yes" if (selftest_ci_rows and ci_gate_hashes and ci_gate_paths) else "partial",
            validator_fix="强制：ci_gate_results.jsonl 必须有 job_id 对应记录，且 ran=true exitCode=0；同时 stdout/stderr 全量日志落盘并校验 sha256。",
            machine_checks=[
                "ci_gate_results.jsonl: job_id match lastJobId",
                "ci_gate_results.jsonl: ran=true ok=true exitCode=0",
                "ci_gate_results.jsonl: stdoutPath/stderrPath exist",
                "sha256(stdout/stderr) matches recorded hashes",
            ],
        )
    )

    # 2) Lie in SUBMIT.tests_run
    add(
        VectorCheck(
            id="spoof_submit_tests",
            spoof="CI 实际没跑或失败，但在 SUBMIT.tests_run 里谎报“通过/已运行”",
            expected_attack="SUBMIT 看起来合规；但没真实执行/失败被掩盖",
            current_defense="裁决以 CI gate 结果为准，不信 SUBMIT 口头；anti-forgery 自测要求 CI 证据",
            detectable="yes" if selftest_ci_rows else "partial",
            validator_fix="task_selftest 强制校验 CI gate evidence（并交叉校验命令/exitCode/日志 hash）。",
            machine_checks=[
                "Ignore SUBMIT.tests_run for pass/fail; use CI gate evidence",
            ],
        )
    )

    # 3) Spoof SUBMIT.touched_files
    add(
        VectorCheck(
            id="spoof_touched_files",
            spoof="SUBMIT.touched_files 伪造：声称改了文件但磁盘上没改/改了别的",
            expected_attack="欺骗审计：看起来触达了文件，但实际无改动或越权改动",
            current_defense="task_selftest: touched_files 必须在 pins/files allowlist 内；禁止 forbidden_paths；新增 mtime 窗口交叉校验",
            detectable="yes" if selftest_mtime else "partial",
            validator_fix="对 touched_files 做 on-disk existence + mtime 窗口校验；必要时加文件 hash snapshot。",
            machine_checks=[
                "touched_files within allowed_paths prefix allowlist",
                "touched_files not under forbidden_paths",
                "touched_files exist on disk",
                "mtime within [job.startedAt - slack, job.finishedAt + slack]",
            ],
        )
    )

    # 4) Fake diff in stdout
    add(
        VectorCheck(
            id="spoof_stdout_patch",
            spoof="stdout 里贴 diff，看起来改了，但实际没落盘或落盘不一致",
            expected_attack="patch_stats 通过 stdout 推断，无法证明文件真实变化",
            current_defense="部分由 touched_files mtime 校验兜底（如果 SUBMIT 真实且 antiforge 启用）",
            detectable="partial",
            validator_fix="增加“工作区真实变更证据”：对 touched_files 做内容 hash snapshot，或在 runner 侧保存 git diff/文件快照（只限 allowlist）。",
            machine_checks=[
                "Require SUBMIT.touched_files for code-touch roles",
                "Verify touched_files mtimes",
                "Optional: record sha256(before/after) for touched_files",
            ],
        )
    )

    # 5) Minimal test deception
    add(
        VectorCheck(
            id="spoof_minimal_tests",
            spoof="只跑 task_selftest 这类“永远通过”的最小测试，实际功能没验证",
            expected_attack="避开真实回归；引入隐藏 bug",
            current_defense="task_selftest: engineer/integrator 触碰非 doc 文件时 tests_run 不能只有 task_selftest",
            detectable="yes" if _has(st_txt, "insufficient tests_run evidence") else "partial",
            validator_fix="把 task_class 最小回归命令固化为 allowlist_tests；CI gate 必须跑 task_class 回归。",
            machine_checks=[
                "If non-doc touched: tests_run must include at least one non-selftest command",
            ],
        )
    )

    # 6) Missing evidence pack
    add(
        VectorCheck(
            id="spoof_missing_artifacts",
            spoof="缺失关键证据文件/路径：只有结论，没有 stdout/stderr、没有命令、没有 touched_files",
            expected_attack="无法裁决但被当做 done",
            current_defense="strict 模式下 task_selftest 强制 SUBMIT + CI evidence；缺失直接失败",
            detectable="yes" if selftest_ci_rows else "partial",
            validator_fix="fail-closed：缺失 SUBMIT 或 CI evidence 直接 FAIL；并自动生成 QA fixup。",
            machine_checks=[
                "Require SUBMIT contract for most roles",
                "Require CI evidence for antiforge-on tasks",
            ],
        )
    )

    # 7) Post-hoc tamper
    add(
        VectorCheck(
            id="spoof_tamper_after",
            spoof="事后篡改 ci_gate_results.jsonl 或 CI 日志文件，再改 hash 伪装一致",
            expected_attack="有磁盘写权限的对手可同时改记录+日志，绕过单点 hash 校验",
            current_defense="当前仅做 hash 一致性；不防“同改记录+日志”的强对手",
            detectable="no",
            validator_fix="为 ci_gate_results.jsonl 加 hash 链（prev_hash -> row_hash）或写入只追加介质/只读权限；或把结果上报到不可变日志（append-only store）。",
            machine_checks=[
                "Hash chain over ci_gate_results.jsonl rows",
                "Lock down artifacts/executor_logs/ci_gate directory ACL to append-only",
            ],
        )
    )

    # 8) Reuse old evidence
    add(
        VectorCheck(
            id="spoof_reuse_old",
            spoof="复用旧 job 的 CI 通过日志/证据，冒充当前 job",
            expected_attack="拿别人通过的证据包，骗过裁决",
            current_defense="task_selftest 以 lastJobId 精确匹配 ci_gate_results.jsonl job_id",
            detectable="yes" if selftest_ci_rows else "partial",
            validator_fix="CI evidence 必须绑定 job_id/task_id，并在裁决时强制一致性。",
            machine_checks=[
                "ci_gate_results.jsonl job_id == task.lastJobId",
                "ci_gate_results.jsonl task_id == task.id (optional strengthen)",
            ],
        )
    )

    # 9) Wrong CI command
    add(
        VectorCheck(
            id="spoof_wrong_ci_cmd",
            spoof="跑了 CI，但不是声明的 allowedTests（偷换成永远 exit 0 的命令）",
            expected_attack="exit_code=0 但没有真实验证价值",
            current_defense="gateway: CI 命令有 allowlist 前缀；CI_GATE_ALLOW_ALL=false 默认阻止任意命令",
            detectable="partial",
            validator_fix="把 task_class 的最小回归命令绑定为 allowlist_tests；CI gate 记录 command 并审计必须匹配模板。",
            machine_checks=[
                "CI command must match allowlist prefixes",
                "CI command should match task_class template",
            ],
        )
    )

    # 10) Success narrative mismatch
    add(
        VectorCheck(
            id="spoof_narrative_mismatch",
            spoof="报告/审计结论与实际改动不一致（说修了但没触达关键文件/符号）",
            expected_attack="靠叙事蒙混过关；功能风险留存",
            current_defense="半径审计 + touched_files allowlist 能挡住一部分；但对“必须触达哪些点”缺少硬校验",
            detectable="partial",
            validator_fix="在 task_class 中声明 must_touch_paths/must_touch_symbols，并在 selftest/validator 中做静态检查；对关键文件变化做 hash snapshot。",
            machine_checks=[
                "must_touch_paths subset of touched_files",
                "optional: must_touch_symbols present in diff",
            ],
        )
    )

    out = {
        "generated_at_utc": _utc_now(),
        "version": str(args.version),
        "signals": {
            "CI_ANTIFORGERY_SINCE_MS_in_env": bool(antiforge_env),
            "ci_gate_persists_hashes": bool(ci_gate_hashes),
            "ci_gate_persists_paths": bool(ci_gate_paths),
            "selftest_requires_ci_evidence": bool(selftest_ci_rows),
            "selftest_mtime_window_check": bool(selftest_mtime),
        },
        "vectors": [asdict(v) for v in vectors],
        "summary": {
            "total": len(vectors),
            "detectable_yes": sum(1 for v in vectors if v.detectable == "yes"),
            "detectable_partial": sum(1 for v in vectors if v.detectable == "partial"),
            "detectable_no": sum(1 for v in vectors if v.detectable == "no"),
            "top_gaps": [v.id for v in vectors if v.detectable == "no"][:5],
        },
    }

    stamp = _stamp()
    md_path = out_dir / f"REPORT__EVIDENCE_ANTIFORGERY_AUDIT__{args.version}__{stamp}.md"
    json_path = out_dir / f"REPORT__EVIDENCE_ANTIFORGERY_AUDIT__{args.version}__{stamp}.json"

    lines: List[str] = []
    lines.append(f"# Evidence Anti-Forgery Audit {args.version}")
    lines.append("")
    lines.append(f"Generated at (UTC): `{out['generated_at_utc']}`")
    lines.append("")
    lines.append("## Signals")
    for k, v in out["signals"].items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")
    lines.append("## Spoofing Vectors")
    for v in vectors:
        lines.append(f"### {v.id}")
        lines.append(f"- Spoof: {v.spoof}")
        lines.append(f"- Attack: {v.expected_attack}")
        lines.append(f"- Detectable now: `{v.detectable}`")
        lines.append(f"- Current defense: {v.current_defense}")
        lines.append(f"- Validator fix: {v.validator_fix}")
        lines.append("- Machine checks:")
        for c in v.machine_checks:
            lines.append(f"  - `{c}`")
        lines.append("")
    lines.append("## Summary")
    lines.append(f"- total: `{out['summary']['total']}`")
    lines.append(f"- detectable_yes: `{out['summary']['detectable_yes']}`")
    lines.append(f"- detectable_partial: `{out['summary']['detectable_partial']}`")
    lines.append(f"- detectable_no: `{out['summary']['detectable_no']}`")
    lines.append(f"- top_gaps: `{', '.join(out['summary']['top_gaps']) or '(none)'}`")
    lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    json_path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(str(md_path))
    print(str(json_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

