from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8", errors="replace") or "{}")
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _get_env_int(name: str, default: int) -> int:
    v = os.environ.get(name)
    if v is None:
        return default
    v = str(v).strip()
    if not v:
        return default
    try:
        return int(v, 10)
    except Exception:
        return default


def _get_env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    s = str(v).strip().lower()
    if s in {"1", "true", "yes", "y", "on"}:
        return True
    if s in {"0", "false", "no", "n", "off"}:
        return False
    return default


@dataclass(frozen=True)
class SCCRuntimeConfig:
    base_url: str
    codex_model: str
    codex_timeout_s: int
    codex_max_outstanding_limit: int
    codex_dangerously_bypass_default: bool
    automation_max_outstanding: int
    automation_dangerously_bypass_default: bool
    executor_abandon_active_run_after_s: int
    patch_apply_enabled: bool
    workspace_write_lock_timeout_s: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "base_url": self.base_url,
            "codex": {
                "model": self.codex_model,
                "timeout_s": self.codex_timeout_s,
                "max_outstanding_limit": self.codex_max_outstanding_limit,
                "dangerously_bypass_default": self.codex_dangerously_bypass_default,
            },
            "automation": {
                "max_outstanding": self.automation_max_outstanding,
                "dangerously_bypass_default": self.automation_dangerously_bypass_default,
            },
            "executor": {
                "abandon_active_run_after_s": self.executor_abandon_active_run_after_s,
            },
            "scc": {
                "patch_apply_enabled": self.patch_apply_enabled,
                "workspace_write_lock_timeout_s": self.workspace_write_lock_timeout_s,
            },
        }


def load_runtime_config(*, repo_root: Optional[Path] = None) -> SCCRuntimeConfig:
    root = Path(repo_root).resolve() if repo_root is not None else _repo_root()
    cfg_path = (root / "configs" / "scc" / "runtime.v0.json").resolve()
    raw = _read_json(cfg_path) if cfg_path.exists() else {}
    defaults = raw.get("defaults") if isinstance(raw.get("defaults"), dict) else {}
    codex = defaults.get("codex") if isinstance(defaults.get("codex"), dict) else {}
    automation = defaults.get("automation") if isinstance(defaults.get("automation"), dict) else {}
    executor = defaults.get("executor") if isinstance(defaults.get("executor"), dict) else {}
    scc = defaults.get("scc") if isinstance(defaults.get("scc"), dict) else {}

    base_url = str(os.environ.get("SCC_BASE_URL") or defaults.get("base_url") or "http://127.0.0.1:18788").strip()
    codex_model = str(os.environ.get("A2A_CODEX_MODEL") or codex.get("model") or "gpt-5.2").strip()
    codex_timeout_s = _get_env_int("A2A_CODEX_TIMEOUT_SEC", int(codex.get("timeout_s") or 900))
    codex_max_outstanding_limit = _get_env_int("A2A_CODEX_MAX_OUTSTANDING_LIMIT", int(codex.get("max_outstanding_limit") or 4))
    codex_dangerously_bypass_default = _get_env_bool(
        "A2A_CODEX_DANGEROUSLY_BYPASS_DEFAULT",
        bool(codex.get("dangerously_bypass_default") or False),
    )

    automation_max_outstanding = _get_env_int("SCC_AUTOMATION_MAX_OUTSTANDING", int(automation.get("max_outstanding") or 3))
    automation_dangerously_bypass_default = _get_env_bool(
        "SCC_AUTOMATION_DANGEROUSLY_BYPASS",
        bool(automation.get("dangerously_bypass_default") or False),
    )

    executor_abandon_active_run_after_s = _get_env_int(
        "SCC_EXECUTOR_ABANDON_ACTIVE_RUN_AFTER_S",
        int(executor.get("abandon_active_run_after_s") or 21600),
    )

    patch_apply_enabled = _get_env_bool("SCC_PATCH_APPLY_ENABLED", bool(scc.get("patch_apply_enabled") or False))
    workspace_write_lock_timeout_s = _get_env_int(
        "SCC_WORKSPACE_WRITE_LOCK_TIMEOUT_S",
        int(scc.get("workspace_write_lock_timeout_s") or 300),
    )

    return SCCRuntimeConfig(
        base_url=base_url,
        codex_model=codex_model,
        codex_timeout_s=int(max(60, codex_timeout_s)),
        codex_max_outstanding_limit=int(max(1, codex_max_outstanding_limit)),
        codex_dangerously_bypass_default=bool(codex_dangerously_bypass_default),
        automation_max_outstanding=int(max(1, automation_max_outstanding)),
        automation_dangerously_bypass_default=bool(automation_dangerously_bypass_default),
        executor_abandon_active_run_after_s=int(max(300, executor_abandon_active_run_after_s)),
        patch_apply_enabled=bool(patch_apply_enabled),
        workspace_write_lock_timeout_s=int(max(5, workspace_write_lock_timeout_s)),
    )
