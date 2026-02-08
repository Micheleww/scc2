from __future__ import annotations

import os
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

import requests


def _get_base_url() -> str:
    base = (os.environ.get("UNIFIED_SERVER_BASE_URL") or "").strip()
    if base:
        return base.rstrip("/")
    host = (os.environ.get("UNIFIED_SERVER_HOST") or "127.0.0.1").strip() or "127.0.0.1"
    port = (os.environ.get("UNIFIED_SERVER_PORT") or "18788").strip() or "18788"
    return f"http://{host}:{port}"


@dataclass(frozen=True)
class ExecutorResult:
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    executor: str
    reason_code: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def run_executor_prompt(
    *,
    executor: str,
    prompt: str,
    model: str = "",
    timeout_s: float = 900,
    trace_id: Optional[str] = None,
) -> ExecutorResult:
    """
    Thin HTTP client for unified-server `/executor/*` endpoints.

    Safety note:
    - This function does not enforce any permission policy; SCC orchestrators must gate
      model usage (SCC_MODEL_ENABLED) and tool execution separately.
    """
    url = _get_base_url() + f"/executor/{executor}"
    headers = {
        "Content-Type": "application/json",
        "X-Trace-ID": trace_id or f"scc-exec-{executor}-{int(time.time())}",
    }
    payload: Dict[str, Any] = {"prompt": prompt}
    if model:
        payload["model"] = model
    r = requests.post(url, headers=headers, json=payload, timeout=max(1, int(timeout_s)))
    r.raise_for_status()
    data = r.json()
    return ExecutorResult(
        success=bool(data.get("success")),
        exit_code=int(data.get("exit_code") or 0),
        stdout=str(data.get("stdout") or ""),
        stderr=str(data.get("stderr") or ""),
        executor=str(data.get("executor") or executor),
        reason_code=str(data.get("reason_code") or ""),
    )

