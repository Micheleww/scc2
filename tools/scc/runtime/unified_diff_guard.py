#!/usr/bin/env python3
from __future__ import annotations

import fnmatch
import os
import pathlib
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from tools.scc.lib.utils import norm_rel


_DIFF_HEADER_RE = re.compile(r"^(?:diff --git a/(.*?) b/(.*?)|--- (?:a/)?(.*?)\n\+\+\+ (?:b/)?(.*?))$", re.MULTILINE)


def _glob_match(path_posix: str, globs: List[str]) -> bool:
    p = path_posix.replace("\\", "/")
    for g in globs:
        if fnmatch.fnmatch(p, g.replace("\\", "/")):
            return True
    return False


def _is_allowed(path_posix: str, allow_globs: List[str], deny_globs: List[str]) -> bool:
    if deny_globs and _glob_match(path_posix, deny_globs):
        return False
    if not allow_globs:
        return False
    if "**" in [g.strip() for g in allow_globs]:
        return True
    return _glob_match(path_posix, allow_globs)


def list_touched_files(diff_text: str) -> List[str]:
    diff = str(diff_text or "")
    out: List[str] = []
    for m in re.finditer(r"^diff --git a/(.*?) b/(.*?)\s*$", diff, re.MULTILINE):
        a = norm_rel(m.group(1))
        b = norm_rel(m.group(2))
        if a:
            out.append(a)
        if b:
            out.append(b)
    if out:
        return sorted({p for p in out})
    # Fallback to ---/+++ pairs
    lines = diff.splitlines()
    for i in range(len(lines) - 1):
        if lines[i].startswith("--- ") and lines[i + 1].startswith("+++ "):
            a = lines[i][4:].strip()
            b = lines[i + 1][4:].strip()
            a = a[2:] if a.startswith("a/") else a
            b = b[2:] if b.startswith("b/") else b
            na = norm_rel(a)
            nb = norm_rel(b)
            if na and na != "/dev/null":
                out.append(na)
            if nb and nb != "/dev/null":
                out.append(nb)
    return sorted({p for p in out if p and p != "/dev/null"})


@dataclass(frozen=True)
class GuardResult:
    ok: bool
    error: Optional[str] = None
    touched_files: Optional[List[str]] = None
    denied: Optional[List[str]] = None
    notes: Optional[str] = None


def guard_diff(
    *,
    diff_text: str,
    role_policy: Dict[str, Any],
    child_task: Dict[str, Any],
) -> GuardResult:
    touched = list_touched_files(diff_text)
    if not touched:
        return GuardResult(ok=False, error="diff_has_no_touched_files", touched_files=[])

    allow_globs = []
    deny_globs = []
    try:
        w = role_policy.get("permissions", {}).get("write", {})
        allow_globs = [str(x) for x in (w.get("allow_paths") or []) if isinstance(x, str)]
        deny_globs = [str(x) for x in (w.get("deny_paths") or []) if isinstance(x, str)]
    except Exception:
        pass

    # Tighten: patch must also stay within child pins allowed_paths prefixes when present.
    pins = child_task.get("pins") if isinstance(child_task.get("pins"), dict) else {}
    allowed_prefixes = [str(x).replace("\\", "/").rstrip("/") for x in (pins.get("allowed_paths") or []) if isinstance(x, str)]
    allowed_prefixes = [p for p in allowed_prefixes if p and p != "**"]

    denied: List[str] = []
    for f in touched:
        nf = norm_rel(f)
        if not nf:
            denied.append(f)
            continue
        if not _is_allowed(nf, allow_globs=allow_globs, deny_globs=deny_globs):
            denied.append(nf)
            continue
        if allowed_prefixes:
            ok_prefix = any(nf == p or nf.startswith(p + "/") for p in allowed_prefixes)
            if not ok_prefix:
                denied.append(nf)
                continue

    if denied:
        return GuardResult(ok=False, error="scope_violation", touched_files=touched, denied=sorted(set(denied)))
    return GuardResult(ok=True, touched_files=touched)

