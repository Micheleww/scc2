#!/usr/bin/env python3
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class ExtractResult:
    ok: bool
    diff: str
    error: Optional[str] = None
    notes: Optional[str] = None


_FENCE_RE = re.compile(r"```(?P<lang>[a-zA-Z0-9_-]+)?\s*\n(?P<body>.*?)\n```", re.DOTALL)


def _looks_like_unified_diff(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    # Fast checks: at least one file header and a hunk header.
    return ("--- " in t and "+++ " in t and "\n@@ " in t) or t.startswith("diff --git ")


def extract_unified_diff(text: str) -> ExtractResult:
    """
    Extract a unified diff from LLM output.
    Priority:
    1) fenced ```diff blocks
    2) any fenced block that looks like unified diff
    3) raw text if it looks like unified diff
    """
    s = str(text or "")
    best: Optional[str] = None

    for m in _FENCE_RE.finditer(s):
        lang = (m.group("lang") or "").strip().lower()
        body = (m.group("body") or "").strip("\n")
        if lang == "diff" and _looks_like_unified_diff(body):
            return ExtractResult(ok=True, diff=body)
        if _looks_like_unified_diff(body):
            best = best or body

    if best:
        return ExtractResult(ok=True, diff=best, notes="extracted_from_fenced_block_non_diff_lang")

    raw = s.strip()
    if _looks_like_unified_diff(raw):
        return ExtractResult(ok=True, diff=raw, notes="extracted_from_raw_text")

    return ExtractResult(ok=False, diff="", error="no_unified_diff_found")

