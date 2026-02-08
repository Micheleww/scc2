from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_stat(path: Path) -> Dict[str, Any]:
    try:
        st = path.stat()
        return {
            "exists": True,
            "size_bytes": int(st.st_size),
            "mtime_utc": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
        }
    except Exception:
        return {"exists": False}


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8", errors="replace") or "{}")
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def task_root_dir(repo_root: Path, task_id: str) -> Path:
    return (Path(repo_root).resolve() / "artifacts" / "scc_tasks" / str(task_id)).resolve()


def task_evidence_dir(repo_root: Path, task_id: str) -> Path:
    return (task_root_dir(repo_root, task_id) / "evidence").resolve()


def _rel(repo_root: Path, p: Path) -> str:
    try:
        return str(p.resolve().relative_to(Path(repo_root).resolve()))
    except Exception:
        return str(p.resolve())


def build_task_evidence_index(*, repo_root: Path, task_id: str) -> Dict[str, Any]:
    """
    Create/update a compact, machine-readable index for task evidence.

    Output:
      artifacts/scc_tasks/<task_id>/evidence/index.json
    """
    root = Path(repo_root).resolve()
    tid = str(task_id)
    troot = task_root_dir(root, tid)
    evidence_dir = task_evidence_dir(root, tid)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    task_json = (troot / "task.json").resolve()
    task_obj = _read_json(task_json) if task_json.exists() else {}
    run_id: Optional[str] = None
    try:
        run_id = str(task_obj.get("run_id") or "").strip() or None
    except Exception:
        run_id = None

    known = {
        "task_json": task_json,
        "events_jsonl": (troot / "events.jsonl").resolve(),
        "continuation_md": (troot / "continuation.md").resolve(),
        "codex_plan_json": (evidence_dir / "codex_plan.json").resolve(),
        "chat_context_json": (evidence_dir / "chat_context.json").resolve(),
        "fullagent_submit_md": (evidence_dir / "fullagent_submit.md").resolve(),
        "patch_gate_status_json": (evidence_dir / "patch_gate" / "status.json").resolve(),
        "permission_decisions_dir": (evidence_dir / "permission_decisions").resolve(),
        "patches_dir": (evidence_dir / "patches").resolve(),
        "patch_applies_dir": (evidence_dir / "patch_applies").resolve(),
        "subtask_summaries_dir": (evidence_dir / "subtask_summaries").resolve(),
    }

    paths: Dict[str, Any] = {}
    for k, p in known.items():
        paths[k] = {
            "path": _rel(root, p),
            **_safe_stat(p),
        }

    listing: Dict[str, Any] = {}
    for dir_key in ("permission_decisions_dir", "patches_dir", "patch_applies_dir", "subtask_summaries_dir"):
        p = known[dir_key]
        if not p.exists() or not p.is_dir():
            continue
        try:
            files = []
            for fp in sorted(p.glob("*"))[:200]:
                if fp.is_dir():
                    continue
                files.append({"path": _rel(root, fp), **_safe_stat(fp)})
            listing[dir_key] = files
        except Exception:
            continue

    out: Dict[str, Any] = {
        "schema_version": "scc_task_evidence_index.v0",
        "task_id": tid,
        "run_id": run_id,
        "updated_utc": _utc_now(),
        "paths": paths,
        "listing": listing,
        "notes": {
            "repo_root": str(root),
            "cwd": os.getcwd(),
        },
    }

    idx_path = (evidence_dir / "index.json").resolve()
    tmp = idx_path.with_suffix(idx_path.suffix + ".tmp")
    tmp.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8", errors="replace")
    os.replace(tmp, idx_path)
    return out
