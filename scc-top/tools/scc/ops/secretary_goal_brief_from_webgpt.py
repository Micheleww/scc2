#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import List


REPO_ROOT = Path(__file__).resolve().parents[3]


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _write_text(path: Path, s: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(s, encoding="utf-8", errors="replace")


def _to_repo_rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve())).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def _extract_user_messages(md_text: str, *, max_items: int) -> List[str]:
    """
    Deterministic extraction: take first non-empty line of each "## User" block.
    """
    lines = md_text.splitlines()
    out: List[str] = []
    in_user = False
    buf: List[str] = []

    def flush():
        nonlocal buf
        if not buf:
            return
        first = ""
        for l in buf:
            s = l.strip()
            if s:
                first = s
                break
        if first:
            out.append(first[:240])
        buf = []

    for line in lines:
        if line.startswith("## "):
            flush()
            header = line[3:].strip().lower()
            in_user = header.startswith("user")
            continue
        if in_user:
            buf.append(line)
    flush()

    seen = set()
    deduped: List[str] = []
    for x in out:
        if x in seen:
            continue
        seen.add(x)
        deduped.append(x)
        if len(deduped) >= max_items:
            break
    return deduped


def main() -> int:
    ap = argparse.ArgumentParser(description="Secretary: build Goal Brief deterministically from WebGPT exports (no LLM).")
    ap.add_argument("--input-root", default="docs/INPUTS/WEBGPT")
    ap.add_argument("--out", default="docs/DERIVED/secretary/GOAL_BRIEF__LATEST.md")
    ap.add_argument("--max-conversations", type=int, default=3)
    ap.add_argument("--max-messages", type=int, default=12)
    args = ap.parse_args()

    input_root = Path(args.input_root)
    if not input_root.is_absolute():
        input_root = (REPO_ROOT / input_root).resolve()
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = (REPO_ROOT / out_path).resolve()

    conversations_dir = (input_root / "conversations").resolve()
    convo_paths = []
    if conversations_dir.exists():
        convo_paths = sorted(conversations_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    convo_paths = convo_paths[: max(0, int(args.max_conversations or 0))]

    items: List[str] = []
    sources: List[str] = []
    for p in convo_paths:
        sources.append(_to_repo_rel(p))
        msgs = _extract_user_messages(_read_text(p), max_items=int(args.max_messages or 12))
        items.extend(msgs)
    items = items[: max(1, int(args.max_messages or 12))]

    content = "\n".join(
        [
            "# GOAL_BRIEF__LATEST (v0.1.0)",
            "",
            f"- generated_utc: {_iso_now()}",
            "- sources:",
            *[f"  - `{s}`" for s in sources],
            "",
            "## Goals (raw-derived, deterministic)",
            *([f"- {x}" for x in items] if items else ["- (no user messages found)"]),
            "",
            "## Constraints (default)",
            "- Follow `docs/START_HERE.md` and SSOT registry; do not create a second docs entrypoint.",
            "- Prefer deterministic tooling; avoid repo-wide scanning.",
            "",
        ]
    )
    _write_text(out_path, content + "\n")
    print(_to_repo_rel(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

