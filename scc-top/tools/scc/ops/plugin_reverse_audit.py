#!/usr/bin/env python3
"""
Protocol / Pluginability Reverse Audit (v1)

Assume we are a 3rd-party developer trying to ship a plugin package
(commands/agents/skills/rules/hooks/eval).

This script generates:
- artifacts/executor_logs/plugin_reverse/report.md
- artifacts/executor_logs/plugin_reverse/report.json

It focuses on "what is unstable/unclear today" and what must be hardened:
- schemas to freeze
- protocol versioning
- lifecycle hooks
- minimal plugin skeleton (files + manifest) to copy/paste
"""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _default_repo_root() -> Path:
    # scc-top/tools/scc/ops/*.py -> repo root is 4 levels up
    return Path(os.environ.get("SCC_REPO_ROOT") or Path(__file__).resolve().parents[4]).resolve()


def _default_exec_log_dir() -> str:
    return os.environ.get("EXEC_LOG_DIR") or str(_default_repo_root() / "artifacts" / "executor_logs")


def _default_gateway_file() -> str:
    return str(_default_repo_root() / "oc-scc-local" / "src" / "gateway.mjs")


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def read_json(path: Path) -> Optional[Any]:
    try:
        return json.loads(read_text(path) or "null")
    except Exception:
        return None


