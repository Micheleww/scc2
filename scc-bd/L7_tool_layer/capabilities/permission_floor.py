from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Literal, Optional
from uuid import uuid4


CommandRisk = Literal["allow", "review", "deny"]
PDPDecision = Literal["allow", "ask", "deny"]

PDP_POLICY_VERSION = "SCC_PERMISSION_PDP_WIRE_V1"


@dataclass(frozen=True)
class PathDecision:
    ok: bool
    action: str
    input_path: str
    abs_path: str
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CommandDecision:
    risk: CommandRisk
    cmd: str
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


_RE_UNC = re.compile(r"^(\\\\\\\\|//)")
_RE_WINDOWS_DRIVE = re.compile(r"^[a-zA-Z]:[\\/]")


def _is_unc_path(p: str) -> bool:
    return bool(_RE_UNC.match(p.strip()))


def _looks_like_windows_absolute(p: str) -> bool:
    return bool(_RE_WINDOWS_DRIVE.match(p.strip()))


def evaluate_write_path(
    *,
    repo_path: Path,
    target_path: str,
    action: str,
    scope_allow: Optional[list[str]] = None,
) -> PathDecision:
    """
    Minimal permission floor for filesystem writes:
    - deny UNC paths (network shares)
    - resolve path and require it to be within repo_path
    - (reserved) scope_allow: optional future allowlist for narrowing/expanding
    """
    repo_path = Path(repo_path).resolve()
    raw = str(target_path or "").strip()
    if not raw:
        return PathDecision(ok=False, action=action, input_path=raw, abs_path="", reason="empty_path")

    if _is_unc_path(raw):
        return PathDecision(ok=False, action=action, input_path=raw, abs_path=raw, reason="unc_path_denied")

    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = (repo_path / p).resolve()
    else:
        p = p.resolve()

    try:
        p.relative_to(repo_path)
    except Exception:
        return PathDecision(ok=False, action=action, input_path=raw, abs_path=str(p), reason="outside_repo_path")

    # Optional scope_allow (minimal: if provided, require target under any allowed prefix)
    if scope_allow:
        allowed = False
        for prefix in scope_allow:
            pref = str(prefix or "").strip().replace("\\", "/").strip("/")
            if not pref:
                continue
            try:
                (repo_path / pref).resolve()
            except Exception:
                continue
            try:
                p.relative_to((repo_path / pref).resolve())
                allowed = True
                break
            except Exception:
                continue
        if not allowed:
            return PathDecision(ok=False, action=action, input_path=raw, abs_path=str(p), reason="not_in_scope_allow")

    return PathDecision(ok=True, action=action, input_path=raw, abs_path=str(p), reason="allowed")


_DENY_TOKENS = [
    # destructive
    " rm -rf ",
    " rm -r ",
    " rm -f ",
    " del ",
    " erase ",
    " format ",
    " shutdown",
    " reboot",
    " stop-computer",
    " remove-item -recurse",
    " remove-item -force",
]

_REVIEW_TOKENS = [
    # network / exfil / remote modifications
    " curl ",
    " wget ",
    " invoke-webrequest",
    " iwr ",
    " irm ",
    " scp ",
    " ssh ",
    " git push",
    " git clone",
    " docker ",
    " kubectl ",
]


def evaluate_command(*, cmd: str) -> CommandDecision:
    """
    Minimal command risk classifier for SCC (no policy engine yet).
    Used for observability and optional enforcement.
    """
    c = f" {str(cmd or '').strip().lower()} "
    if not c.strip():
        return CommandDecision(risk="allow", cmd=str(cmd or ""), reason="empty")

    for tok in _DENY_TOKENS:
        if tok in c:
            return CommandDecision(risk="deny", cmd=str(cmd or ""), reason=f"matched_deny:{tok.strip()}")

    for tok in _REVIEW_TOKENS:
        if tok in c:
            return CommandDecision(risk="review", cmd=str(cmd or ""), reason=f"matched_review:{tok.strip()}")

    return CommandDecision(risk="allow", cmd=str(cmd or ""), reason="ok")


def command_floor_enforce_enabled() -> bool:
    return (os.environ.get("SCC_COMMAND_FLOOR_ENFORCE", "false").strip().lower() == "true")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_repo_root() -> Path:
    # tools/scc/capabilities/permission_floor.py -> repo root is 3 levels up from "tools"
    return Path(__file__).resolve().parents[3]

def _looks_like_repo_root(p: Path) -> bool:
    try:
        p = Path(p).resolve()
        return (p / "tools").exists() and (p / "configs").exists()
    except Exception:
        return False

