from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ServiceRegistryConfig:
    raw: dict[str, Any]
    path: Path


def load_service_registry_config(*, repo_root: Path) -> ServiceRegistryConfig | None:
    """
    Load the canonical service registry config.

    This is used for:
    - single-entrypoint governance (Desktop/DEV)
    - port reference audits
    - client tooling (discoverability)
    """
    cfg_path = (repo_root / "configs" / "unified_server" / "service_registry.v0.json").resolve()
    if not cfg_path.exists():
        return None
    raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("service_registry config must be a JSON object")
    return ServiceRegistryConfig(raw=raw, path=cfg_path)

