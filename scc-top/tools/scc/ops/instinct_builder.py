#!/usr/bin/env python3
"""
Instinct Builder (v1)

Goal:
- Read failures.jsonl (+ jobs.jsonl for usage) from SCC executor logs
- Cluster failures into "patterns"
- Emit:
  - patterns.json (machine-readable snapshot)
  - playbooks.yaml (rollback-safe remediation templates)
  - skills_draft.yaml (draft skills that are verifiable + rollable)
  - schemas.yaml (YAML schema description)

No external deps. Designed to run offline or via hooks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


def _default_repo_root() -> Path:
    # scc-top/tools/scc/ops/*.py -> repo root is 4 levels up
    return Path(os.environ.get("SCC_REPO_ROOT") or Path(__file__).resolve().parents[4]).resolve()


def _default_exec_log_dir() -> str:
    return os.environ.get("EXEC_LOG_DIR") or str(_default_repo_root() / "artifacts" / "executor_logs")


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_jsonl_tail(path: Path, limit: int) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    if limit > 0:
        lines = lines[-limit:]
    out = []
    for ln in lines:
        try:
            obj = json.loads(ln)
        except Exception:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def sha1_hex(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8", errors="ignore")).hexdigest()


def norm_sig(s: str) -> str:
    s = s or ""
    s = re.sub(r"[A-Z]:[\\/][^\s\"']+", "<PATH>", s, flags=re.I)
    s = re.sub(r"https?://\S+", "<URL>", s, flags=re.I)
    s = re.sub(r"\b\d+\b", "<N>", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s[:2000]


def classify_taxonomy(reason: str, stderr: str, stdout: str) -> str:
    msg = norm_sig(" ".join([reason, stderr, stdout]))
    if "&&" in msg and "not a valid statement separator" in msg:
        return "infra.shell.powershell_syntax"
    if "file not found" in msg or "no such file" in msg or "enotfound" in msg:
        return "infra.fs.missing_file"
    if "missing_submit_contract" in msg or "submit" in msg:
        return "executor.contract.submit"
    if reason == "timeout":
        return "infra.process.timeout"
    if "rate limit" in msg or "too many requests" in msg:
        return "model.throttle.rate_limited"
    if "unauthorized" in msg or "401" in msg:
        return "model.auth.unauthorized"
    if "ci_gate" in msg or "ci_failed" in msg or reason.startswith("ci"):
        return "ci.gate.failed"
    if "pins" in msg or "pins_apply_failed" in msg:
        return "pins.quality.insufficient"
    return "unknown"


def extract_signature(reason: str, stderr: str, stdout: str, executor: str) -> str:
    msg = "\n".join([stderr or "", stdout or ""])
    s = norm_sig(msg)
    if "&&" in s and "not a valid statement separator" in s:
        return "powershell_andand_separator"
    if "file not found: follow the attached file" in s:
        return "occli_file_not_found_attached_file"
    if "missing_submit_contract" in s:
        return "missing_submit_contract"
    if "buninstallfailederror" in s:
        return "occli_bun_install_failed"
    if "show help" in s and executor == "opencodecli":
        return "occli_wrong_subcommand"
    if reason == "timeout":
        return "timeout"
    lines = [ln.strip() for ln in msg.splitlines() if ln.strip()]
    for ln in lines:
        if re.match(r"^error[: ]", ln, flags=re.I):
            return norm_sig(ln)[:160]
    for ln in lines:
        low = ln.lower()
        if "exception" in low or "traceback" in low or "failed" in low:
            return norm_sig(ln)[:160]
    return "unknown"


def yaml_quote(s: Any) -> str:
    if s is None:
        return "null"
    if isinstance(s, bool):
        return "true" if s else "false"
    if isinstance(s, (int, float)):
        return str(s)
    txt = str(s)
    txt = txt.replace("\\", "\\\\").replace('"', '\\"')
    return f"\"{txt}\""


def to_yaml(v: Any, indent: int = 0) -> str:
    pad = " " * indent
    if v is None or isinstance(v, (bool, int, float, str)):
        return yaml_quote(v)
    if isinstance(v, list):
        if not v:
            return "[]"
        lines: List[str] = []
        for it in v:
            if isinstance(it, (dict, list)):
                lines.append(f"{pad}- {to_yaml(it, indent + 2).lstrip()}")
            else:
                lines.append(f"{pad}- {to_yaml(it, 0)}")
        return "\n".join(lines)
    if isinstance(v, dict):
        if not v:
            return "{}"
        lines = []
        for k, it in v.items():
            if isinstance(it, (dict, list)):
                lines.append(f"{pad}{k}:\n{to_yaml(it, indent + 2)}")
            else:
                lines.append(f"{pad}{k}: {to_yaml(it, 0)}")
        return "\n".join(lines)
    return yaml_quote(str(v))


@dataclass
class PatternAgg:
    taxonomy: str
    reason: str
    signature: str
    role: str
    task_class: str
    executor: str
    count: int = 0
    total_dur_ms: int = 0
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    sample_task_ids: List[str] = None
    sample_job_ids: List[str] = None
    sigs: set = None
    usage_sum: Dict[str, int] = None
    usage_n: int = 0

    def __post_init__(self) -> None:
        self.sample_task_ids = self.sample_task_ids or []
        self.sample_job_ids = self.sample_job_ids or []
        self.sigs = self.sigs or set()
        self.usage_sum = self.usage_sum or {"input_tokens": 0, "output_tokens": 0, "cached_input_tokens": 0}

    def add(self, f: Dict[str, Any], usage: Optional[Dict[str, Any]]) -> None:
        self.count += 1
        self.total_dur_ms += int(f.get("durationMs") or 0)
        t = f.get("t")
        if not self.first_seen:
            self.first_seen = t
        self.last_seen = t or self.last_seen
        tid = f.get("task_id")
        jid = f.get("id")
        if tid and len(self.sample_task_ids) < 8:
            self.sample_task_ids.append(str(tid))
        if jid and len(self.sample_job_ids) < 8:
            self.sample_job_ids.append(str(jid))
        self.sigs.add(self.signature)
        if usage and isinstance(usage, dict):
            for k in ("input_tokens", "output_tokens", "cached_input_tokens"):
                self.usage_sum[k] += int(usage.get(k) or 0)
            self.usage_n += 1

    def to_obj(self) -> Dict[str, Any]:
        ck = {
            "taxonomy": self.taxonomy,
            "reason": self.reason,
            "signature": self.signature,
            "role": self.role,
            "task_class": self.task_class,
            "executor": self.executor,
        }
        pid = sha1_hex("|".join([self.taxonomy, self.reason, self.signature, self.role, self.task_class, self.executor]))
        usage_avgs = None
        if self.usage_n > 0:
            usage_avgs = {k: int(self.usage_sum[k] / self.usage_n) for k in self.usage_sum.keys()}
        avg_dur = int(self.total_dur_ms / self.count) if self.count else 0
        return {
            "id": pid,
            "taxonomy": self.taxonomy,
            "cluster_key": ck,
            "count": self.count,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "avg_duration_ms": avg_dur,
            "usage_avgs": usage_avgs,
            "sample_task_ids": self.sample_task_ids,
            "sample_job_ids": self.sample_job_ids,
            "signatures": sorted(list(self.sigs))[:12],
        }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exec-log-dir", default=_default_exec_log_dir())
    ap.add_argument("--failures-tail", type=int, default=2000)
    ap.add_argument("--jobs-tail", type=int, default=4000)
    ap.add_argument("--out-dir", default="")
    args = ap.parse_args()

    log_dir = Path(args.exec_log_dir)
    failures_file = log_dir / "failures.jsonl"
    jobs_file = log_dir / "jobs.jsonl"
    out_dir = Path(args.out_dir) if args.out_dir else (log_dir / "instinct")
    out_dir.mkdir(parents=True, exist_ok=True)

    failures = read_jsonl_tail(failures_file, args.failures_tail)
    jobs = read_jsonl_tail(jobs_file, args.jobs_tail)
    usage_by_job: Dict[str, Dict[str, Any]] = {}
    for j in jobs:
        jid = j.get("id")
        u = j.get("usage")
        if jid and isinstance(u, dict):
            usage_by_job[str(jid)] = u

    patterns: Dict[str, PatternAgg] = {}
    for f in failures:
        reason = str(f.get("reason") or "unknown")
        stderr = str(f.get("stderrPreview") or f.get("stderr") or "")
        stdout = str(f.get("stdoutPreview") or f.get("stdout") or "")
        role = str(f.get("role") or "unknown")
        task_class = str(f.get("task_class") or f.get("taskClass") or "none")
        executor = str(f.get("executor") or "unknown")

        taxonomy = classify_taxonomy(reason, stderr, stdout)
        signature = extract_signature(reason, stderr, stdout, executor)

        key = "|".join([taxonomy, reason, signature, role, task_class, executor])
        pid = sha1_hex(key)
        agg = patterns.get(pid)
        if not agg:
            agg = PatternAgg(taxonomy=taxonomy, reason=reason, signature=signature, role=role, task_class=task_class, executor=executor)
            patterns[pid] = agg
        agg.add(f, usage_by_job.get(str(f.get("id") or "")))

    out_patterns = [agg.to_obj() for agg in patterns.values()]
    out_patterns.sort(key=lambda p: (-(p["count"] * (p["avg_duration_ms"] + 1))), reverse=False)
    out_patterns = sorted(out_patterns, key=lambda p: p["count"] * (p["avg_duration_ms"] + 1), reverse=True)

    taxonomy_counts: Dict[str, int] = {}
    for p in out_patterns:
        taxonomy_counts[p["taxonomy"]] = taxonomy_counts.get(p["taxonomy"], 0) + int(p["count"])
    taxonomy = [{"taxonomy": k, "count": v} for k, v in sorted(taxonomy_counts.items(), key=lambda kv: kv[1], reverse=True)]

    snapshot = {
        "t": iso_now(),
        "window": {
            "failures_tail": args.failures_tail,
            "jobs_tail": args.jobs_tail,
            "failures": len(failures),
            "patterns": len(out_patterns),
        },
        "taxonomy": taxonomy,
        "clustering_keys": [
            "taxonomy",
            "reason",
            "signature",
            "role",
            "task_class",
            "executor",
        ],
        "patterns": out_patterns[:200],
    }

    (out_dir / "patterns.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

    schemas = {
        "version": "v1",
        "pattern_schema": {
            "id": "sha1(cluster_key)",
            "taxonomy": "string",
            "cluster_key": {
                "taxonomy": "string",
                "reason": "string",
                "signature": "string",
                "role": "string",
                "task_class": "string",
                "executor": "string",
            },
            "count": "int",
            "first_seen": "iso8601|null",
            "last_seen": "iso8601|null",
            "avg_duration_ms": "int",
            "usage_avgs": "object|null",
            "sample_task_ids": ["uuid"],
            "sample_job_ids": ["uuid"],
            "signatures": ["string"],
        },
        "playbook_schema": {
            "id": "string",
            "enabled_flag": "ENV var name; default false-safe",
            "trigger": {"taxonomy": "string", "reason": "string", "signature_contains": "string|null", "min_count": "int"},
            "observation": {"metrics": ["string"], "files": ["path"], "endpoint_hints": ["string"]},
            "remediation": {"actions": ["string"], "minimal_change_points": ["string"]},
            "verification": {"replay": ["command"], "expected": "exit_code=0 and evidence present"},
            "rollback": {"steps": ["string"]},
        },
        "skills_draft_schema": {
            "name": "string",
            "version": "string",
            "trigger_patterns": ["pattern_id"],
            "instructions": ["string"],
            "verification": {"replay": ["command"], "expected": "exit_code=0"},
            "rollout": {"enabled_flag": "ENV var name"},
            "rollback": {"steps": ["string"]},
        },
    }
    (out_dir / "schemas.yaml").write_text(to_yaml(schemas) + "\n", encoding="utf-8")

    # Top 12 playbooks (templates)
    playbooks = []
    for p in snapshot["patterns"][:12]:
        ck = p.get("cluster_key") or {}
        pid = str(p.get("id") or "")
        playbooks.append(
            {
                "id": f"playbook__{pid[:12]}__v1",
                "enabled_flag": f"PLAYBOOK_{pid[:12].upper()}_ENABLED",
                "trigger": {
                    "taxonomy": str(ck.get("taxonomy") or p.get("taxonomy") or "unknown"),
                    "reason": str(ck.get("reason") or "unknown"),
                    "signature_contains": str(ck.get("signature") or "")[:64] or "unknown",
                    "min_count": min(5, max(2, int(p.get("count") or 2))),
                },
                "observation": {
                    "metrics": ["failures.count", "avg_duration_ms", "usage_avgs.input_tokens"],
                    "files": [str(failures_file), str(jobs_file), str(log_dir / "state_events.jsonl")],
                    "endpoint_hints": ["/executor/debug/failures", "/executor/debug/summary", "/replay/task?task_id=..."],
                },
                "remediation": {
                    "actions": [
                        "Create a factory_manager task: find root cause -> minimal patch -> add replay/selftest evidence.",
                        "If pins/contract issue: fix pins or tighten allowlist, then retry (<=2). Avoid fixup storms.",
                    ],
                    "minimal_change_points": [
                        "gateway: preflight/contract checks",
                        "task_selftest.py: strengthen evidence requirements",
                        "pins templates: tighten files/window",
                    ],
                },
                "verification": {
                    "replay": [
                        f'powershell -ExecutionPolicy Bypass -Command "Invoke-RestMethod http://127.0.0.1:18788/replay/task?task_id={(p.get("sample_task_ids") or ["..."])[0]}"',
                        f'python scc-top/tools/scc/ops/task_selftest.py --task-id {(p.get("sample_task_ids") or ["..."])[0]}',
                    ],
                    "expected": "exit_code=0 AND SUBMIT(touched_files/tests_run) present for new tasks",
                },
                "rollback": {
                    "steps": [
                        "Set enabled_flag=false and restart the daemon.",
                        "If regression: revert the minimal patch or tighten trigger conditions.",
                    ]
                },
            }
        )
    (out_dir / "playbooks.yaml").write_text(to_yaml({"version": "v1", "generated_at": iso_now(), "playbooks": playbooks}) + "\n", encoding="utf-8")

    skills_draft = []
    for p in snapshot["patterns"][:6]:
        pid = str(p.get("id") or "")
        skills_draft.append(
            {
                "name": f"skill__auto__{str(p.get('taxonomy') or 'unknown').replace('.', '_')}__v1",
                "version": "v1",
                "trigger_patterns": [pid],
                "instructions": [
                    "Use /replay/task to reproduce and pin down the minimal trigger conditions.",
                    "Produce the minimal patch (touch only necessary files) and write verification commands into SUBMIT.tests_run.",
                    "If pins are insufficient: output a pins patch + replayable evidence; do not expand context blindly.",
                ],
                "verification": {
                    "replay": [
                        f'powershell -ExecutionPolicy Bypass -Command "Invoke-RestMethod http://127.0.0.1:18788/replay/task?task_id={(p.get("sample_task_ids") or ["..."])[0]}"'
                    ],
                    "expected": "replay->ci gate exit_code=0",
                },
                "rollout": {"enabled_flag": f"SKILL_{pid[:12].upper()}_ENABLED"},
                "rollback": {"steps": ["关闭 enabled_flag 并重启", "回滚技能文件/规则文件"]},
            }
        )
    (out_dir / "skills_draft.yaml").write_text(to_yaml({"version": "v1", "generated_at": iso_now(), "skills_draft": skills_draft}) + "\n", encoding="utf-8")

    print(str(out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
