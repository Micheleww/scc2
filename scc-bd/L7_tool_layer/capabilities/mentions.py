from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class MentionParseResult:
    agent_mentions: List[str]
    model_mentions: List[str]
    file_mentions: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


_RE_AGENT = re.compile(r"@(run-agent-[\w\-]+)", re.IGNORECASE)
_RE_MODEL = re.compile(r"@(ask-[\w\-]+)", re.IGNORECASE)
_RE_ANY = re.compile(r"@([^\s@]+)")
_RE_FILE_LOC = re.compile(
    r"^(?P<path>[a-zA-Z0-9/._\\\-]+)(?:(?:#L|:)(?P<start>\d+)(?:-(?P<end>\d+))?)?$"
)
_RE_EMAIL = re.compile(r"[\w.\-+]+@[\w.\-]+\.[A-Za-z]{2,}")


def parse_mentions(text: str, *, repo_root: Optional[Path] = None) -> MentionParseResult:
    """
    Parse Kode-style mentions:
    - @run-agent-xxx
    - @ask-xxx
    - @path/to/file

    Email addresses are ignored.
    """
    t = str(text or "")
    if not t.strip():
        return MentionParseResult(agent_mentions=[], model_mentions=[], file_mentions=[])

    # remove emails so they don't get picked up by @file matcher
    scrubbed = _RE_EMAIL.sub("", t)

    agent_mentions = sorted({m.group(1) for m in _RE_AGENT.finditer(scrubbed)})
    model_mentions = sorted({m.group(1) for m in _RE_MODEL.finditer(scrubbed)})

    file_mentions: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for m in _RE_ANY.finditer(scrubbed):
        token = str(m.group(1) or "").strip()
        if not token:
            continue

        # trim common trailing punctuation (but keep ':'/'#' for loc spec)
        raw = token.rstrip(".,;!?)]}>\"'")
        if not raw:
            continue
        low = raw.lower()
        if low.startswith("run-agent-") or low.startswith("ask-"):
            continue
        if raw in seen:
            continue
        seen.add(raw)

        mm = _RE_FILE_LOC.match(raw)
        if not mm:
            continue

        rel = str(mm.group("path") or "").strip().replace("\\", "/")
        if not rel:
            continue

        start_line: Optional[int] = None
        end_line: Optional[int] = None
        try:
            if mm.group("start") is not None:
                start_line = int(mm.group("start"))
                if mm.group("end") is not None:
                    end_line = int(mm.group("end"))
        except Exception:
            start_line = None
            end_line = None

        exists = False
        abs_path = ""
        if repo_root:
            p = (Path(repo_root) / rel).resolve()
            try:
                rr = Path(repo_root).resolve()
                if rr in p.parents or p == rr:
                    exists = p.exists()
                    abs_path = str(p)
            except Exception:
                pass

        fm: Dict[str, Any] = {"path": rel, "exists": exists, "abs_path": abs_path}
        if start_line is not None:
            fm["start_line"] = start_line
            if end_line is not None:
                fm["end_line"] = end_line
            fm["label"] = "mention:range"
        else:
            fm["label"] = "mention:file"
        file_mentions.append(fm)

    return MentionParseResult(
        agent_mentions=agent_mentions,
        model_mentions=model_mentions,
        file_mentions=file_mentions,
    )
