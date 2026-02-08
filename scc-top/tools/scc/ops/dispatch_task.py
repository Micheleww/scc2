#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SCC deterministic dispatcher (v0.1.0).

Goals:
- Turn a human goal into a deterministic routing decision (RoleSpec)
- Generate a safe Codex delegation config (allowed_globs required, worktree isolation, token budgets)
- Optionally run the batch via tools/scc/automation/run_batches.py

This tool is "leader-facing": it does not call LLMs itself; it only generates config and runs the automation runner.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8", errors="replace") or "{}")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", errors="replace")


def _normalize_path(p: str) -> str:
    return (p or "").replace("\\", "/").lstrip("/").strip()


def _match_any(path: str, patterns: list[str]) -> bool:
    path = _normalize_path(path)
    for pat in patterns:
        pat = _normalize_path(pat)
        if not pat:
            continue
        if pat.endswith("/") and path.startswith(pat):
            return True
        if fnmatch.fnmatchcase(path, pat):
            return True
    return False


def _extract_keywords(text: str) -> list[str]:
    import re

    words = re.findall(r"[A-Za-z0-9_./:-]{3,}", text or "")
    out: list[str] = []
    seen: set[str] = set()
    for w in words:
        w2 = w.strip().strip(".,;:()[]{}\"'").lower()
        if not w2 or w2 in seen:
            continue
        seen.add(w2)
        out.append(w2)
    return out[:24]


def _load_registry(repo_root: Path) -> dict:
    p = (repo_root / "docs" / "ssot" / "registry.json").resolve()
    if not p.exists():
        p = (repo_root / "docs" / "ssot" / "_registry.json").resolve()
    if not p.exists():
        return {}
    return _read_json(p)


def _load_role_spec(repo_root: Path) -> dict:
    p = (repo_root / "docs" / "ssot" / "03_agent_playbook" / "role_spec.json").resolve()
    if not p.exists():
        return {}
    return _read_json(p)


def _tokenize(text: str) -> list[str]:
    s = (text or "").lower()
    out: list[str] = []
    cur: list[str] = []
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


def _route_role_id(*, desc: str, role_spec: dict) -> str:
    roles = role_spec.get("roles") if isinstance(role_spec.get("roles"), list) else []
    fallback = str(role_spec.get("fallback_role_id") or "router")
    tokens = _tokenize(desc)

    best_role = fallback
    best_score = -1
    for r in roles:
        if not isinstance(r, dict):
            continue
        rid = str(r.get("role_id") or "").strip()
        if not rid:
            continue
        match = r.get("match") if isinstance(r.get("match"), dict) else {}
        kws = match.get("keywords_any") if isinstance(match.get("keywords_any"), list) else []
        kws = [str(k).strip().lower() for k in kws if str(k).strip()]
        score = 0
        for kw in kws:
            if kw and kw in tokens:
                score += 1
        if score > best_score:
            best_score = score
            best_role = rid
    return best_role


def _memory_paths_for_role(*, role_id: str, role_spec: dict) -> list[str]:
    roles = role_spec.get("roles") if isinstance(role_spec.get("roles"), list) else []
    for r in roles:
        if not isinstance(r, dict):
            continue
        rid = str(r.get("role_id") or "").strip()
        if rid != role_id:
            continue
        m = r.get("memory_paths")
        if isinstance(m, list):
            return [str(x).strip() for x in m if str(x).strip()]
        return []
    return []


def select_embed_paths_from_registry(*, repo_root: Path, task_text: str, allowed_globs: list[str], limit: int = 6) -> list[str]:
    """
    Deterministic selection of registry-defined docs (read-only).

    NOTE: embed_paths are read-only context and MUST NOT be constrained by write allowlists.
    """
    reg = _load_registry(repo_root)
    if not isinstance(reg, dict):
        return []
    ctx = reg.get("context_assembly") if isinstance(reg.get("context_assembly"), dict) else {}
    default_order = ctx.get("default_order") if isinstance(ctx.get("default_order"), list) else []
    canonical = reg.get("canonical") if isinstance(reg.get("canonical"), list) else []

    meta_by_path: dict[str, dict[str, str]] = {}
    candidates: list[str] = []

    def add(rel: str, *, doc_id: str = "", title: str = "") -> None:
        rel2 = _normalize_path(rel)
        if not rel2:
            return
        rp = (repo_root / rel2).resolve()
        if not rp.exists() or not rp.is_file():
            return
        if rel2 not in candidates:
            candidates.append(rel2)
        if doc_id or title:
            meta_by_path.setdefault(rel2, {"doc_id": doc_id, "title": title})

    for p in default_order:
        if isinstance(p, str) and p.strip():
            add(p.strip())
    for it in canonical:
        if not isinstance(it, dict):
            continue
        p = it.get("canonical_path")
        if isinstance(p, str) and p.strip():
            add(p.strip(), doc_id=str(it.get("doc_id") or ""), title=str(it.get("title") or ""))

    keywords = _extract_keywords(task_text)
    dlow = (task_text or "").lower()
    scored: list[tuple[int, str]] = []
    for rel in candidates:
        m = meta_by_path.get(rel) or {}
        doc_id = (m.get("doc_id") or "").lower()
        title = (m.get("title") or "").lower()
        base = rel.lower()
        s = 0
        if rel in (task_text or ""):
            s += 20
        if doc_id and doc_id in dlow:
            s += 20
        for kw in keywords:
            if kw in base:
                s += 8
            if doc_id and kw in doc_id:
                s += 10
            if title and kw in title:
                s += 6
        scored.append((s, rel))

    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    picked = [rel for s, rel in scored if s > 0][: max(1, min(50, int(limit or 6)))]
    return picked


