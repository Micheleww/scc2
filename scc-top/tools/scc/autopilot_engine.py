from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _autopilot_config_path(repo_root: Path) -> Path:
    return (Path(repo_root).resolve() / "configs" / "scc" / "autopilot.v0.json").resolve()


def _autopilot_state_path(repo_root: Path, task_id: str) -> Path:
    return (Path(repo_root).resolve() / "artifacts" / "scc_tasks" / str(task_id) / "evidence" / "autopilot" / "state.json").resolve()


@dataclass(frozen=True)
class AutopilotDecision:
    ok: bool
    rule_id: str
    next_phase: str
    next_action: str
    ask_user: Optional[Dict[str, Any]] = None
    escalate_to_tier: Optional[str] = None
    model_override: Optional[str] = None
    backoff_s: float = 0.0
    reason_code: str = ""
    risk_level: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": bool(self.ok),
            "rule_id": self.rule_id,
            "next_phase": self.next_phase,
            "next_action": self.next_action,
            "ask_user": self.ask_user,
            "escalate_to_tier": self.escalate_to_tier,
            "model_override": self.model_override,
            "backoff_s": float(self.backoff_s or 0.0),
            "reason_code": self.reason_code,
            "risk_level": self.risk_level,
            "ts_utc": _utc_now_iso(),
        }


def classify_reason_code(*, error: str, exit_code: Optional[int] = None) -> str:
    s = str(error or "").strip()
    if exit_code == 97:
        return "PERMISSION_DENIED"
    if ":" in s:
        head = s.split(":", 1)[0].strip()
        if head and head.replace("_", "").replace("-", "").isalnum() and len(head) <= 48:
            return head
    low = s.lower()
    if "rate limit" in low:
        return "RATE_LIMITED"
    if "timed out" in low or "timeout" in low:
        return "TIMEOUT"
    if "permission" in low or "access is denied" in low:
        return "PERMISSION_DENIED"
    if "auth" in low or "token" in low or "credential" in low:
        return "AUTH_REQUIRED"
    if "conflict" in low:
        return "WORKSPACE_CONFLICT"
    return "UNKNOWN"


def _risk_rank(risk: str) -> int:
    r = str(risk or "").strip().lower()
    return {"low": 0, "medium": 1, "high": 2, "critical": 3}.get(r, 0)


def _match_rule(*, rule: Dict[str, Any], status: str, reason_code: str, risk_level: str) -> bool:
    match = rule.get("match") if isinstance(rule.get("match"), dict) else {}
    if not match:
        return True
    if "status" in match:
        allowed = match.get("status")
        if isinstance(allowed, list) and status not in [str(x) for x in allowed]:
            return False
    if "reason_code" in match:
        allowed = match.get("reason_code")
        if isinstance(allowed, list) and reason_code not in [str(x) for x in allowed]:
            return False
    if "risk_level" in match:
        allowed = match.get("risk_level")
        if isinstance(allowed, list) and str(risk_level) not in [str(x) for x in allowed]:
            return False
    return True


def decide(
    *,
    repo_root: Path,
    task_id: str,
    status: str,
    reason_code: str,
    risk_level: str,
) -> Tuple[AutopilotDecision, Dict[str, Any]]:
    cfg = _read_json(_autopilot_config_path(repo_root))
    defaults = cfg.get("defaults") if isinstance(cfg.get("defaults"), dict) else {}
    max_auto_steps = int(defaults.get("max_auto_steps") or 0) if defaults else 0
    tiers = defaults.get("escalate_models") if isinstance(defaults.get("escalate_models"), dict) else {}

    state_path = _autopilot_state_path(repo_root, task_id)
    st = _read_json(state_path)
    auto_steps = int(st.get("auto_steps") or 0)
    matches_by_rule = st.get("matches_by_rule") if isinstance(st.get("matches_by_rule"), dict) else {}
    retries_by_reason = st.get("retries_by_reason") if isinstance(st.get("retries_by_reason"), dict) else {}

    rules = cfg.get("rules") if isinstance(cfg.get("rules"), list) else []
    rules_sorted = sorted(
        [r for r in rules if isinstance(r, dict)],
        key=lambda r: int(r.get("priority") or 0),
        reverse=True,
    )

    if max_auto_steps and auto_steps >= max_auto_steps:
        dec = AutopilotDecision(
            ok=True,
            rule_id="max_auto_steps__dlq",
            next_phase="dlq",
            next_action="dlq",
            reason_code=reason_code,
            risk_level=risk_level,
        )
        st["auto_steps"] = auto_steps
        st["last_decision"] = dec.to_dict()
        st["updated_utc"] = _utc_now_iso()
        _write_json(state_path, st)
        return dec, st

    chosen: Optional[Dict[str, Any]] = None
    for rule in rules_sorted:
        rid = str(rule.get("id") or "").strip() or "rule"
        if not _match_rule(rule=rule, status=status, reason_code=reason_code, risk_level=risk_level):
            continue
        limits = rule.get("limits") if isinstance(rule.get("limits"), dict) else {}
        max_matches = limits.get("max_matches_per_task")
        if max_matches is not None:
            try:
                if int(matches_by_rule.get(rid) or 0) >= int(max_matches):
                    continue
            except Exception:
                pass
        if str((rule.get("action") or {}).get("next_action") or "") == "retry":
            max_retries = limits.get("max_retries")
            if max_retries is not None:
                try:
                    if int(retries_by_reason.get(reason_code) or 0) >= int(max_retries):
                        continue
                except Exception:
                    pass
        chosen = rule
        break

    chosen = chosen or {"id": "fallback__dlq", "action": {"next_phase": "dlq", "next_action": "dlq"}}
    rid = str(chosen.get("id") or "rule")
    action = chosen.get("action") if isinstance(chosen.get("action"), dict) else {}
    escalate = chosen.get("escalate") if isinstance(chosen.get("escalate"), dict) else {}
    limits = chosen.get("limits") if isinstance(chosen.get("limits"), dict) else {}
    backoff_s = float(limits.get("backoff_s") or 0.0)
    next_phase = str(action.get("next_phase") or ("await_user" if action.get("next_action") == "ask_user" else "run"))
    next_action = str(action.get("next_action") or "noop")

    escalate_to_tier = str(escalate.get("to_tier") or "").strip() or None
    model_override = None
    if escalate_to_tier and isinstance(tiers, dict):
        model_override = str(tiers.get(escalate_to_tier) or "").strip() or None

    ask_user = action.get("ask_user") if isinstance(action.get("ask_user"), dict) else None

    dec = AutopilotDecision(
        ok=True,
        rule_id=rid,
        next_phase=next_phase,
        next_action=next_action,
        ask_user=ask_user,
        escalate_to_tier=escalate_to_tier,
        model_override=model_override,
        backoff_s=backoff_s,
        reason_code=reason_code,
        risk_level=risk_level,
    )

    matches_by_rule[rid] = int(matches_by_rule.get(rid) or 0) + 1
    st["schema_version"] = "scc_autopilot_state.v0"
    st["task_id"] = str(task_id)
    st["auto_steps"] = auto_steps
    st["matches_by_rule"] = matches_by_rule
    st["retries_by_reason"] = retries_by_reason
    st["last_decision"] = dec.to_dict()
    st.setdefault("created_utc", _utc_now_iso())
    st["updated_utc"] = _utc_now_iso()
    _write_json(state_path, st)
    return dec, st


