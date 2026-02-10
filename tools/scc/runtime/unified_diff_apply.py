#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from tools.scc.lib.utils import norm_rel as _norm_rel


@dataclass
class ApplyResult:
    ok: bool
    error: Optional[str] = None
    applied_files: Optional[List[str]] = None


_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _read_lines(path: pathlib.Path) -> List[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)


def _write_lines(path: pathlib.Path, lines: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(lines), encoding="utf-8")


def apply_unified_diff(repo_root: pathlib.Path, diff_text: str) -> ApplyResult:
    """
    Minimal unified diff applier:
    - supports file sections with ---/+++ headers
    - supports hunks with context, +, - lines
    - does not support binary diffs or rename metadata
    Fail-closed if context mismatches.
    """
    root = pathlib.Path(repo_root).resolve()
    diff = (diff_text or "").splitlines()
    i = 0
    applied: List[str] = []

    def next_line() -> Optional[str]:
        nonlocal i
        if i >= len(diff):
            return None
        ln = diff[i]
        i += 1
        return ln

    while True:
        ln = next_line()
        if ln is None:
            break
        if not ln.startswith("--- "):
            continue
        old = _norm_rel(ln[4:].strip().removeprefix("a/"))
        ln2 = next_line()
        if ln2 is None or not ln2.startswith("+++ "):
            return ApplyResult(ok=False, error="missing_new_file_header")
        new = _norm_rel(ln2[4:].strip().removeprefix("b/"))
        target_rel = new or old
        if not target_rel:
            return ApplyResult(ok=False, error="invalid_target_path")
        target = (root / target_rel).resolve()
        try:
            target.relative_to(root)
        except Exception:
            return ApplyResult(ok=False, error=f"path_escapes_repo:{target_rel}")

        src_lines = _read_lines(target) if new else _read_lines(root / (old or ""))  # type: ignore[arg-type]
        out_lines = src_lines[:]
        # Apply hunks sequentially; we do line-based matching using the old file positions.
        # We keep a moving offset to account for insertions/deletions.
        offset = 0

        while True:
            pos = i
            peek = diff[pos] if pos < len(diff) else None
            if peek is None or peek.startswith("--- "):
                break
            ln3 = next_line()
            if ln3 is None:
                break
            if ln3.startswith("@@ "):
                m = _HUNK_RE.match(ln3)
                if not m:
                    return ApplyResult(ok=False, error="invalid_hunk_header")
                old_start = int(m.group(1))
                old_count = int(m.group(2) or "1")
                # new_start/new_count unused for apply.
                # Convert to 0-based index.
                idx = max(0, old_start - 1) + offset
                # Collect hunk lines until next header/hunk/file.
                hunk: List[str] = []
                while True:
                    p2 = i
                    nxt = diff[p2] if p2 < len(diff) else None
                    if nxt is None or nxt.startswith("--- ") or nxt.startswith("@@ "):
                        break
                    hunk.append(next_line() or "")
                # Apply hunk
                # Build expected old slice and replacement slice.
                expected: List[str] = []
                replacement: List[str] = []
                for hl in hunk:
                    if not hl:
                        continue
                    tag = hl[0]
                    text = hl[1:] + "\n"
                    if tag == " ":
                        expected.append(text)
                        replacement.append(text)
                    elif tag == "-":
                        expected.append(text)
                    elif tag == "+":
                        replacement.append(text)
                    elif tag == "\\":
                        # "\ No newline..." ignore
                        continue
                    else:
                        return ApplyResult(ok=False, error=f"invalid_hunk_line:{tag}")
                # Verify context
                if idx < 0 or idx + len(expected) > len(out_lines):
                    return ApplyResult(ok=False, error="hunk_out_of_range")
                if out_lines[idx : idx + len(expected)] != expected:
                    return ApplyResult(ok=False, error="hunk_context_mismatch")
                out_lines[idx : idx + len(expected)] = replacement
                offset += len(replacement) - len(expected)
            else:
                # Skip non-hunk metadata (diff --git, index, etc.)
                continue

        # Handle delete file
        if new is None and old is not None:
            # old exists; remove
            try:
                (root / old).unlink()
            except FileNotFoundError:
                pass
            applied.append(old)
        else:
            _write_lines(target, out_lines)
            applied.append(target_rel)

    return ApplyResult(ok=True, applied_files=sorted(set(applied)))

