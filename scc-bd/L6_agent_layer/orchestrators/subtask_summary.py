from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.scc.event_log import get_task_logger


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        if not path.exists():
            return None
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _tail_lines(path: Path, limit: int = 80) -> List[str]:
    try:
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        lim = max(1, min(400, int(limit or 80)))
        return lines[-lim:]
    except Exception:
        return []


def _extract_submit_block(report_md: str) -> str:
    """
    Extract a machine-readable SUBMIT block if present.
    We accept common forms:
    - ```SUBMIT ... ```
    - ```submit ... ```
    """
    m = re.search(r"```(?:SUBMIT|submit)\s*\\n(.*?)\\n```", report_md, flags=re.DOTALL)
    if not m:
        return ""
    body = m.group(1).strip()
    return body[:8000]


@dataclass(frozen=True)
class SubtaskSummary:
    parent_task_id: str
    child_task_id: str
    recorded_utc: str
    status: str
    verdict: Optional[str]
    run_id: Optional[str]
    exit_code: Optional[int]
    report_md: Optional[str]
    evidence_dir: Optional[str]
    submit_block: str
    child_recent_events_tail: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def record_subtask_summary(*, repo_root: Path, parent_task_id: str, child_task_id: str) -> Optional[Path]:
    """
    Deterministically record a child task summary into the parent task's evidence folder.

    Output:
      artifacts/scc_tasks/<parent_task_id>/evidence/subtask_summaries/<child_task_id>.json
    """
    repo_root = Path(repo_root).resolve()
    parent_task_id = str(parent_task_id)
    child_task_id = str(child_task_id)

    child_dir = (repo_root / "artifacts" / "scc_tasks" / child_task_id).resolve()
    child_task_json = child_dir / "task.json"
    child_events = child_dir / "events.jsonl"
    child = _read_json(child_task_json) or {}

    status = str(child.get("status") or "").strip() or "unknown"
    verdict = str(child.get("verdict") or "").strip() or None
    run_id = str(child.get("run_id") or "").strip() or None
    report_md_path = str(child.get("report_md") or "").strip() or None
    evidence_dir = str(child.get("evidence_dir") or "").strip() or None
    exit_code = child.get("exit_code")
    exit_code_int = int(exit_code) if isinstance(exit_code, int) else None

    submit_block = ""
    if report_md_path:
        try:
            p = Path(report_md_path)
            if p.exists():
                submit_block = _extract_submit_block(p.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            submit_block = ""

    summary = SubtaskSummary(
        parent_task_id=parent_task_id,
        child_task_id=child_task_id,
        recorded_utc=_utc_now_iso(),
        status=status,
        verdict=verdict,
        run_id=run_id,
        exit_code=exit_code_int,
        report_md=report_md_path,
        evidence_dir=evidence_dir,
        submit_block=submit_block,
        child_recent_events_tail=_tail_lines(child_events, limit=60),
    )

    out_dir = (repo_root / "artifacts" / "scc_tasks" / parent_task_id / "evidence" / "subtask_summaries").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = (out_dir / f"{child_task_id}.json").resolve()
    out_path.write_text(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    get_task_logger(repo_root=repo_root, task_id=parent_task_id).emit(
        "subtask_summary_recorded",
        task_id=parent_task_id,
        data={"child_task_id": child_task_id, "status": status, "verdict": verdict, "path": str(out_path)},
    )

    return out_path