def apply_action(
    *,
    repo_root: Path,
    task_id: str,
    decision: AutopilotDecision,
    state: Dict[str, Any],
    task_record: Dict[str, Any],
    on_retry_sleep: bool = True,
) -> Dict[str, Any]:
    st_path = _autopilot_state_path(repo_root, task_id)
    st = _read_json(st_path)
    auto_steps = int(st.get("auto_steps") or 0)
    retries_by_reason = st.get("retries_by_reason") if isinstance(st.get("retries_by_reason"), dict) else {}

    out: Dict[str, Any] = {"ok": True, "task_id": str(task_id), "decision": decision.to_dict()}
    if decision.next_action == "retry":
        st["auto_steps"] = auto_steps + 1
        retries_by_reason[decision.reason_code or "UNKNOWN"] = int(retries_by_reason.get(decision.reason_code or "UNKNOWN") or 0) + 1
        st["retries_by_reason"] = retries_by_reason
        st["updated_utc"] = _utc_now_iso()
        _write_json(st_path, st)
        if on_retry_sleep and float(decision.backoff_s or 0.0) > 0:
            time.sleep(float(decision.backoff_s))
        out["action_taken"] = "retry"
        out["set_status"] = "pending"
        return out

    if decision.next_action == "ask_user":
        st["auto_steps"] = auto_steps + 1
        st["updated_utc"] = _utc_now_iso()
        _write_json(st_path, st)
        out["action_taken"] = "ask_user"
        out["set_status"] = "await_user"
        out["ask_user"] = decision.ask_user
        return out

    if decision.next_action == "dlq" or decision.next_phase == "dlq":
        st["auto_steps"] = auto_steps + 1
        st["updated_utc"] = _utc_now_iso()
        _write_json(st_path, st)
        dlq_dir = (Path(repo_root).resolve() / "artifacts" / "scc_state" / "dlq").resolve()
        dlq_dir.mkdir(parents=True, exist_ok=True)
        dlq_path = (dlq_dir / f"{task_id}.json").resolve()
        _write_json(
            dlq_path,
            {
                "schema_version": "scc_dlq_item.v0",
                "task_id": str(task_id),
                "created_utc": _utc_now_iso(),
                "reason_code": decision.reason_code,
                "risk_level": decision.risk_level,
                "decision": decision.to_dict(),
                "task_record": task_record,
            },
        )
        out["action_taken"] = "dlq"
        out["set_status"] = "dlq"
        out["dlq_path"] = str(dlq_path)
        return out

    st["auto_steps"] = auto_steps + 1
    st["updated_utc"] = _utc_now_iso()
    _write_json(st_path, st)
    out["action_taken"] = "noop"
    return out


def selftest(repo_root: Path) -> Dict[str, Any]:
    cases = [
        ("failed", "TIMEOUT", "low"),
        ("failed", "PERMISSION_DENIED", "high"),
        ("failed", "RATE_LIMITED", "low"),
        ("failed", "UNKNOWN", "low"),
        ("failed", "DATA_LOSS_RISK", "critical"),
    ]
    results = []
    for i, (status, rc, risk) in enumerate(cases, 1):
        tid = f"_autopilot_selftest_{i:02d}"
        dec, st = decide(repo_root=repo_root, task_id=tid, status=status, reason_code=rc, risk_level=risk)
        results.append({"task_id": tid, "decision": dec.to_dict(), "state": st})
    return {"ok": True, "cases": results}


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        print(json.dumps(selftest(Path(args.repo_root).resolve()), ensure_ascii=False, indent=2))
