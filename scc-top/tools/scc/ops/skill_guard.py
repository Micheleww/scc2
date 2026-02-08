#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SCC Skill Guard (v0.1.0)

Validates that a dispatch config only requests skills allowed by RoleSpec/SkillSpec.

This is a deterministic, fail-closed gate (no LLM calls).
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8", errors="replace") or "{}")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", errors="replace")
    os.replace(tmp, path)


def _iter_parents_from_config(cfg: dict) -> List[dict]:
    batches = cfg.get("batches") if isinstance(cfg.get("batches"), list) else []
    out: List[dict] = []
    for b in batches:
        if not isinstance(b, dict):
            continue
        parents = b.get("parents")
        if isinstance(parents, dict):
            items = parents.get("parents")
            if not isinstance(items, list):
                items = parents.get("tasks")
            if isinstance(items, list):
                for it in items:
                    if isinstance(it, dict):
                        out.append(it)
    return out


def _infer_role_id(parent: dict) -> str:
    rid = str(parent.get("role_id") or "").strip()
    if rid:
        return rid
    desc = str(parent.get("description") or "").lower()
    if any(k in desc for k in ["verdict", "verify", "validate", "selftest", "test"]):
        return "verifier"
    if any(k in desc for k in ["audit", "compliance", "gate", "guard"]):
        return "auditor"
    if any(k in desc for k in ["plan", "design", "schema", "spec", "contract"]):
        return "planner"
    return "executor"


def _index_roles(role_spec: dict) -> Dict[str, dict]:
    roles = role_spec.get("roles") if isinstance(role_spec.get("roles"), list) else []
    out: Dict[str, dict] = {}
    for r in roles:
        if not isinstance(r, dict):
            continue
        rid = str(r.get("role_id") or "").strip()
        if rid:
            out[rid] = r
    return out


def _index_skills(skill_spec: dict) -> Dict[str, dict]:
    skills = skill_spec.get("skills") if isinstance(skill_spec.get("skills"), list) else []
    out: Dict[str, dict] = {}
    for s in skills:
        if not isinstance(s, dict):
            continue
        sid = str(s.get("skill_id") or "").strip()
        if sid:
            out[sid] = s
    return out


def validate_config(
    *,
    cfg: dict,
    role_spec: dict,
    skill_spec: dict,
) -> Tuple[bool, dict]:
    roles = _index_roles(role_spec)
    skills = _index_skills(skill_spec)
    fallback = str(role_spec.get("fallback_role_id") or "router")

    parents = _iter_parents_from_config(cfg)
    problems: List[dict] = []
    checked: List[dict] = []

    for p in parents:
        pid = str(p.get("id") or "")
        role_id = _infer_role_id(p) or fallback
        role = roles.get(role_id) or roles.get(fallback) or {}
        allowed_skills = role.get("allowed_skills") if isinstance(role.get("allowed_skills"), list) else []
        allowed_skills_set = {str(x) for x in allowed_skills if str(x).strip()}

        req = p.get("skills_required")
        req_list = req if isinstance(req, list) else []
        req_list = [str(x).strip() for x in req_list if str(x).strip()]

        missing_skills = [s for s in req_list if s not in skills]
        denied_skills = [s for s in req_list if allowed_skills_set and (s not in allowed_skills_set)]

        checked.append({"id": pid, "role_id": role_id, "skills_required": req_list})
        if missing_skills or denied_skills:
            problems.append(
                {
                    "id": pid,
                    "role_id": role_id,
                    "skills_required": req_list,
                    "missing_skills": missing_skills,
                    "denied_skills": denied_skills,
                    "allowed_skills": sorted(list(allowed_skills_set)),
                }
            )

    ok = not problems
    report = {
        "ok": ok,
        "schema_version": "v0.1.0",
        "checked_count": len(checked),
        "problems_count": len(problems),
        "checked": checked,
        "problems": problems,
    }
    return ok, report


def main() -> int:
    ap = argparse.ArgumentParser(description="SCC skill guard (fail-closed)")
    ap.add_argument("--config", required=True, help="Dispatch config json (as produced by dispatch_task.py)")
    ap.add_argument("--role-spec", default="docs/ssot/03_agent_playbook/role_spec.json")
    ap.add_argument("--skill-spec", default="docs/ssot/03_agent_playbook/skill_spec.json")
    ap.add_argument("--out", default="", help="Write JSON report here (defaults to artifacts/scc_state/skill_guard_result.json)")
    args = ap.parse_args()

    repo_root = _repo_root()
    cfg_path = Path(args.config)
    if not cfg_path.is_absolute():
        cfg_path = (repo_root / cfg_path).resolve()
    if not cfg_path.exists():
        print(f"[skill_guard] config not found: {cfg_path}")
        return 2

    role_path = Path(args.role_spec)
    if not role_path.is_absolute():
        role_path = (repo_root / role_path).resolve()
    skill_path = Path(args.skill_spec)
    if not skill_path.is_absolute():
        skill_path = (repo_root / skill_path).resolve()

    cfg = _read_json(cfg_path)
    role_spec = _read_json(role_path)
    skill_spec = _read_json(skill_path)

    ok, report = validate_config(cfg=cfg, role_spec=role_spec, skill_spec=skill_spec)

    out = str(args.out or "").strip()
    if not out:
        out = "artifacts/scc_state/skill_guard_result.json"
    out_path = Path(out)
    if not out_path.is_absolute():
        out_path = (repo_root / out_path).resolve()
    _write_json(out_path, report)
    print(str(out_path))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

