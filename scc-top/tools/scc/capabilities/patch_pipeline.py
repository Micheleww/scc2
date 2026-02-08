from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import uuid4

from tools.scc.capabilities.permission_floor import evaluate_write_path, pdp_decide_patch_apply


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class PatchFileStat:
    path: str
    additions: int
    deletions: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PatchPreview:
    ok: bool
    now_utc: str
    repo_path: str
    files: List[PatchFileStat]
    total_additions: int
    total_deletions: int
    path_decisions: List[Dict[str, Any]]
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PatchApplyResult:
    ok: bool
    now_utc: str
    repo_path: str
    applied: bool
    git_check_ok: bool
    exit_code: int
    stdout: str
    stderr: str
    files: List[str]
    pdp: Optional[Dict[str, Any]] = None
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


_RE_DIFF_GIT = re.compile(r"^diff --git a/(.*?) b/(.*?)\s*$")
_RE_PLUS = re.compile(r"^\+\+\+ (.*)$")
_RE_MINUS = re.compile(r"^--- (.*)$")


def parse_unified_diff_files(patch_text: str) -> List[str]:
    """
    Best-effort file extraction from unified diff.

    Accepts:
    - git-style: diff --git a/x b/x
    - --- a/x +++ b/x
    """
    files: Set[str] = set()
    for raw in (patch_text or "").splitlines():
        line = raw.rstrip("\n")
        m = _RE_DIFF_GIT.match(line)
        if m:
            b = m.group(2).strip()
            if b and b != "/dev/null":
                files.add(b)
            continue
        m2 = _RE_PLUS.match(line)
        if m2:
            p = m2.group(1).strip()
            if p.startswith("b/"):
                p = p[2:]
            if p and p != "/dev/null":
                files.add(p)
            continue
        m3 = _RE_MINUS.match(line)
        if m3:
            p = m3.group(1).strip()
            if p.startswith("a/"):
                p = p[2:]
            if p and p != "/dev/null":
                files.add(p)
            continue
    return sorted(files)


def compute_patch_stats(patch_text: str) -> List[PatchFileStat]:
    """
    Very small stat extractor: additions/deletions per file.
    """
    cur: Optional[str] = None
    adds: Dict[str, int] = {}
    dels: Dict[str, int] = {}

    def _bump(m: Dict[str, int], k: str, n: int) -> None:
        m[k] = int(m.get(k) or 0) + n

    for raw in (patch_text or "").splitlines():
        line = raw.rstrip("\n")

        m = _RE_DIFF_GIT.match(line)
        if m:
            cur = m.group(2).strip() or None
            if cur:
                adds.setdefault(cur, 0)
                dels.setdefault(cur, 0)
            continue

        m2 = _RE_PLUS.match(line)
        if m2:
            p = m2.group(1).strip()
            if p.startswith("b/"):
                p = p[2:]
            cur = p if p and p != "/dev/null" else cur
            continue

        if line.startswith("+++ ") or line.startswith("--- "):
            continue
        if line.startswith("@@"):
            continue

        if cur:
            if line.startswith("+"):
                _bump(adds, cur, 1)
            elif line.startswith("-"):
                _bump(dels, cur, 1)

    out: List[PatchFileStat] = []
    for p in sorted(set(list(adds.keys()) + list(dels.keys()))):
        out.append(PatchFileStat(path=p, additions=int(adds.get(p) or 0), deletions=int(dels.get(p) or 0)))
    return out


def preview_patch(*, repo_path: Path, patch_text: str, scope_allow: Optional[List[str]] = None) -> PatchPreview:
    repo_path = Path(repo_path).resolve()
    files = compute_patch_stats(patch_text)
    decisions: List[Dict[str, Any]] = []
    ok = True

    for f in files:
        d = evaluate_write_path(repo_path=repo_path, target_path=f.path, action="apply_patch", scope_allow=scope_allow)
        decisions.append(d.to_dict())
        if not d.ok:
            ok = False

    total_add = sum(x.additions for x in files)
    total_del = sum(x.deletions for x in files)
    return PatchPreview(
        ok=ok,
        now_utc=_utc_now_iso(),
        repo_path=str(repo_path),
        files=files,
        total_additions=total_add,
        total_deletions=total_del,
        path_decisions=decisions,
        error="" if ok else "path_not_allowed",
    )


