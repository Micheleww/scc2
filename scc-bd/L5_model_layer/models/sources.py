from __future__ import annotations

import json
import os
import pathlib
import subprocess
import time
import urllib.request
from typing import Any, Dict, List, Optional

from tools.scc.models.model_types import ModelCaps, ModelCost, ModelRecord


def _read_json(path: pathlib.Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8").lstrip("\ufeff"))


def load_codex_models_cache(path: Optional[pathlib.Path] = None) -> Dict[str, Any]:
    if path is None:
        path = pathlib.Path(os.environ.get("USERPROFILE", "~")).expanduser() / ".codex" / "models_cache.json"
    return _read_json(path)


def codex_models_from_cache(cache: Dict[str, Any]) -> List[ModelRecord]:
    out: List[ModelRecord] = []
    models = cache.get("models")
    if not isinstance(models, list):
        return out
    for m in models:
        if not isinstance(m, dict):
            continue
        slug = str(m.get("slug") or "").strip()
        if not slug:
            continue
        display = str(m.get("display_name") or slug)
        desc = str(m.get("description") or "")
        ctx = m.get("context_window") or m.get("context") or None
        ctx_i = int(ctx) if isinstance(ctx, int) else None
        caps = ModelCaps(
            toolcall=bool(m.get("supported_in_api", True)),  # best-effort; codex cache isn't a strict schema
            reasoning=bool(m.get("supports_reasoning_summaries", False)) or bool(m.get("supports_parallel_tool_calls", False)),
            vision=("image" in (m.get("input_modalities") or [])),
            temperature=True,
        )
        out.append(
            ModelRecord(
                canonical_id=f"codex/{slug}",
                source="codex",
                model_id=slug,
                display_name=display,
                description=desc,
                context_length=ctx_i,
                cost=ModelCost(),
                caps=caps,
                is_free=False,
                raw={
                    "visibility": m.get("visibility"),
                    "supported_in_api": m.get("supported_in_api"),
                    "default_reasoning_level": m.get("default_reasoning_level"),
                },
            )
        )
    return out


def load_opencode_models_cache(path: Optional[pathlib.Path] = None) -> Dict[str, Any]:
    if path is None:
        path = pathlib.Path(os.environ.get("USERPROFILE", "~")).expanduser() / ".cache" / "opencode" / "models.json"
    return _read_json(path)


def opencode_models_from_cache(cache: Dict[str, Any]) -> List[ModelRecord]:
    out: List[ModelRecord] = []
    if not isinstance(cache, dict):
        return out

    for provider_id, provider in cache.items():
        if not isinstance(provider, dict):
            continue
        models = provider.get("models")
        items: List[Dict[str, Any]] = []
        # Cache format varies by version:
        # - dict: { "<model_id>": { ...model... }, ... }
        # - list: [ { ...model... }, ... ]
        if isinstance(models, dict):
            for _, v in models.items():
                if isinstance(v, dict):
                    items.append(v)
        elif isinstance(models, list):
            for v in models:
                if isinstance(v, dict):
                    items.append(v)
        else:
            continue

        for m in items:
            if not isinstance(m, dict):
                continue
            mid = str(m.get("id") or "").strip()
            if not mid:
                continue
            name = str(m.get("name") or mid)
            limit_obj = m.get("limit") if isinstance(m.get("limit"), dict) else {}
            ctx = limit_obj.get("context") if isinstance(limit_obj, dict) else None
            ctx_i = int(ctx) if isinstance(ctx, int) else None
            cost_obj = m.get("cost") if isinstance(m.get("cost"), dict) else {}

            # Capabilities: cache may use either a nested object or flattened booleans.
            caps_obj = m.get("capabilities") if isinstance(m.get("capabilities"), dict) else {}
            toolcall = bool(caps_obj.get("toolcall", False)) if caps_obj else bool(m.get("tool_call", False))
            reasoning = bool(caps_obj.get("reasoning", False)) if caps_obj else bool(m.get("reasoning", False))
            temp = bool(caps_obj.get("temperature", False)) if caps_obj else bool(m.get("temperature", False))

            inp = caps_obj.get("input") if isinstance(caps_obj.get("input"), dict) else {}
            if inp:
                vision = bool(inp.get("image", False))
            else:
                modalities = m.get("modalities") if isinstance(m.get("modalities"), dict) else {}
                in_mod = modalities.get("input") if isinstance(modalities.get("input"), list) else []
                vision = "image" in in_mod
            cost = ModelCost(
                input=float(cost_obj.get("input")) if isinstance(cost_obj.get("input"), (int, float)) else None,
                output=float(cost_obj.get("output")) if isinstance(cost_obj.get("output"), (int, float)) else None,
                cache_read=float(cost_obj.get("cache_read")) if isinstance(cost_obj.get("cache_read"), (int, float)) else None,
                cache_write=float(cost_obj.get("cache_write")) if isinstance(cost_obj.get("cache_write"), (int, float)) else None,
            )
            is_free = (cost.input == 0 and cost.output == 0)
            # Opencode model ids are typically referenced as provider/model.
            canonical_id = f"opencode/{provider_id}/{mid}"
            out.append(
                ModelRecord(
                    canonical_id=canonical_id,
                    source="opencode",
                    model_id=f"{provider_id}/{mid}",
                    display_name=name,
                    description=str(m.get("family") or ""),
                    context_length=ctx_i,
                    cost=cost,
                    caps=ModelCaps(toolcall=toolcall, reasoning=reasoning, vision=vision, temperature=temp),
                    is_free=bool(is_free),
                    raw={
                        "providerID": provider_id,
                        "status": m.get("status"),
                        "release_date": m.get("release_date"),
                    },
                )
            )
    return out


def run_opencode_models_verbose(opencode_bin: str = "opencode", timeout_s: int = 90) -> str:
    # This is slower than reading the cache, but useful if you want the very latest.
    p = subprocess.run(
        [opencode_bin, "models", "--verbose"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_s,
        env=os.environ.copy(),
    )
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout or "opencode models failed").strip()[:2000])
    return p.stdout or ""


def now_iso() -> str:
    # Stable ISO without needing timezone dependencies.
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
