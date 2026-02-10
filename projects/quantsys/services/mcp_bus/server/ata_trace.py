from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any


@dataclass
class ATATraceInfo:
    trace_id: str
    langgraph_url: str | None
    langsmith_url: str | None


def build_trace_info(env: dict[str, str]) -> ATATraceInfo:
    trace_id = f"ata-{uuid.uuid4().hex}"
    langgraph_base = env.get("LANGGRAPH_UI_URL") or env.get("LANGGRAPH_TRACE_URL")
    langsmith_base = env.get("LANGSMITH_UI_URL") or env.get("LANGSMITH_PROJECT_URL")

    langgraph_url = f"{langgraph_base.rstrip('/')}/trace/{trace_id}" if langgraph_base else None
    langsmith_url = f"{langsmith_base.rstrip('/')}/trace/{trace_id}" if langsmith_base else None
    return ATATraceInfo(trace_id=trace_id, langgraph_url=langgraph_url, langsmith_url=langsmith_url)


def trace_payload(trace: ATATraceInfo) -> dict[str, Any]:
    return {
        "trace_id": trace.trace_id,
        "langgraph_url": trace.langgraph_url,
        "langsmith_url": trace.langsmith_url,
    }