def _write_temp_patch(repo_path: Path, patch_text: str) -> Path:
    tmp_dir = (repo_path / "artifacts" / "scc_tmp").resolve()
    tmp_dir.mkdir(parents=True, exist_ok=True)
    p = tmp_dir / f"patch_{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}_{uuid4().hex[:8]}.diff"
    p.write_text(patch_text or "", encoding="utf-8", errors="replace")
    return p


def _run_git_apply(repo_path: Path, patch_file: Path, *, check_only: bool) -> Tuple[int, str, str]:
    argv = ["git", "apply"]
    if check_only:
        argv.append("--check")
    argv += ["--whitespace=nowarn", str(patch_file)]
    proc = subprocess.run(argv, cwd=str(repo_path), capture_output=True, text=True)
    return int(proc.returncode), proc.stdout or "", proc.stderr or ""

def _run_git_apply_opts(
    repo_path: Path,
    patch_file: Path,
    *,
    check_only: bool,
    reverse: bool,
    reject: bool,
) -> Tuple[int, str, str]:
    argv = ["git", "apply"]
    if reverse:
        argv.append("--reverse")
    if reject and not check_only:
        argv.append("--reject")
    if check_only:
        argv.append("--check")
    argv += ["--whitespace=nowarn", str(patch_file)]
    proc = subprocess.run(argv, cwd=str(repo_path), capture_output=True, text=True)
    return int(proc.returncode), proc.stdout or "", proc.stderr or ""


def patch_apply_enabled() -> bool:
    return (os.environ.get("SCC_PATCH_APPLY_ENABLED", "false").strip().lower() == "true")

def _find_repo_root(repo_path: Path) -> Path:
    """
    Best-effort repo_root discovery starting from a workspace path.
    """
    p = Path(repo_path).resolve()
    for cur in [p] + list(p.parents)[:8]:
        try:
            if (cur / "artifacts").exists() or (cur / ".git").exists():
                return cur
        except Exception:
            continue
    return p


def apply_patch_text(
    *,
    repo_path: Path,
    patch_text: str,
    scope_allow: Optional[List[str]] = None,
    check_only: bool = False,
    reverse: bool = False,
    reject: bool = False,
    task_id: Optional[str] = None,
) -> PatchApplyResult:
    repo_path = Path(repo_path).resolve()
    files = parse_unified_diff_files(patch_text)

    repo_root = _find_repo_root(repo_path)
    evidence_root: Path = repo_root
    if task_id:
        evidence_root = (repo_root / "artifacts" / "scc_tasks" / str(task_id) / "evidence").resolve()

    pdp = pdp_decide_patch_apply(
        repo_path=repo_path,
        files=list(files or []),
        scope_allow=scope_allow,
        check_only=bool(check_only),
        reverse=bool(reverse),
        patch_apply_enabled=bool(patch_apply_enabled()),
        task_id=task_id,
        evidence_root=evidence_root,
    )

    if str(pdp.get("decision") or "") == "deny":
        return PatchApplyResult(
            ok=False,
            now_utc=_utc_now_iso(),
            repo_path=str(repo_path),
            applied=False,
            git_check_ok=False,
            exit_code=97,
            stdout="",
            stderr=str(pdp.get("reason") or "pdp_denied"),
            files=files,
            pdp=pdp,
            error="pdp_denied",
        )

    if str(pdp.get("decision") or "") == "ask":
        return PatchApplyResult(
            ok=False,
            now_utc=_utc_now_iso(),
            repo_path=str(repo_path),
            applied=False,
            git_check_ok=False,
            exit_code=95,
            stdout="",
            stderr=str(pdp.get("reason") or "approval_required"),
            files=files,
            pdp=pdp,
            error="approval_required",
        )

    patch_file = _write_temp_patch(repo_path, patch_text)
    try:
        c_exit, c_out, c_err = _run_git_apply_opts(
            repo_path, patch_file, check_only=True, reverse=bool(reverse), reject=False
        )
        if c_exit != 0:
            return PatchApplyResult(
                ok=False,
                now_utc=_utc_now_iso(),
                repo_path=str(repo_path),
                applied=False,
                git_check_ok=False,
                exit_code=c_exit,
                stdout=c_out,
                stderr=c_err,
                files=files,
                pdp=pdp,
                error="git_apply_check_failed",
            )
        if check_only:
            return PatchApplyResult(
                ok=True,
                now_utc=_utc_now_iso(),
                repo_path=str(repo_path),
                applied=False,
                git_check_ok=True,
                exit_code=0,
                stdout=c_out,
                stderr=c_err,
                files=files,
                pdp=pdp,
                error="",
            )
        a_exit, a_out, a_err = _run_git_apply_opts(
            repo_path, patch_file, check_only=False, reverse=bool(reverse), reject=bool(reject)
        )
        return PatchApplyResult(
            ok=(a_exit == 0),
            now_utc=_utc_now_iso(),
            repo_path=str(repo_path),
            applied=(a_exit == 0),
            git_check_ok=True,
            exit_code=a_exit,
            stdout=a_out,
            stderr=a_err,
            files=files,
            pdp=pdp,
            error="" if a_exit == 0 else "git_apply_failed",
        )
    finally:
        try:
            patch_file.unlink(missing_ok=True)  # type: ignore[call-arg]
        except Exception:
            pass


