from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ToolSpan:
    span_id: str
    name: str
    kind: str
    started_utc: str
    ended_utc: str
    ok: bool
    input: Dict[str, Any]
    output: Dict[str, Any]
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def append_tool_span(*, evidence_dir: Path, span: ToolSpan) -> Path:
    p = (Path(evidence_dir).resolve() / "tool_spans.jsonl").resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(span.to_dict(), ensure_ascii=False) + "\n")
    return p


def record_tool_span(
    *,
    evidence_dir: Path,
    name: str,
    kind: str,
    started_utc: str,
    ok: bool,
    input: Optional[Dict[str, Any]] = None,
    output: Optional[Dict[str, Any]] = None,
    error: str = "",
) -> Path:
    span = ToolSpan(
        span_id=f"span_{uuid4().hex[:12]}",
        name=str(name or "").strip() or "tool",
        kind=str(kind or "").strip() or "tool",
        started_utc=started_utc,
        ended_utc=_utc_now_iso(),
        ok=bool(ok),
        input=input or {},
        output=output or {},
        error=str(error or ""),
    )
    return append_tool_span(evidence_dir=evidence_dir, span=span)

