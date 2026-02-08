#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Deterministic SSOT registry search (v0.1.0).

Purpose:
- Reduce token burn by selecting a small, deterministic set of context files from docs/ssot/registry.json.
- Avoid LLM "file hunting". This tool is purely local and reproducible.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace") or "{}")
    except Exception:
        return {}


def _extract_keywords(text: str) -> list[str]:
    t = (text or "").strip()
    if not t:
        return []
    # keep ASCII-ish tokens + common SCC tokens.
    words = re.findall(r"[A-Za-z0-9_./:-]{3,}", t)
    out: list[str] = []
    seen: set[str] = set()
    for w in words:
        w2 = w.strip().strip(".,;:()[]{}\"'").lower()
        if not w2:
            continue
        if w2 in seen:
            continue
        seen.add(w2)
        out.append(w2)
    return out[:24]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", default="docs/ssot/registry.json")
    ap.add_argument("--task-text", required=True)
    ap.add_argument("--limit", type=int, default=12)
    args = ap.parse_args()

    repo_root = _repo_root()
    registry_path = Path(args.registry)
    if not registry_path.is_absolute():
        registry_path = (repo_root / registry_path).resolve()
    if not registry_path.exists():
        print(json.dumps({"ok": False, "error": "registry_missing", "registry": str(registry_path)}, ensure_ascii=False, indent=2))
        return 2

    reg = _read_json(registry_path)
    if not isinstance(reg, dict):
        print(json.dumps({"ok": False, "error": "registry_invalid"}, ensure_ascii=False, indent=2))
        return 2

    keywords = _extract_keywords(str(args.task_text or ""))
    dlow = str(args.task_text or "").lower()

    candidates: list[dict] = []

    # candidates from default order + canonical list
    ctx = reg.get("context_assembly") if isinstance(reg.get("context_assembly"), dict) else {}
    default_order = ctx.get("default_order") if isinstance(ctx.get("default_order"), list) else []
    for p in default_order:
        if isinstance(p, str) and p.strip():
            candidates.append({"path": p.strip(), "doc_id": "", "title": "", "source": "default_order"})

    canonical = reg.get("canonical") if isinstance(reg.get("canonical"), list) else []
    for item in canonical:
        if not isinstance(item, dict):
            continue
        p = item.get("canonical_path")
        if isinstance(p, str) and p.strip():
            candidates.append(
                {
                    "path": p.strip(),
                    "doc_id": str(item.get("doc_id") or ""),
                    "title": str(item.get("title") or ""),
                    "source": "canonical",
                }
            )

    # de-dupe by path
    seen: set[str] = set()
    dedup: list[dict] = []
    for c in candidates:
        p = str(c.get("path") or "")
        if not p or p in seen:
            continue
        seen.add(p)
        dedup.append(c)
    candidates = dedup

    scored: list[dict] = []
    for c in candidates:
        p = str(c.get("path") or "")
        doc_id = str(c.get("doc_id") or "").lower()
        title = str(c.get("title") or "").lower()
        base = p.lower()
        s = 0
        if p and p in (args.task_text or ""):
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
        scored.append({**c, "score": s})

    scored.sort(key=lambda x: (int(x.get("score") or 0), str(x.get("path") or "")), reverse=True)

    limit = max(1, min(200, int(args.limit or 12)))
    picked = [x for x in scored if int(x.get("score") or 0) > 0][:limit]
    payload = {"ok": True, "registry": str(registry_path.relative_to(repo_root)), "keywords": keywords, "picked": picked}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

