from __future__ import annotations

from typing import Dict

from tools.scc.orchestrators.cc_orchestrator_v0 import CCLikeOrchestratorV0
from tools.scc.orchestrators.interface import Orchestrator


def get_builtin_orchestrators() -> Dict[str, Orchestrator]:
    orch = CCLikeOrchestratorV0()
    return {orch.name: orch}


def resolve_orchestrator(name: str) -> Orchestrator:
    key = str(name or "").strip() or "cc_like_v0"
    orch = get_builtin_orchestrators().get(key)
    if not orch:
        raise ValueError(f"unknown_orchestrator: {key}")
    return orch