def _sanitize_patch_name_for_dir(name: str) -> str:
    n = str(name or "").strip()
    n = n.replace("\\", "_").replace("/", "_").replace("..", "_")
    return (n or "patch")[:120]


def _atomic_write_json(path: Path, obj: Dict[str, Any]) -> None:
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _patch_gate_default_state(*, task_id: str) -> Dict[str, Any]:
    return {
        "ok": True,
        "task_id": str(task_id),
        "phase": "idle",
        "last_action": None,
        "updated_utc": _utc_now_iso(),
        "items": [],
    }


_PATCH_GATE_PHASE_ORDER: Dict[str, int] = {
    "idle": 0,
    "previewed": 1,
    "applied": 2,
    "rolled_back": 2,
    "selftested": 3,
    "verdicted": 4,
}
_PATCH_GATE_PHASES: Set[str] = set(_PATCH_GATE_PHASE_ORDER.keys())


def _parse_ts_utc(ts: Any) -> Optional[datetime]:
    if ts is None:
        return None
    s = str(ts).strip()
    if not s:
        return None
    # Support common "Z" UTC suffix.
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _ts_from_record(rec: Any) -> Optional[datetime]:
    if not isinstance(rec, dict):
        return None
    return _parse_ts_utc(rec.get("ts_utc") or rec.get("now_utc") or rec.get("ts"))


def _patch_gate_item_phase(it: Dict[str, Any]) -> str:
    """
    Compute the *current* item phase as a state machine.

    Key rule: rollback invalidates later phases (selftest/verdict) until a newer apply occurs.
    We preserve old fields on disk for auditability, but the phase reflects the latest valid
    lifecycle based on timestamps.
    """
    preview = it.get("preview")
    apply_rec = it.get("apply")
    rollback = it.get("rollback")
    selftest = it.get("selftest")
    verdict = it.get("verdict")

    preview_ts = _ts_from_record(preview)
    apply_ts_all = _ts_from_record(apply_rec)
    rollback_ts = _ts_from_record(rollback)
    selftest_ts = _ts_from_record(selftest)
    verdict_ts = _ts_from_record(verdict)

    apply_action = ""
    if isinstance(apply_rec, dict):
        apply_action = str(apply_rec.get("action") or "").strip().lower()

    # A "check" is not a state transition; it only validates applicability.
    apply_ts = None if apply_action == "check" else apply_ts_all

    applied_now = apply_ts is not None and (rollback_ts is None or apply_ts > rollback_ts)
    rolled_back_now = rollback_ts is not None and (apply_ts is None or rollback_ts >= apply_ts)

    phase = "idle"
    if isinstance(preview, dict) or preview_ts is not None:
        phase = "previewed"

    if applied_now:
        phase = "applied"
    elif rolled_back_now:
        phase = "rolled_back"

    # Selftest/verdict are only valid after the *currently effective* apply.
    if applied_now and selftest_ts is not None and apply_ts is not None and selftest_ts > apply_ts:
        phase = "selftested"
        if verdict_ts is not None and verdict_ts > selftest_ts:
            phase = "verdicted"

    # Allow standalone selftest/verdict (no apply/rollback) to surface as phases for API parity.
    if (not applied_now) and (not rolled_back_now):
        if selftest_ts is not None and (apply_ts_all is None or selftest_ts > apply_ts_all):
            phase = "selftested"
        if verdict_ts is not None and (selftest_ts is None or verdict_ts > selftest_ts):
            phase = "verdicted"

    return phase if phase in _PATCH_GATE_PHASES else "idle"


