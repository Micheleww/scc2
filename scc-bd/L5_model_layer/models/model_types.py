from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class ModelCost:
    # Cost is kept provider-native. For opencode models it is typically $/1M tokens.
    input: Optional[float] = None
    output: Optional[float] = None
    cache_read: Optional[float] = None
    cache_write: Optional[float] = None


@dataclass(frozen=True)
class ModelCaps:
    toolcall: bool = False
    reasoning: bool = False
    vision: bool = False
    temperature: bool = False


@dataclass(frozen=True)
class ModelRecord:
    # Canonical id is "<source>/<model_id>"
    canonical_id: str
    source: str  # codex | opencode
    model_id: str
    display_name: str = ""
    description: str = ""
    context_length: Optional[int] = None
    cost: ModelCost = field(default_factory=ModelCost)
    caps: ModelCaps = field(default_factory=ModelCaps)
    is_free: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)

