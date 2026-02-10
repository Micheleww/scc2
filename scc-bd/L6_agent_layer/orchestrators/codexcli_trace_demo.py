from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _base_url() -> str:
    # Use unified server base; default local port.
    return "http://127.0.0.1:18788"


def _post(path: str, payload: Dict[str, Any], *, timeout_s: float = 1200) -> Dict[str, Any]:
    r = requests.post(
        _base_url() + path,
        headers={"Content-Type": "application/json", "X-Trace-ID": f"scc-codex-demo-{int(time.time())}"},
        json=payload,
        timeout=timeout_s,
    )
    r.raise_for_status()
    return r.json()


def _get(path: str, *, timeout_s: float = 30) -> Dict[str, Any]:
    r = requests.get(_base_url() + path, timeout=timeout_s)
    r.raise_for_status()
    return r.json()


def _safe_mkdir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, obj: Any) -> None:
    _safe_mkdir(path.parent)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _try_parse_json_loose(text: str) -> Optional[Dict[str, Any]]:
    s = (text or "").strip()
    if not s:
        return None
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except Exception:
        start = s.find("{")
        end = s.rfind("}")
        if start >= 0 and end > start:
            mid = s[start : end + 1]
            try:
                obj = json.loads(mid)
                return obj if isinstance(obj, dict) else None
            except Exception:
                return None
        return None


@dataclass(frozen=True)
class CodexDemoResult:
    ok: bool
    task_id: str
    started_utc: str
    ended_utc: str
    decompose: Dict[str, Any]
    children: List[Dict[str, Any]]
    evidence_dir: str
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def run_codexcli_demo(*, repo_root: Path, goal: str, task_id: Optional[str] = None) -> CodexDemoResult:
    """
    Run a no-side-effect demo where CodexCLI acts as:
    - decomposer (parent task -> children)
    - executor (children -> results)

    This uses unified server `/executor/codex` and `/executor/codex/run`.
    """
    started = _utc_now_iso()
    tid = task_id or f"CODEXDEMO-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    ev_dir = (Path(repo_root).resolve() / "artifacts" / "scc_tasks" / tid / "evidence" / "codexcli_demo").resolve()
    _safe_mkdir(ev_dir)

    # 0) verify server up
    _get("/health")

    # 1) decompose (single prompt)
    decompose_prompt = (
        "Return ONLY JSON.\n"
        "Goal: " + goal + "\n"
        "Create 3-5 child tasks that are SAFE and have NO side effects.\n"
        "Read-only shell commands are allowed (ls/rg/cat). No edits.\n"
        "Schema:\n"
        "{\n"
        '  "children":[{"id":1,"description":"..."}],\n'
        '  "notes":"..."\n'
        "}\n"
    )
    started_tool = _utc_now_iso()
    try:
        dec = _post("/executor/codex", {"prompt": decompose_prompt, "model": "gpt-5.2-codex"}, timeout_s=1200)
        try:
            from tools.scc.capabilities.tool_spans import record_tool_span

            record_tool_span(
                evidence_dir=ev_dir,
                name="executor/codex",
                kind="executor_prompt",
                started_utc=started_tool,
                ok=bool(dec.get("success")),
                input={"path": "/executor/codex", "model": "gpt-5.2-codex"},
                output={"success": bool(dec.get("success")), "exit_code": int(dec.get("exit_code") or 0), "run_id": str(dec.get("run_id") or "")},
            )
        except Exception:
            pass
    except Exception as e:
        try:
            from tools.scc.capabilities.tool_spans import record_tool_span

            record_tool_span(
                evidence_dir=ev_dir,
                name="executor/codex",
                kind="executor_prompt",
                started_utc=started_tool,
                ok=False,
                input={"path": "/executor/codex", "model": "gpt-5.2-codex"},
                output={},
                error=str(e),
            )
        except Exception:
            pass
        raise
    _write_json(ev_dir / "decompose_raw.json", dec)

    parsed = _try_parse_json_loose(str(dec.get("stdout") or ""))
    if not parsed or not isinstance(parsed.get("children"), list):
        ended = _utc_now_iso()
        return CodexDemoResult(
            ok=False,
            task_id=tid,
            started_utc=started,
            ended_utc=ended,
            decompose={"raw": dec, "parsed": parsed},
            children=[],
            evidence_dir=str(ev_dir),
            error="decompose_parse_failed",
        )

    children = []
    for c in parsed.get("children")[:5]:
        if not isinstance(c, dict):
            continue
        cid = int(c.get("id") or 0) or (len(children) + 1)
        desc = str(c.get("description") or "").strip()
        if not desc:
            continue
        # Hard-enforce no side effects, but allow read-only tools.
        desc2 = (
            desc
            + "\n\nConstraints:\n"
            + "- Allowed: run READ-ONLY shell commands to inspect repo: `ls`, `rg`, `cat`, `Get-ChildItem`, `Select-String`.\n"
            + "- Forbidden: editing files, applying patches, running any write commands (rm/mv/cp/git apply/etc).\n"
            + "- Output: return ONLY valid JSON.\n"
        )
        children.append({"id": cid, "description": desc2})

    # 2) execute children as batch
    batch_payload = {"parents": {"parents": children}, "model": "gpt-5.2-codex", "timeout_s": 900}
    started_tool = _utc_now_iso()
    try:
        batch = _post("/executor/codex/run", batch_payload, timeout_s=1800)
        try:
            from tools.scc.capabilities.tool_spans import record_tool_span

            record_tool_span(
                evidence_dir=ev_dir,
                name="executor/codex/run",
                kind="executor_batch",
                started_utc=started_tool,
                ok=bool(batch.get("success")),
                input={"path": "/executor/codex/run", "model": "gpt-5.2-codex", "children": len(children)},
                output={"success": bool(batch.get("success")), "run_id": str(batch.get("run_id") or "")},
            )
        except Exception:
            pass
    except Exception as e:
        try:
            from tools.scc.capabilities.tool_spans import record_tool_span

            record_tool_span(
                evidence_dir=ev_dir,
                name="executor/codex/run",
                kind="executor_batch",
                started_utc=started_tool,
                ok=False,
                input={"path": "/executor/codex/run", "model": "gpt-5.2-codex", "children": len(children)},
                output={},
                error=str(e),
            )
        except Exception:
            pass
        raise
    _write_json(ev_dir / "children_run_raw.json", batch)

    ended = _utc_now_iso()
    result = CodexDemoResult(
        ok=bool(batch.get("success")) and bool(dec.get("success")),
        task_id=tid,
        started_utc=started,
        ended_utc=ended,
        decompose={"raw": dec, "parsed": parsed},
        children=[{"input": children, "run": batch}],
        evidence_dir=str(ev_dir),
        error="",
    )
    _write_json(ev_dir / "summary.json", result.to_dict())
    return result
