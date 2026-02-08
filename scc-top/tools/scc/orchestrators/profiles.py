from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any, Dict, Literal, Optional


OrchestratorMode = Literal["plan", "chat", "fullagent"]


@dataclass(frozen=True)
class OrchestratorProfile:
    """
    SCC Orchestrator profile (aka "挡位").

    This is *not* a model config; it is a policy bundle that controls:
    - whether model calls are allowed
    - whether running shell commands is allowed
    - maximum agent steps
    """

    name: OrchestratorMode
    description: str
    model_calls_allowed: bool
    shell_allowed: bool
    max_steps: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def model_calls_globally_enabled() -> bool:
    return (os.environ.get("SCC_MODEL_ENABLED", "false").strip().lower() == "true")


def get_builtin_profiles() -> Dict[str, OrchestratorProfile]:
    """
    Built-in SCC profiles.

    - plan: deterministic planning only (no model, no shell)
    - chat: interactive planning scaffold (no model, no shell) — placeholder for future chat UX
    - fullagent: model-driven loop + tools (model gated by SCC_MODEL_ENABLED)
    """
    model_ok = model_calls_globally_enabled()
    return {
        "plan": OrchestratorProfile(
            name="plan",
            description="Plan-only (dry-run): build plan/todos/state, no model, no shell.",
            model_calls_allowed=False,
            shell_allowed=False,
            max_steps=8,
        ),
        "chat": OrchestratorProfile(
            name="chat",
            description="Chat scaffold (dry-run): store messages/plan/todos, no model, no shell.",
            model_calls_allowed=False,
            shell_allowed=False,
            max_steps=12,
        ),
        "fullagent": OrchestratorProfile(
            name="fullagent",
            description="Full agent loop (model + tools). Model calls gated by SCC_MODEL_ENABLED.",
            model_calls_allowed=model_ok,
            shell_allowed=model_ok,
            max_steps=64,
        ),
    }


def resolve_profile(name: Optional[str]) -> OrchestratorProfile:
    profiles = get_builtin_profiles()
    key = (name or "plan").strip().lower()
    if key not in profiles:
        raise ValueError(f"unknown_profile: {key}")
    return profiles[key]

