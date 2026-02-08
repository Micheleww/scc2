from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.scc.task_queue import SCCTaskQueue


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dlq_dir(repo_root: Path) -> Path:
    return (Path(repo_root).resolve() / "artifacts" / "scc_state" / "dlq").resolve()


def _safe_name(name: str) -> str:
    n = str(name or "").strip().replace("\\", "/").split("/")[-1]
    if not n or n in {".", ".."}:
        raise ValueError("invalid_name")
    if not n.endswith(".json"):
        raise ValueError("invalid_name")
    return n


@dataclass(frozen=True)
class DLQItemRef:
    name: str
    path: str
    size_bytes: int
    mtime_utc: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def list_dlq_items(*, repo_root: Path, limit: int = 50) -> Dict[str, Any]:
    dlq_dir = _dlq_dir(repo_root)
    if not dlq_dir.exists():
        return {"ok": True, "items": [], "dlq_dir": str(dlq_dir)}

    lim = max(1, min(500, int(limit or 50)))
    cand = list(dlq_dir.glob("*.json"))
    cand.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)

    out: List[Dict[str, Any]] = []
    for p in cand[:lim]:
        try:
            st = p.stat()
            out.append(
                DLQItemRef(
                    name=p.name,
                    path=str(p),
                    size_bytes=int(st.st_size),
                    mtime_utc=datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
                ).to_dict()
            )
        except Exception:
            continue
    return {"ok": True, "items": out, "dlq_dir": str(dlq_dir)}


def peek_dlq_item(*, repo_root: Path, name: str) -> Dict[str, Any]:
    dlq_dir = _dlq_dir(repo_root)
    n = _safe_name(name)
    p = (dlq_dir / n).resolve()
    try:
        if not p.is_relative_to(dlq_dir):
            return {"ok": False, "error": "invalid_path"}
    except Exception:
        return {"ok": False, "error": "invalid_path"}
    if not p.exists():
        return {"ok": False, "error": "not_found", "path": str(p)}
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(obj, dict):
            obj = {"raw": obj}
    except Exception as e:
        obj = {"parse_error": str(e)}
    return {"ok": True, "name": n, "path": str(p), "item": obj}


def ack_dlq_item(*, repo_root: Path, name: str, reason: str = "") -> Dict[str, Any]:
    dlq_dir = _dlq_dir(repo_root)
    n = _safe_name(name)
    p = (dlq_dir / n).resolve()
    try:
        if not p.is_relative_to(dlq_dir):
            return {"ok": False, "error": "invalid_path"}
    except Exception:
        return {"ok": False, "error": "invalid_path"}
    if not p.exists():
        return {"ok": False, "error": "not_found", "path": str(p)}

    # Best-effort: archive the ack as a sidecar for traceability.
    sidecar = p.with_suffix(".acked.json")
    try:
        sidecar.write_text(
            json.dumps({"acked_utc": _utc_now_iso(), "reason": str(reason or "").strip() or None}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass

    try:
        p.unlink()
        return {"ok": True, "name": n, "deleted": True, "path": str(p), "sidecar": str(sidecar)}
    except Exception as e:
        return {"ok": False, "error": str(e), "path": str(p)}


def replay_dlq_item(
    *,
    repo_root: Path,
    name: str,
    autostart: Optional[bool] = None,
    keep_in_dlq: bool = True,
) -> Dict[str, Any]:
    """
    Replay a DLQ item by re-queuing its task request.

    This is intentionally minimal:
    - It reuses the stored task_id and request payload (if present).
    - It does not attempt to "repair" payload schema; those should be handled upstream.
    """
    peek = peek_dlq_item(repo_root=repo_root, name=name)
    if not peek.get("ok"):
        return peek
    item = peek.get("item") if isinstance(peek.get("item"), dict) else {}

    task_id = str(item.get("task_id") or "").strip()
    task_record = item.get("task_record") if isinstance(item.get("task_record"), dict) else {}
    request = task_record.get("request") if isinstance(task_record.get("request"), dict) else None
    if not request and isinstance(item.get("request"), dict):
        request = item.get("request")
    if not task_id or not isinstance(request, dict):
        return {"ok": False, "error": "missing_task_id_or_request", "name": str(name), "task_id": task_id or None}

    q = SCCTaskQueue(repo_root=Path(repo_root))
    rec = q.submit_with_task_id(task_id=task_id, payload=request, autostart=autostart)

    out: Dict[str, Any] = {
        "ok": True,
        "name": str(peek.get("name")),
        "task_id": str(task_id),
        "requeued": True,
        "autostart": autostart,
        "keep_in_dlq": bool(keep_in_dlq),
        "task_record": rec.to_dict() if hasattr(rec, "to_dict") else {"task_id": rec.task_id, "status": rec.status},
    }

    if not keep_in_dlq:
        ack = ack_dlq_item(repo_root=repo_root, name=str(peek.get("name")), reason="replayed")
        out["acked"] = bool(ack.get("ok"))
        out["ack_result"] = ack

    return out
