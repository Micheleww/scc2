#!/usr/bin/env python3
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class ExtractResult:
    """Result of extracting a unified diff from text.

    Attributes:
        ok: True if a valid diff was extracted
        diff: The extracted diff text (empty if ok=False)
        error: Error message if extraction failed (None if ok=True)
        notes: Additional information about extraction method used
    """
    ok: bool
    diff: str
    error: Optional[str] = None
    notes: Optional[str] = None


_FENCE_RE = re.compile(r"```(?P<lang>[a-zA-Z0-9_-]+)?\s*\n(?P<body>.*?)\n```", re.DOTALL)


def _looks_like_unified_diff(text: str) -> bool:
    """Quick heuristic check if text looks like a unified diff.

    Checks for presence of standard diff markers:
    - File headers (--- and +++)
    - Hunk headers (@@)
    - Or git diff format (diff --git)

    Args:
        text: Text to check

    Returns:
        True if text appears to be a unified diff
    """
    t = (text or "").strip()
    if not t:
        return False
    # Fast checks: at least one file header and a hunk header.
    return ("--- " in t and "+++ " in t and "\n@@ " in t) or t.startswith("diff --git ")


def extract_unified_diff(text: str) -> ExtractResult:
    """Extract a unified diff from LLM output.

    Attempts to find and extract a valid unified diff from the input text.
    Tries multiple extraction strategies in order of preference:

    1. Fenced code blocks with language tag "diff" that contain valid diff
    2. Any fenced code block containing valid diff content
    3. Raw text if it looks like a valid diff

    Args:
        text: Input text that may contain a unified diff (e.g., LLM output)

    Returns:
        ExtractResult with ok=True and the extracted diff if found,
        or ok=False with error message if no valid diff found

    Example:
        >>> result = extract_unified_diff("```diff\\n--- a/file.txt\\n+++ b/file.txt\\n@@ -1 +1 @@\\n-old\\n+new\\n```")
        >>> result.ok
        True
        >>> "--- a/file.txt" in result.diff
        True
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