def _find_repo_root_from_path(p: Path) -> Path:
    """
    Best-effort repo root discovery from an arbitrary path (repo_root or task evidence dir).
    """
    cur = Path(p).resolve()
    for cand in [cur] + list(cur.parents)[:10]:
        if _looks_like_repo_root(cand):
            return cand
    return cur


def _normalize_evidence_dir(*, evidence_root: Optional[Path]) -> Path:
    """
    Backward-compatible evidence directory resolution.

    - If caller passes a task evidence dir (…/artifacts/scc_tasks/<task_id>/evidence), use it directly.
    - If caller passes an evidence dir named "evidence", use it directly.
    - Otherwise, treat evidence_root as repo_root and use <repo_root>/artifacts/scc_state/evidence.
    """
    root = Path(evidence_root).resolve() if evidence_root is not None else _default_repo_root()
    try:
        if root.name.lower() == "evidence":
            return root
        parts = [p.lower() for p in root.parts]
        if "artifacts" in parts and "scc_tasks" in parts and root.name.lower() == "evidence":
            return root
    except Exception:
        pass
    # Global/system evidence should not pollute the workspace root.
    if _looks_like_repo_root(root):
        return (root / "artifacts" / "scc_state" / "evidence").resolve()
    return (root / "artifacts" / "scc_state" / "evidence").resolve()


def _legacy_permission_decisions_dir(*, evidence_root: Optional[Path]) -> Optional[Path]:
    """
    Legacy path (pre-normalization):
      <repo_root>/evidence/permission_decisions
    """
    root = Path(evidence_root).resolve() if evidence_root is not None else _default_repo_root()
    if _looks_like_repo_root(root):
        return (root / "evidence" / "permission_decisions").resolve()
    return None


def _permission_decisions_dir(*, evidence_root: Optional[Path] = None) -> Path:
    ev_root = _normalize_evidence_dir(evidence_root=evidence_root)
    return (ev_root / "permission_decisions").resolve()


def _atomic_write_json(path: Path, obj: Dict[str, Any]) -> None:
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _write_pdp_evidence(*, evidence_root: Optional[Path], record: Dict[str, Any]) -> Path:
    ev_dir = _permission_decisions_dir(evidence_root=evidence_root)
    ev_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    decision = str(record.get("decision") or "unknown")
    kind = str(record.get("input", {}).get("kind") or "unknown")
    decision_id = str(record.get("decision_id") or uuid4().hex)
    fname = f"{stamp}__{decision}__{kind}__{decision_id}.json"
    out_path = (ev_dir / fname).resolve()
    out_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8", errors="replace")
    return out_path


def _queue_path(*, evidence_root: Optional[Path]) -> Path:
    # Approval queue is system state (not evidence). Keep it out of evidence/permission_decisions.
    root = Path(evidence_root).resolve() if evidence_root is not None else _default_repo_root()
    repo_root = _find_repo_root_from_path(root)
    return (repo_root / "artifacts" / "scc_state" / "approval_queue" / "permission_pdp_queue.json").resolve()


def _legacy_queue_candidates(*, evidence_root: Optional[Path]) -> list[Path]:
    """
    Legacy locations (read-only fallback):
    - <task_evidence>/permission_decisions/queue.json
    - <repo_root>/artifacts/scc_state/evidence/permission_decisions/queue.json
    - <repo_root>/evidence/permission_decisions/queue.json
    """
    cands: list[Path] = []
    root = Path(evidence_root).resolve() if evidence_root is not None else _default_repo_root()
    try:
        if root.name.lower() == "evidence":
            cands.append((root / "permission_decisions" / "queue.json").resolve())
        else:
            cands.append((_permission_decisions_dir(evidence_root=evidence_root) / "queue.json").resolve())
    except Exception:
        pass
    repo_root = _find_repo_root_from_path(root)
    cands.append((repo_root / "artifacts" / "scc_state" / "evidence" / "permission_decisions" / "queue.json").resolve())
    cands.append((repo_root / "evidence" / "permission_decisions" / "queue.json").resolve())
    # de-dupe while preserving order
    out: list[Path] = []
    seen = set()
    for p in cands:
        sp = str(p)
        if sp in seen:
            continue
        seen.add(sp)
        out.append(p)
    return out


def _queue_load(*, evidence_root: Optional[Path]) -> Dict[str, Any]:
    p = _queue_path(evidence_root=evidence_root)
    if not p.exists():
        return {"ok": True, "updated_utc": _utc_now_iso(), "items": []}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {"ok": True, "updated_utc": _utc_now_iso(), "items": []}
        if not isinstance(raw.get("items"), list):
            raw["items"] = []
        raw["ok"] = True
        raw["updated_utc"] = _utc_now_iso()
        return raw
    except Exception:
        return {"ok": True, "updated_utc": _utc_now_iso(), "items": []}


