#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8", errors="replace") or "{}")


def _write_json(path: Optional[Path], obj: Any) -> None:
    s = json.dumps(obj, ensure_ascii=False, indent=2)
    if path is None:
        print(s)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(s + "\n", encoding="utf-8", errors="replace")


def _tokenize(text: str) -> List[str]:
    s = (text or "").lower()
    out = []
    cur = []
    for ch in s:
        if ch.isalnum() or ch in ("_", "-"):
            cur.append(ch)
        else:
            if cur:
                out.append("".join(cur))
                cur = []
    if cur:
        out.append("".join(cur))
    return out


def _score_role(goal_tokens: List[str], role: Dict[str, Any]) -> Tuple[int, List[str]]:
    match = role.get("match") if isinstance(role.get("match"), dict) else {}
    kws = match.get("keywords_any") if isinstance(match.get("keywords_any"), list) else []
    kws = [str(k).strip().lower() for k in kws if str(k).strip()]
    score = 0
    hits: List[str] = []
    for kw in kws:
        if kw and kw in goal_tokens:
            score += 1
            hits.append(kw)
    return score, hits


def route_goal(*, goal: str, role_spec: Dict[str, Any]) -> Dict[str, Any]:
    roles = role_spec.get("roles") if isinstance(role_spec.get("roles"), list) else []
    fallback = str(role_spec.get("fallback_role_id") or "router")
    tokens = _tokenize(goal)

    best = {"role_id": fallback, "score": -1, "hits": []}
    for r in roles:
        if not isinstance(r, dict):
            continue
        role_id = str(r.get("role_id") or "").strip()
        if not role_id:
            continue
        s, hits = _score_role(tokens, r)
        if s > best["score"]:
            best = {"role_id": role_id, "score": s, "hits": hits}

    return {
        "ok": True,
        "goal": goal,
        "role_id": best["role_id"],
        "reason": {
            "match_score": best["score"],
            "matched_keywords": best["hits"],
            "fallback_role_id": fallback,
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="SCC role router (RoleSpec v0.1.0)")
    ap.add_argument("--goal", required=True, help="Task goal text")
    ap.add_argument(
        "--role-spec",
        default="docs/ssot/03_agent_playbook/role_spec.json",
        help="Path to RoleSpec JSON",
    )
    ap.add_argument("--out", default="", help="Optional output JSON path")
    args = ap.parse_args()

    repo_root = _repo_root()
    spec_path = Path(args.role_spec)
    if not spec_path.is_absolute():
        spec_path = (repo_root / spec_path).resolve()
    role_spec = _read_json(spec_path)

    decision = route_goal(goal=str(args.goal), role_spec=role_spec)
    out_path = Path(args.out).resolve() if str(args.out).strip() else None
    _write_json(out_path, decision)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