def _patch_gate_recompute_phase(state: Dict[str, Any]) -> str:
    """
    Derive a stable overall phase from the current item states and last_action.

    This keeps Patch Gate a real state machine: phase is always one of the known phases.
    """
    items = state.get("items") if isinstance(state.get("items"), list) else []
    best = "idle"
    best_rank = _PATCH_GATE_PHASE_ORDER[best]
    for it in items:
        if not isinstance(it, dict):
            continue
        ph = str(it.get("phase") or _patch_gate_item_phase(it))
        rank = _PATCH_GATE_PHASE_ORDER.get(ph, 0)
        if rank > best_rank:
            best = ph
            best_rank = rank

    la = state.get("last_action") if isinstance(state, dict) else None
    if isinstance(la, dict):
        act = str(la.get("action") or "").strip().lower()
        act_to_phase = {
            "preview": "previewed",
            "check": "previewed",
            "apply": "applied",
            "rollback": "rolled_back",
            "selftest": "selftested",
            "verdict": "verdicted",
        }
        ph = act_to_phase.get(act)
        if ph:
            rank = _PATCH_GATE_PHASE_ORDER.get(ph, 0)
            if rank > best_rank:
                best = ph
                best_rank = rank
    return best if best in _PATCH_GATE_PHASES else "idle"