def extract_routes_from_gateway(src: str) -> List[str]:
    # Best-effort: parse occurrences of `pathname === "/xxx"` literals.
    routes = set()
    for m in re.finditer(r'pathname\s*===\s*"(/[^"]+)"', src):
        routes.add(m.group(1))
    return sorted(routes)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exec-log-dir", default=_default_exec_log_dir())
    ap.add_argument("--gateway-file", default=_default_gateway_file())
    args = ap.parse_args()

    exec_log_dir = Path(args.exec_log_dir)
    out_dir = exec_log_dir / "plugin_reverse"
    out_dir.mkdir(parents=True, exist_ok=True)

    gw_path = Path(args.gateway_file)
    gw_src = read_text(gw_path)
    routes = extract_routes_from_gateway(gw_src)

    # Observed pain points (grounded in current repo patterns).
    unstable: List[Dict[str, Any]] = [
        {
            "area": "contracts",
            "issue": "SUBMIT 协议未版本化，字段语义依赖解析器启发式（submit/touched_files/tests_run 等）。",
            "breaks_plugin": "插件无法可靠判定任务是否可裁决/是否满足证据门槛；不同 executor 输出差异会导致插件误判。",
            "needs_schema": ["SubmitContractV1"],
            "needs_versioning": ["submit.schema_version", "submit.contract_id"],
        },
        {
            "area": "pins",
            "issue": "pins 结构缺少正式 schema；allowed_paths/forbidden_paths 的匹配语义历史上不一致（精确 vs 前缀）。",
            "breaks_plugin": "插件无法安全做半径/权限判断；会出现 allowed 与 forbidden 冲突导致不可预测行为。",
            "needs_schema": ["PinsV1"],
            "needs_versioning": ["pins.schema_version"],
        },
        {
            "area": "events/logging",
            "issue": "leader/state_events/failures 等事件类型未 schema 化、未稳定版本；字段随代码演进漂移。",
            "breaks_plugin": "插件订阅事件无法写可靠解析器；无法做回放/回归。",
            "needs_schema": ["LeaderEventV1", "StateEventV1", "FailureRecordV1"],
            "needs_versioning": ["event.schema_version", "event.type registry"],
        },
        {
            "area": "jobs",
            "issue": "jobs.jsonl / jobs_state.json 与内存对象字段不完全一致；taskId 可能为空（如 board_split）。",
            "breaks_plugin": "插件无法稳定关联 job->task，导致统计/调度/修复策略不可预测。",
            "needs_schema": ["JobRecordV1"],
            "needs_versioning": ["job.schema_version"],
        },
        {
            "area": "config",
            "issue": "runtime.env 变更需要重启才生效，但系统缺少 build_id/git_sha 暴露与版本一致性校验。",
            "breaks_plugin": "插件无法判断某个 hook 是否真正启用；会出现接口 404/行为不一致。",
            "needs_schema": ["RuntimeConfigV1"],
            "needs_versioning": ["/health build_id", "config schema registry version"],
        },
        {
            "area": "lifecycle",
            "issue": "缺少正式插件生命周期钩子（on_startup/on_shutdown/on_tick/before_dispatch/after_job/after_ci 等）。",
            "breaks_plugin": "第三方只能改主程序或靠外部轮询，无法可控接入。",
            "needs_schema": ["PluginHookEventV1", "PluginContextV1"],
            "needs_versioning": ["hook API v1"],
        },
        {
            "area": "safety/radius",
            "issue": "范围控制/证据门槛/重试预算等 guardrail 分散在网关与脚本中，缺少统一 policy schema。",
            "breaks_plugin": "插件无法可靠扩展 policy（比如自定义 fail-closed）且难回滚。",
            "needs_schema": ["PolicyPackV1"],
            "needs_versioning": ["policy.schema_version"],
        },
    ]

    fields_to_freeze = [
        {"schema": "SubmitContractV1", "fields": ["schema_version", "status", "reason_code", "touched_files[]", "tests_run[]", "deps_added[]", "artifacts[]"]},
        {"schema": "PinsV1", "fields": ["schema_version", "allowed_paths[]", "forbidden_paths[]", "symbols[]", "line_windows{}", "max_files", "max_loc", "ssot_assumptions[]"]},
        {"schema": "BoardTaskV1", "fields": ["id", "kind", "status", "role", "goal", "files[]", "pins", "allowedTests[]", "allowedExecutors[]", "allowedModels[]", "runner", "timeoutMs", "createdAt", "updatedAt", "lastJobId"]},
        {"schema": "JobRecordV1", "fields": ["id", "taskId", "taskType", "executor", "model", "status", "createdAt", "startedAt", "finishedAt", "exit_code", "reason", "usage", "patch_stats", "submit"]},
        {"schema": "StateEventV1", "fields": ["t", "task_id", "kind", "status", "role", "area", "task_class", "durationMs", "touched_files", "tests_run", "ci_gate_ok", "reason"]},
        {"schema": "LeaderEventV1", "fields": ["t", "level", "type", "id", "task_id", "job_id", "reason", "details"]},
        {"schema": "PluginManifestV1", "fields": ["schema_version", "id", "name", "version", "requires", "hooks[]", "commands[]", "evals[]"]},
    ]

    protocol_versioning = [
        {"protocol": "SUBMIT", "version_field": "submit.schema_version", "compat": "old versions must remain parseable or be fail-closed"},
        {"protocol": "PINS", "version_field": "pins.schema_version", "compat": "matching semantics (prefix vs exact) must be frozen"},
        {"protocol": "EVENTS", "version_field": "event.schema_version", "compat": "event type registry must be stable"},
        {"protocol": "PLUGIN_API", "version_field": "plugin_api_version", "compat": "hook payloads must be backwards compatible"},
    ]

    lifecycle_hooks = [
        {"hook": "on_startup", "when": "gateway start", "payload": ["build_id", "runtime_env", "capabilities"]},
        {"hook": "on_shutdown", "when": "gateway stop", "payload": ["reason"]},
        {"hook": "on_tick", "when": "periodic", "payload": ["time", "counters"]},
        {"hook": "before_dispatch", "when": "task->job dispatch", "payload": ["task", "contract", "pins", "policy"]},
        {"hook": "after_dispatch", "when": "job created", "payload": ["job", "task"]},
        {"hook": "after_job_finished", "when": "job finished", "payload": ["job", "task", "ci_gate"]},
        {"hook": "after_ci_gate", "when": "ci result", "payload": ["task_id", "ok", "command", "exit_code"]},
        {"hook": "on_failure_record", "when": "failure appended", "payload": ["failure", "classification"]},
        {"hook": "on_state_event", "when": "state_events appended", "payload": ["event"]},
    ]

    minimal_plugin_skeleton = {
        "files": [
            {
                "path": "scc-top/tools/scc/plugins/example-plugin/plugin.json",
                "content": json.dumps(
                    {
                        "schema_version": "plugin_manifest_v1",
                        "id": "example.echo",
                        "name": "Example Echo Plugin",
                        "version": "0.1.0",
                        "requires": {"plugin_api": "v1"},
                        "hooks": [
                            {"type": "after_job_finished", "enabled": True},
                            {"type": "on_state_event", "enabled": False},
                        ],
                        "commands": [{"id": "echo", "description": "Echo a message via leader log"}],
                        "evals": [],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            },
            {
                "path": "scc-top/tools/scc/plugins/example-plugin/index.mjs",
                "content": "\n".join(
                    [
                        "// Minimal plugin skeleton (v1).",
                        "// Host must provide ctx: { leader(event), createTask(payload), dispatch(taskId), readJson(path), writeJson(path,obj) }",
                        "",
                        "export function register(ctx) {",
                        "  return {",
                        "    id: 'example.echo',",
                        "    plugin_api: 'v1',",
                        "    hooks: {",
                        "      after_job_finished: async (ev) => {",
                        "        // Fail-closed behavior: do nothing if fields are missing.",
                        "        if (!ev || !ev.job || !ev.task) return",
                        "        ctx.leader({ level: 'info', type: 'plugin_example_echo', task_id: ev.task.id, job_id: ev.job.id })",
                        "      },",
                        "    },",
                        "    commands: {",
                        "      echo: async ({ message }) => {",
                        "        ctx.leader({ level: 'info', type: 'plugin_command_echo', message: String(message ?? '') })",
                        "        return { ok: true }",
                        "      },",
                        "    },",
                        "  }",
                        "}",
                        "",
                    ]
                ),
            },
        ]
    }

    report = {
        "version": "v1",
        "generated_at": iso_now(),
        "gateway_file": str(gw_path),
        "observed_routes_count": len(routes),
        "observed_routes_sample": routes[:80],
        "unstable_or_unclear": unstable,
        "schemas_to_freeze": fields_to_freeze,
        "protocols_to_version": protocol_versioning,
        "required_lifecycle_hooks": lifecycle_hooks,
        "minimal_plugin_skeleton": minimal_plugin_skeleton,
        "recommended_next_step": "Add a plugin loader that reads plugins/*/plugin.json + index.mjs, validates schema_version/plugin_api, registers hooks, and supports enable/disable + rollback flags.",
    }

    (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    md: List[str] = []
    md.append("# Protocol / Pluginability Reverse Audit v1")
    md.append("")
    md.append(f"- generated_at: `{report['generated_at']}`")
    md.append(f"- gateway_file: `{report['gateway_file']}`")
    md.append(f"- observed_routes_count: `{report['observed_routes_count']}`")
    md.append("")
    md.append("## Unstable Or Unclear Interfaces")
    md.append("")
    for item in unstable:
        md.append(f"- **{item['area']}**: {item['issue']}")
        md.append(f"  - breaks_plugin: {item['breaks_plugin']}")
        md.append(f"  - needs_schema: {', '.join(item['needs_schema'])}")
        md.append(f"  - needs_versioning: {', '.join(item['needs_versioning'])}")
    md.append("")
    md.append("## Schemas To Freeze")
    md.append("")
    for s in fields_to_freeze:
        md.append(f"- **{s['schema']}**: {', '.join(s['fields'])}")
    md.append("")
    md.append("## Protocol Versioning")
    md.append("")
    for p in protocol_versioning:
        md.append(f"- **{p['protocol']}**: version_field=`{p['version_field']}` compat=`{p['compat']}`")
    md.append("")
    md.append("## Lifecycle Hooks To Provide")
    md.append("")
    for h in lifecycle_hooks:
        md.append(f"- **{h['hook']}** when={h['when']} payload={', '.join(h['payload'])}")
    md.append("")
    md.append("## Minimal Plugin Skeleton")
    md.append("")
    for f in minimal_plugin_skeleton["files"]:
        md.append(f"- `{f['path']}`")
    md.append("")
    md.append("### plugin.json")
    md.append("```json")
    md.append(minimal_plugin_skeleton["files"][0]["content"])
    md.append("```")
    md.append("")
    md.append("### index.mjs")
    md.append("```js")
    md.append(minimal_plugin_skeleton["files"][1]["content"])
    md.append("```")
    md.append("")

    (out_dir / "report.md").write_text("\n".join(md).strip() + "\n", encoding="utf-8-sig")

    print(str(out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
