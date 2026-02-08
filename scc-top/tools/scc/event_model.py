from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional
from uuid import uuid4

SCCEventKind = Literal["action", "event", "span"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_event_id() -> str:
    return uuid4().hex


@dataclass(frozen=True)
class SCCUnifiedEvent:
    """
    SCC unified event model (v0.1.0).

    This is a minimal, append-only schema intended to unify Action/Event/Span.
    """

    event_id: str
    ts_utc: str
    kind: SCCEventKind
    name: str
    data: Dict[str, Any]

    task_id: Optional[str] = None
    run_id: Optional[str] = None
    parent_id: Optional[str] = None
    step_id: Optional[str] = None
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    parent_span_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "event_id": self.event_id,
            "ts_utc": self.ts_utc,
            "kind": self.kind,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "parent_id": self.parent_id,
            "step_id": self.step_id,
            "name": self.name,
            "data": self.data,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
        }
        return out