def _ssot_search_paths(*, repo_root: Path, task_text: str, limit: int = 6) -> list[str]:
    """
    Deterministic, low-token context selection from SSOT registry.
    Uses tools/scc/ops/ssot_search.py for a stable implementation.
    """
    try:
        p = subprocess.run(
            [
                sys.executable,
                "tools/scc/ops/ssot_search.py",
                "--task-text",
                str(task_text or ""),
                "--limit",
                str(int(limit or 6)),
            ],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if int(p.returncode or 0) != 0:
            return []
        j = json.loads(p.stdout or "{}")
        picked = j.get("picked") if isinstance(j.get("picked"), list) else []
        out: list[str] = []
        for it in picked:
            if isinstance(it, dict) and str(it.get("path") or "").strip():
                out.append(str(it.get("path")).strip().replace("\\", "/"))
        return out[: max(0, int(limit or 6))]
    except Exception:
        return []


def _write_snippet_pack(
    *,
    repo_root: Path,
    area: str,
    taskcode: str,
    parent_id: str,
    task_text: str,
    allowed_globs: list[str],
    embed_paths: list[str],
    max_total_chars: int,
) -> str:
    """
    Generate a deterministic snippet pack under docs/REPORT/... to reduce token usage.
    Returns repo-relative path to the pack.
    """
    artifacts_dir = (repo_root / "docs" / "REPORT" / area / "artifacts" / taskcode).resolve()
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    safe_pid = _normalize_path(parent_id).replace("/", "_").replace(":", "_")
    out_path = (artifacts_dir / f"snippet_pack__{safe_pid}.md").resolve()
    args = [sys.executable, "tools/scc/ops/deterministic_snippet_pack.py", "--task-text", task_text, "--out", str(out_path.relative_to(repo_root)).replace("\\", "/")]
    for g in allowed_globs or []:
        gg = _normalize_path(g)
        if gg:
            args += ["--allowed-glob", gg]
    for p0 in embed_paths or []:
        pp = _normalize_path(p0)
        if pp:
            args += ["--embed-path", pp]
    args += ["--max-total-chars", str(int(max_total_chars or 30000)), "--max-files", "12"]
    subprocess.run(args, cwd=str(repo_root), check=False)
    return str(out_path.relative_to(repo_root)).replace("\\", "/")


@dataclass
class ParentSpec:
    id: str
    description: str
    allowed_globs: list[str]
    role_id: str = ""
    skills_required: list[str] | None = None


def _load_parents_file(path: Path) -> list[ParentSpec]:
    raw = json.loads(path.read_text(encoding="utf-8", errors="replace") or "[]")
    if not isinstance(raw, list):
        raise ValueError("parents_file must be a JSON list")
    out: list[ParentSpec] = []
    for it in raw:
        if not isinstance(it, dict):
            continue
        pid = str(it.get("id") or "").strip()
        desc = str(it.get("description") or "").strip()
        allowed = it.get("allowed_globs")
        role_id = str(it.get("role_id") or "").strip()
        skills_required = it.get("skills_required")
        if not pid or not desc:
            continue
        if not isinstance(allowed, list) or not [x for x in allowed if str(x).strip()]:
            raise ValueError(f"parent {pid}: missing allowed_globs[] (required)")
        sr = None
        if isinstance(skills_required, list):
            sr = [str(x).strip() for x in skills_required if str(x).strip()]
        out.append(
            ParentSpec(
                id=pid,
                description=desc,
                allowed_globs=[str(x).strip() for x in allowed if str(x).strip()],
                role_id=role_id,
                skills_required=sr,
            )
        )
    if not out:
        raise ValueError("no valid parents found")
    return out


def build_delegation_config(
    *,
    repo_root: Path,
    parents: list[ParentSpec],
    model: str,
    timeout_s: int,
    max_outstanding: int,
    context_budget: dict[str, int],
    area: str,
    taskcode: str,
) -> dict:
    role_spec = _load_role_spec(repo_root)
    items: list[dict[str, Any]] = []
    for p in parents:
        role_id = str(p.role_id or "").strip() or _route_role_id(desc=p.description, role_spec=role_spec)
        memory_paths = _memory_paths_for_role(role_id=role_id, role_spec=role_spec)
        ssot_paths = _ssot_search_paths(repo_root=repo_root, task_text=p.description, limit=6)
        embed_paths = [
            "docs/START_HERE.md",
            "docs/ssot/registry.json",
            *ssot_paths,
        ]
        # Embed role memory (read-only) even if not within allowlist; it does NOT grant write access.
        embed_paths = [*(memory_paths or []), *(embed_paths or [])]
        pack = _write_snippet_pack(
            repo_root=repo_root,
            area=str(area or "control_plane"),
            taskcode=str(taskcode or "DISPATCH_TASK_V010"),
            parent_id=p.id,
            task_text=p.description,
            allowed_globs=p.allowed_globs,
            embed_paths=embed_paths,
            max_total_chars=int(context_budget.get("max_total_chars") or 45000),
        )
        skills_required = p.skills_required if isinstance(p.skills_required, list) else None
        items.append(
            {
                "id": p.id,
                "description": p.description,
                "allowed_globs": p.allowed_globs,
                "role_id": role_id,
                "skills_required": skills_required or ["PATCH_APPLY"],
                "isolate_worktree": True,
                "embed_allowlisted_files": True,
                "embed_paths": [pack],
                "context_max_files": 1,
                "context_max_total_chars": int(context_budget.get("max_total_chars") or 45000),
                "context_head_lines": int(context_budget.get("head_lines") or 80),
                "context_tail_lines": int(context_budget.get("tail_lines") or 40),
                "require_changes": True,
            }
        )
    cfg = {
        "schema_version": "v0.1.0",
        "generated_by": "tools/scc/ops/dispatch_task.py",
        "max_outstanding": int(max_outstanding),
        "timeout_s": int(timeout_s),
        "batches": [{"name": "adhoc_dispatch_v0_1_0", "parents": {"parents": items}}],
        "defaults": {"model": str(model)},
    }
    return cfg


def main() -> int:
    ap = argparse.ArgumentParser(description="SCC deterministic dispatch helper (v0.1.0)")
    ap.add_argument("--goal", default="", help="High-level goal (routing only)")
    ap.add_argument("--parents-file", default="", help="JSON list of parents: [{id,description,allowed_globs[]}, ...]")
    ap.add_argument("--out-config", default="", help="Output config path (json)")
    ap.add_argument("--run", action="store_true", help="Run the generated config via run_batches.py")
    ap.add_argument("--base", default=os.environ.get("SCC_BASE_URL", "http://127.0.0.1:18788"))
    ap.add_argument("--model", default=os.environ.get("A2A_CODEX_MODEL", "gpt-5.2"))
    ap.add_argument("--area", default=os.environ.get("AREA", "control_plane"))
    ap.add_argument("--taskcode", default=os.environ.get("TASK_CODE", "DISPATCH_TASK_V010"))
    ap.add_argument("--timeout-s", type=int, default=int(os.environ.get("A2A_CODEX_TIMEOUT_SEC", "1800")))
    ap.add_argument("--max-outstanding", type=int, default=int(os.environ.get("SCC_AUTOMATION_MAX_OUTSTANDING", "3")))
    ap.add_argument("--context-max-files", type=int, default=4)
    ap.add_argument("--context-max-total-chars", type=int, default=45000)
    ap.add_argument("--context-head-lines", type=int, default=80)
    ap.add_argument("--context-tail-lines", type=int, default=40)
    args = ap.parse_args()

    repo_root = _repo_root()

    # Routing (optional)
    if str(args.goal or "").strip():
        try:
            p = subprocess.run(
                [sys.executable, "tools/scc/role_router.py", "--goal", str(args.goal), "--role-spec", "docs/ssot/03_agent_playbook/role_spec.json"],
                capture_output=True,
                text=True,
                timeout=15,
                cwd=str(repo_root),
            )
            print((p.stdout or "").strip())
        except Exception:
            pass

    if not str(args.parents_file or "").strip():
        return 0

    parents_path = Path(str(args.parents_file))
    if not parents_path.is_absolute():
        parents_path = (repo_root / parents_path).resolve()
    parents = _load_parents_file(parents_path)

    out_config = str(args.out_config or "").strip()
    if not out_config:
        stamp = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
        out_config = f"configs/scc/dispatch__adhoc__{stamp}Z.json"
    out_path = Path(out_config)
    if not out_path.is_absolute():
        out_path = (repo_root / out_path).resolve()

    budget = {
        "max_files": int(args.context_max_files),
        "max_total_chars": int(args.context_max_total_chars),
        "head_lines": int(args.context_head_lines),
        "tail_lines": int(args.context_tail_lines),
    }

    cfg = build_delegation_config(
        repo_root=repo_root,
        parents=parents,
        model=str(args.model),
        timeout_s=int(args.timeout_s),
        max_outstanding=int(args.max_outstanding),
        context_budget=budget,
        area=str(args.area),
        taskcode=str(args.taskcode),
    )
    _write_json(out_path, cfg)
    print(f"config={out_path}")

    if not args.run:
        return 0

    cmd = [
        sys.executable,
        "tools/scc/automation/run_batches.py",
        "--base",
        str(args.base),
        "--config",
        str(out_path),
        "--model",
        str(args.model),
        "--timeout-s",
        str(args.timeout_s),
        "--max-outstanding",
        str(args.max_outstanding),
    ]
    p = subprocess.run(cmd, cwd=str(repo_root))
    return int(p.returncode or 0)


if __name__ == "__main__":
    raise SystemExit(main())