def _patch_gate_normalize_state(*, task_id: str, raw: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    """
    Normalize patch gate state into the stable v1 schema used by the Patch Gate API.

    Returns (state, changed) where changed indicates a persistence-worthy migration.
    """
    base = _patch_gate_default_state(task_id=str(task_id))
    changed = False

    if not isinstance(raw, dict):
        return base, True

    # Only accept known top-level keys; keep forward-compatible unknown keys out of API shape.
    out = dict(base)
    for k in ["task_id", "phase", "last_action", "updated_utc", "items"]:
        if k in raw:
            out[k] = raw.get(k)

    out["task_id"] = str(task_id)
    out["ok"] = True

    if not isinstance(out.get("items"), list):
        out["items"] = []
        changed = True

    items_out: List[Dict[str, Any]] = []
    for it in list(out.get("items") or []):
        if not isinstance(it, dict):
            changed = True
            continue
        nm = str(it.get("name") or "").strip()
        if not nm:
            changed = True
            continue
        cur = {
            "name": nm,
            "updated_utc": str(it.get("updated_utc") or out.get("updated_utc") or _utc_now_iso()),
            "patch_path": it.get("patch_path"),
            "repo_path": it.get("repo_path"),
            "preview": it.get("preview"),
            "apply": it.get("apply"),
            "rollback": it.get("rollback"),
            "selftest": it.get("selftest"),
            "verdict": it.get("verdict"),
        }
        ph = str(it.get("phase") or "").strip()
        computed = _patch_gate_item_phase(cur)
        if (not ph) or (ph not in _PATCH_GATE_PHASES) or (ph != computed):
            cur["phase"] = computed
            changed = True
        else:
            cur["phase"] = ph
        items_out.append(cur)

    out["items"] = sorted(items_out, key=lambda d: str(d.get("name")))

    ph0 = str(out.get("phase") or "").strip()
    ph = ph0 if ph0 in _PATCH_GATE_PHASES else _patch_gate_recompute_phase(out)
    if ph != ph0:
        out["phase"] = ph
        changed = True

    if out.get("last_action") is not None and not isinstance(out.get("last_action"), dict):
        out["last_action"] = None
        changed = True

    if not out.get("updated_utc"):
        out["updated_utc"] = _utc_now_iso()
        changed = True

    return out, changed


def patch_gate_paths(*, evidence_dir: Path) -> Dict[str, Path]:
    """
    Canonical per-task patch gate paths rooted at <evidence_dir>/patch_gate.
    """
    ev = Path(evidence_dir).resolve()
    pg = (ev / "patch_gate").resolve()
    return {
        "patch_gate_dir": pg,
        "status_json": (pg / "status.json").resolve(),
        "events_jsonl": (pg / "events.jsonl").resolve(),
        "previews_dir": (pg / "previews").resolve(),
        "actions_dir": (pg / "actions").resolve(),
        "selftests_dir": (pg / "selftests").resolve(),
        "verdicts_dir": (pg / "verdicts").resolve(),
    }


def patch_gate_load(*, evidence_dir: Path, task_id: str) -> Dict[str, Any]:
    paths = patch_gate_paths(evidence_dir=evidence_dir)
    st_path = paths["status_json"]
    if not st_path.exists():
        return _patch_gate_default_state(task_id=str(task_id))
    try:
        raw = json.loads(st_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return _patch_gate_default_state(task_id=str(task_id))
    except Exception:
        return _patch_gate_default_state(task_id=str(task_id))

    # Back-compat: older schema stored {"current": {...}, "history": [...]}
    if "items" not in raw and (isinstance(raw.get("current"), dict) or isinstance(raw.get("history"), list)):
        items_by_name: Dict[str, Dict[str, Any]] = {}

        def _ingest_entry(ent: Dict[str, Any]) -> None:
            nm = str(ent.get("name") or "").strip()
            if not nm:
                return
            it = items_by_name.get(nm) or {
                "name": nm,
                "updated_utc": _utc_now_iso(),
                "preview": None,
                "apply": None,
                "rollback": None,
                "selftest": None,
                "verdict": None,
            }
            act = str(ent.get("action") or "").strip()
            if act in {"apply", "check", "rollback"} and isinstance(ent.get("apply_result"), dict):
                rec = {"ts_utc": str(ent.get("ts_utc") or _utc_now_iso()), "action": act, **ent.get("apply_result", {})}
                if act == "rollback":
                    it["rollback"] = rec
                elif act == "check":
                    if isinstance(it.get("apply"), dict) and str((it.get("apply") or {}).get("action") or "").strip().lower() != "check":
                        it["apply"]["last_check"] = rec
                    else:
                        it["apply"] = rec
                else:
                    it["apply"] = rec
            if isinstance(ent.get("selftest"), dict):
                it["selftest"] = {"ts_utc": str(ent.get("ts_utc") or _utc_now_iso()), **ent.get("selftest", {})}
            it["updated_utc"] = _utc_now_iso()
            items_by_name[nm] = it

        for h in list(raw.get("history") or []):
            if isinstance(h, dict):
                _ingest_entry(h)
        if isinstance(raw.get("current"), dict):
            _ingest_entry(raw["current"])

        cur_ent = raw.get("current") if isinstance(raw.get("current"), dict) else {}
        last_action = None
        if isinstance(cur_ent, dict) and cur_ent.get("action") and cur_ent.get("name"):
            last_action = {
                "ts_utc": str(cur_ent.get("ts_utc") or _utc_now_iso()),
                "action": str(cur_ent.get("action")),
                "name": str(cur_ent.get("name")),
            }

        out = _patch_gate_default_state(task_id=str(task_id))
        out["items"] = sorted(items_by_name.values(), key=lambda d: str(d.get("name")))
        out["last_action"] = last_action
        out["phase"] = str(raw.get("phase") or ("applied" if last_action and last_action.get("action") in {"apply", "check"} else out["phase"]))
        out["updated_utc"] = str(raw.get("updated_utc") or out["updated_utc"])
        norm, _ = _patch_gate_normalize_state(task_id=str(task_id), raw=out)
        return norm

    out = _patch_gate_default_state(task_id=str(task_id))
    out.update({k: raw.get(k) for k in ["phase", "last_action", "items", "updated_utc"] if k in raw})
    norm, _ = _patch_gate_normalize_state(task_id=str(task_id), raw=out)
    return norm


def patch_gate_write(*, evidence_dir: Path, task_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
    cur0 = _patch_gate_default_state(task_id=str(task_id))
    if isinstance(state, dict):
        cur0.update(state)
    cur0["task_id"] = str(task_id)
    cur0["ok"] = True

    cur, _ = _patch_gate_normalize_state(task_id=str(task_id), raw=cur0)
    cur["phase"] = _patch_gate_recompute_phase(cur)
    cur["updated_utc"] = _utc_now_iso()
    _atomic_write_json(patch_gate_paths(evidence_dir=evidence_dir)["status_json"], cur)
    return cur


def patch_gate_append_event(*, evidence_dir: Path, task_id: str, event_type: str, name: str, data: Dict[str, Any]) -> None:
    paths = patch_gate_paths(evidence_dir=evidence_dir)
    paths["patch_gate_dir"].mkdir(parents=True, exist_ok=True)
    rec = {"ts_utc": _utc_now_iso(), "task_id": str(task_id), "type": str(event_type), "name": str(name), "data": data or {}}
    try:
        with paths["events_jsonl"].open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _patch_gate_upsert_item(items: List[Dict[str, Any]], *, name: str) -> Dict[str, Any]:
    for it in items:
        if isinstance(it, dict) and str(it.get("name") or "") == str(name):
            return it
    it = {"name": str(name), "updated_utc": _utc_now_iso(), "preview": None, "apply": None, "rollback": None, "selftest": None, "verdict": None}
    items.append(it)
    return it


def patch_gate_sync_from_patches_dir(*, evidence_dir: Path, task_id: str) -> Dict[str, Any]:
    """
    Ensure patch_gate/status.json exists and contains an item per evidence/patches/*.diff.
    Safe to call repeatedly.
    """
    ev = Path(evidence_dir).resolve()
    patches_dir = (ev / "patches").resolve()
    paths = patch_gate_paths(evidence_dir=ev)
    status_exists = paths["status_json"].exists()
    state = patch_gate_load(evidence_dir=ev, task_id=str(task_id))

    changed = False
    # One-time migration: ensure on-disk schema includes per-item phases + stable top-level shape.
    for it in list(state.get("items") or []):
        if isinstance(it, dict) and (str(it.get("phase") or "").strip() not in _PATCH_GATE_PHASES):
            changed = True
            break
    if str(state.get("phase") or "").strip() not in _PATCH_GATE_PHASES:
        changed = True

    items = state.get("items") if isinstance(state.get("items"), list) else []
    by_name: Dict[str, Dict[str, Any]] = {}
    for it in items:
        if isinstance(it, dict) and it.get("name"):
            by_name[str(it.get("name"))] = it

    now = _utc_now_iso()
    if patches_dir.exists():
        for p in sorted(patches_dir.glob("*.diff"))[-200:]:
            it = by_name.get(p.name)
            if it is None:
                it = _patch_gate_upsert_item(items, name=p.name)
                by_name[p.name] = it
                changed = True
            if str(it.get("patch_path") or "") != str(p):
                it["patch_path"] = str(p)
                it["updated_utc"] = now
                changed = True
            # Keep per-item phase stable but correct.
            computed = _patch_gate_item_phase(it)
            if str(it.get("phase") or "") != computed:
                it["phase"] = computed
                changed = True

    state["items"] = items
    state["phase"] = _patch_gate_recompute_phase(state)

    if (not status_exists) or changed:
        return patch_gate_write(evidence_dir=ev, task_id=str(task_id), state=state)
    return state


def patch_gate_record_preview(
    *,
    evidence_dir: Path,
    task_id: str,
    name: str,
    repo_path: str,
    patch_path: str,
    preview: PatchPreview,
    scope_allow: Optional[List[str]],
) -> Dict[str, Any]:
    ev = Path(evidence_dir).resolve()
    paths = patch_gate_paths(evidence_dir=ev)
    paths["previews_dir"].mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    safe = _sanitize_patch_name_for_dir(name)
    out_path = (paths["previews_dir"] / f"{stamp}__preview__{safe}.json").resolve()
    out_path.write_text(
        json.dumps(
            {
                "ts_utc": _utc_now_iso(),
                "task_id": str(task_id),
                "name": str(name),
                "repo_path": str(repo_path),
                "patch_path": str(patch_path),
                "scope_allow": list(scope_allow or []),
                "preview": preview.to_dict(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    state = patch_gate_load(evidence_dir=ev, task_id=str(task_id))
    items = state.get("items") if isinstance(state.get("items"), list) else []
    it = _patch_gate_upsert_item(items, name=str(name))
    it["patch_path"] = str(patch_path)
    it["repo_path"] = str(repo_path)
    it["preview"] = {"ts_utc": _utc_now_iso(), **preview.to_dict(), "evidence_path": str(out_path)}
    it["updated_utc"] = _utc_now_iso()
    state["items"] = items
    state["phase"] = "previewed"
    state["last_action"] = {"ts_utc": _utc_now_iso(), "action": "preview", "name": str(name), "ok": bool(preview.ok)}
    patch_gate_append_event(evidence_dir=ev, task_id=str(task_id), event_type="preview", name=str(name), data={"ok": bool(preview.ok), "evidence_path": str(out_path)})
    return patch_gate_write(evidence_dir=ev, task_id=str(task_id), state=state)


def patch_gate_record_apply(
    *,
    evidence_dir: Path,
    task_id: str,
    name: str,
    action: str,
    repo_path: str,
    patch_path: str,
    pre_git: Dict[str, Any],
    post_git: Dict[str, Any],
    apply_result: PatchApplyResult,
    selftest: Optional[Dict[str, Any]],
    patch_apply_evidence_path: Optional[str] = None,
) -> Dict[str, Any]:
    ev = Path(evidence_dir).resolve()
    paths = patch_gate_paths(evidence_dir=ev)
    paths["actions_dir"].mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    safe = _sanitize_patch_name_for_dir(name)
    out_path = (paths["actions_dir"] / f"{stamp}__{str(action)}__{safe}.json").resolve()
    out_path.write_text(
        json.dumps(
            {
                "ts_utc": _utc_now_iso(),
                "task_id": str(task_id),
                "name": str(name),
                "action": str(action),
                "repo_path": str(repo_path),
                "patch_path": str(patch_path),
                "pre_git": pre_git or {},
                "post_git": post_git or {},
                "apply_result": apply_result.to_dict(),
                "selftest": selftest,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    state = patch_gate_load(evidence_dir=ev, task_id=str(task_id))
    items = state.get("items") if isinstance(state.get("items"), list) else []
    it = _patch_gate_upsert_item(items, name=str(name))
    it["patch_path"] = str(patch_path)
    it["repo_path"] = str(repo_path)
    rec = {
        "ts_utc": _utc_now_iso(),
        "action": str(action),
        **apply_result.to_dict(),
        "pre_git": pre_git or {},
        "post_git": post_git or {},
        "selftest": selftest,
        "evidence_path": str(out_path),
        "patch_apply_evidence_path": str(patch_apply_evidence_path or "") or None,
    }

    if str(action) == "rollback":
        it["rollback"] = rec
    elif str(action) == "check":
        # A "check" must not clobber a prior successful apply/rollback record.
        if isinstance(it.get("apply"), dict) and str((it.get("apply") or {}).get("action") or "").strip().lower() != "check":
            it["apply"]["last_check"] = rec
        else:
            it["apply"] = rec
    else:
        it["apply"] = rec
    it["updated_utc"] = _utc_now_iso()
    state["items"] = items
    if str(action) == "rollback":
        state["phase"] = "rolled_back"
    elif str(action) == "apply":
        state["phase"] = "applied"
    else:
        state["phase"] = "applied"
    state["last_action"] = {
        "ts_utc": _utc_now_iso(),
        "action": str(action),
        "name": str(name),
        "ok": bool(apply_result.ok),
        "applied": bool(apply_result.applied),
    }
    patch_gate_append_event(
        evidence_dir=ev,
        task_id=str(task_id),
        event_type=str(action),
        name=str(name),
        data={
            "ok": bool(apply_result.ok),
            "applied": bool(apply_result.applied),
            "evidence_path": str(out_path),
            "patch_apply_evidence_path": str(patch_apply_evidence_path or "") or None,
        },
    )
    return patch_gate_write(evidence_dir=ev, task_id=str(task_id), state=state)


def patch_gate_record_selftest(
    *,
    evidence_dir: Path,
    task_id: str,
    name: str,
    result: Dict[str, Any],
    out_dir: Optional[str],
) -> Dict[str, Any]:
    ev = Path(evidence_dir).resolve()
    paths = patch_gate_paths(evidence_dir=ev)
    paths["selftests_dir"].mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    safe = _sanitize_patch_name_for_dir(name)
    out_path = (paths["selftests_dir"] / f"{stamp}__selftest__{safe}.json").resolve()
    try:
        out_path.write_text(
            json.dumps(
                {"ts_utc": _utc_now_iso(), "task_id": str(task_id), "name": str(name), "out_dir": out_dir, "result": result or {}},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        out_path = Path("")
    state = patch_gate_load(evidence_dir=ev, task_id=str(task_id))
    items = state.get("items") if isinstance(state.get("items"), list) else []
    it = _patch_gate_upsert_item(items, name=str(name))
    it["selftest"] = {"ts_utc": _utc_now_iso(), "out_dir": out_dir, "evidence_path": str(out_path) if str(out_path) else None, **(result or {})}
    it["updated_utc"] = _utc_now_iso()
    state["items"] = items
    state["phase"] = "selftested"
    state["last_action"] = {"ts_utc": _utc_now_iso(), "action": "selftest", "name": str(name), "ok": bool(result.get("ok"))}
    patch_gate_append_event(
        evidence_dir=ev,
        task_id=str(task_id),
        event_type="selftest",
        name=str(name),
        data={"ok": bool(result.get("ok")), "out_dir": out_dir, "evidence_path": str(out_path) if str(out_path) else None},
    )
    return patch_gate_write(evidence_dir=ev, task_id=str(task_id), state=state)


def patch_gate_set_verdict(
    *,
    evidence_dir: Path,
    task_id: str,
    name: str,
    verdict: str,
    note: str,
) -> Dict[str, Any]:
    ev = Path(evidence_dir).resolve()
    paths = patch_gate_paths(evidence_dir=ev)
    paths["verdicts_dir"].mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    safe = _sanitize_patch_name_for_dir(name)
    out_path = (paths["verdicts_dir"] / f"{stamp}__verdict__{safe}.json").resolve()
    out_path.write_text(
        json.dumps(
            {"ts_utc": _utc_now_iso(), "task_id": str(task_id), "name": str(name), "verdict": str(verdict), "note": str(note or "")},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    state = patch_gate_load(evidence_dir=ev, task_id=str(task_id))
    items = state.get("items") if isinstance(state.get("items"), list) else []
    it = _patch_gate_upsert_item(items, name=str(name))
    it["verdict"] = {"ts_utc": _utc_now_iso(), "verdict": str(verdict), "note": str(note or ""), "evidence_path": str(out_path)}
    it["updated_utc"] = _utc_now_iso()
    state["items"] = items
    state["phase"] = "verdicted"
    state["last_action"] = {"ts_utc": _utc_now_iso(), "action": "verdict", "name": str(name), "verdict": str(verdict)}
    patch_gate_append_event(evidence_dir=ev, task_id=str(task_id), event_type="verdict", name=str(name), data={"verdict": str(verdict), "evidence_path": str(out_path)})
    return patch_gate_write(evidence_dir=ev, task_id=str(task_id), state=state)