def _queue_load_with_legacy_fallback(*, evidence_root: Optional[Path]) -> Dict[str, Any]:
    """
    Load the canonical queue; if missing, try legacy locations and promote into canonical.
    """
    p = _queue_path(evidence_root=evidence_root)
    if p.exists():
        return _queue_load(evidence_root=evidence_root)

    for lp in _legacy_queue_candidates(evidence_root=evidence_root):
        if not lp.exists():
            continue
        try:
            raw = json.loads(lp.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raw = {}
        except Exception:
            raw = {}
        if not isinstance(raw.get("items"), list):
            raw["items"] = []
        raw["ok"] = True
        raw["updated_utc"] = _utc_now_iso()
        try:
            _atomic_write_json(p, raw)
        except Exception:
            pass
        return raw

    return {"ok": True, "updated_utc": _utc_now_iso(), "items": []}


def _queue_upsert(*, evidence_root: Optional[Path], item: Dict[str, Any]) -> Dict[str, Any]:
    q = _queue_load_with_legacy_fallback(evidence_root=evidence_root)
    items = q.get("items") if isinstance(q.get("items"), list) else []
    rid = str(item.get("request_id") or "").strip()
    if not rid:
        return q

    replaced = False
    out_items = []
    for it in items:
        if isinstance(it, dict) and str(it.get("request_id") or "") == rid:
            out_items.append(item)
            replaced = True
        else:
            out_items.append(it)
    if not replaced:
        out_items.append(item)

    q["items"] = sorted(
        [x for x in out_items if isinstance(x, dict) and x.get("request_id")],
        key=lambda d: str(d.get("created_utc") or ""),
    )
    q["updated_utc"] = _utc_now_iso()
    _atomic_write_json(_queue_path(evidence_root=evidence_root), q)
    return q


def pdp_list_requests(*, evidence_root: Optional[Path] = None, status: Optional[str] = "pending", limit: int = 200) -> Dict[str, Any]:
    q = _queue_load_with_legacy_fallback(evidence_root=evidence_root)
    items = q.get("items") if isinstance(q.get("items"), list) else []
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        if status and str(it.get("status") or "") != str(status):
            continue
        out.append(it)
    q["items"] = out[-int(limit or 200) :]
    return q


def pdp_resolve_request(
    *,
    evidence_root: Optional[Path] = None,
    request_id: str,
    verdict: Literal["approved", "denied"],
    note: str = "",
) -> Dict[str, Any]:
    rid = str(request_id or "").strip()
    if not rid:
        return {"ok": False, "error": "request_id_required"}

    q = _queue_load_with_legacy_fallback(evidence_root=evidence_root)
    items = q.get("items") if isinstance(q.get("items"), list) else []
    found = None
    for it in items:
        if isinstance(it, dict) and str(it.get("request_id") or "") == rid:
            found = it
            break
    if not found:
        return {"ok": False, "error": "not_found", "request_id": rid}

    found = dict(found)
    found["status"] = "approved" if verdict == "approved" else "denied"
    found["resolved_utc"] = _utc_now_iso()
    found["note"] = str(note or "")
    _queue_upsert(evidence_root=evidence_root, item=found)

    # Write an explicit resolution evidence record for auditability.
    rec = {
        "ts_utc": _utc_now_iso(),
        "decision_id": uuid4().hex,
        "policy_version": PDP_POLICY_VERSION,
        "input": {"kind": "approval_resolution", "request_id": rid, "verdict": verdict, "note": str(note or "")},
        "decision": "allow" if verdict == "approved" else "deny",
        "risk": str(found.get("risk") or "review"),
        "reason": "resolved_by_human",
        "request_id": rid,
        "task_id": str(found.get("task_id") or ""),
    }
    ev_path = _write_pdp_evidence(evidence_root=evidence_root, record=rec)
    return {"ok": True, "request_id": rid, "status": found.get("status"), "evidence_path": str(ev_path)}


def pdp_decide_command(
    *,
    cmd: str,
    task_id: Optional[str] = None,
    evidence_root: Optional[Path] = None,
    enqueue: bool = True,
) -> Dict[str, Any]:
    """
    Unified PDP for command execution decisions.

    Maps CommandRisk -> PDPDecision:
      - allow -> allow
      - review -> ask
      - deny -> deny
    """
    command_decision = evaluate_command(cmd=str(cmd or ""))
    if command_decision.risk == "allow":
        decision: PDPDecision = "allow"
    elif command_decision.risk == "review":
        decision = "ask"
    else:
        decision = "deny"

    tid = str(task_id or "").strip() or f"pdp_{uuid4().hex[:12]}"
    rid = uuid4().hex  # request id for ask decisions (and trace id otherwise)

    record: Dict[str, Any] = {
        "ts_utc": _utc_now_iso(),
        "decision_id": uuid4().hex,
        "policy_version": PDP_POLICY_VERSION,
        "input": {"kind": "command", "task_id": tid, "cmd": str(cmd or "")},
        "decision": decision,
        "risk": command_decision.risk,
        "reason": command_decision.reason,
    }

    ev_path = _write_pdp_evidence(evidence_root=evidence_root, record=record)
    out: Dict[str, Any] = {
        "ok": True,
        "task_id": tid,
        "decision": decision,
        "risk": command_decision.risk,
        "reason": command_decision.reason,
        "evidence_path": str(ev_path),
    }

    if decision == "ask" and bool(enqueue):
        req = {
            "request_id": rid,
            "task_id": tid,
            "status": "pending",
            "created_utc": record["ts_utc"],
            "updated_utc": record["ts_utc"],
            "policy_version": PDP_POLICY_VERSION,
            "risk": command_decision.risk,
            "reason": command_decision.reason,
            "input": record["input"],
            "decision_evidence_path": str(ev_path),
        }
        _queue_upsert(evidence_root=evidence_root, item=req)
        out["approval_required"] = True
        out["request_id"] = rid
        out["request_status"] = "pending"
    else:
        out["approval_required"] = False
    return out


def pdp_decide_patch_apply(
    *,
    repo_path: Path,
    files: list[str],
    scope_allow: Optional[list[str]] = None,
    check_only: bool = False,
    reverse: bool = False,
    patch_apply_enabled: Optional[bool] = None,
    task_id: Optional[str] = None,
    evidence_root: Optional[Path] = None,
    enqueue: bool = True,
) -> Dict[str, Any]:
    """
    Unified PDP for patch apply/rollback decisions.

    Rules:
      - Any out-of-repo path => deny (fail-closed)
      - check_only or reverse (rollback) => allow
      - forward apply: allow if patch_apply_enabled else ask
    """
    repo_path = Path(repo_path).resolve()
    tid = str(task_id or "").strip() or f"pdp_{uuid4().hex[:12]}"

    pe = bool(patch_apply_enabled) if patch_apply_enabled is not None else (
        os.environ.get("SCC_PATCH_APPLY_ENABLED", "false").strip().lower() == "true"
    )

    path_decisions = []
    denied = None
    for f in list(files or [])[:2000]:
        d = evaluate_write_path(repo_path=repo_path, target_path=str(f), action="apply_patch", scope_allow=scope_allow)
        dd = d.to_dict()
        path_decisions.append(dd)
        if not d.ok and denied is None:
            denied = dd

    if denied is not None:
        decision: PDPDecision = "deny"
        risk: str = "deny"
        reason: str = f"path_not_allowed:{denied.get('reason') or 'denied'}"
    elif bool(check_only) or bool(reverse):
        decision = "allow"
        risk = "allow"
        reason = "check_or_reverse_allowed"
    elif pe:
        decision = "allow"
        risk = "allow"
        reason = "patch_apply_enabled"
    else:
        decision = "ask"
        risk = "review"
        reason = "patch_apply_disabled"

    record: Dict[str, Any] = {
        "ts_utc": _utc_now_iso(),
        "decision_id": uuid4().hex,
        "policy_version": PDP_POLICY_VERSION,
        "input": {
            "kind": "patch_apply",
            "task_id": tid,
            "repo_path": str(repo_path),
            "files": list(files or []),
            "scope_allow": list(scope_allow or []),
            "check_only": bool(check_only),
            "reverse": bool(reverse),
            "patch_apply_enabled": bool(pe),
            "path_decisions": path_decisions,
        },
        "decision": decision,
        "risk": risk,
        "reason": reason,
    }

    ev_path = _write_pdp_evidence(evidence_root=evidence_root, record=record)
    out: Dict[str, Any] = {
        "ok": True,
        "task_id": tid,
        "decision": decision,
        "risk": risk,
        "reason": reason,
        "evidence_path": str(ev_path),
    }

    if decision == "ask" and bool(enqueue):
        rid = uuid4().hex
        req = {
            "request_id": rid,
            "task_id": tid,
            "status": "pending",
            "created_utc": record["ts_utc"],
            "updated_utc": record["ts_utc"],
            "policy_version": PDP_POLICY_VERSION,
            "risk": risk,
            "reason": reason,
            "input": record["input"],
            "decision_evidence_path": str(ev_path),
        }
        _queue_upsert(evidence_root=evidence_root, item=req)
        out["approval_required"] = True
        out["request_id"] = rid
        out["request_status"] = "pending"
    else:
        out["approval_required"] = False

    return out
