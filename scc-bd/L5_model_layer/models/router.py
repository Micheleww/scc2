from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

from tools.scc.models.model_types import ModelRecord

import re
import os


@dataclass(frozen=True)
class RouteRequest:
    difficulty: str  # easy | medium | hard
    task_hint: str = ""
    prefer_free: bool = True
    need_tools: bool = False
    need_vision: bool = False
    min_context: int = 0
    allow_sources: Optional[Tuple[str, ...]] = None  # e.g. ("opencode","codex")


def _score_model(req: RouteRequest, m: ModelRecord) -> float:
    # Higher is better.
    s = 0.0

    if req.allow_sources and m.source not in req.allow_sources:
        return -1e9

    # Avoid routing to local providers by default (they require extra services running).
    if m.source == "opencode":
        prov = str((m.raw or {}).get("providerID") or "").strip().lower()
        if prov in {"lmstudio", "ollama", "ollama-chat"} and os.environ.get("SCC_ALLOW_LOCAL_LLM", "").strip() not in {"1", "true", "yes"}:
            return -1e9

    if req.need_tools and not m.caps.toolcall:
        return -1e9
    if req.need_vision and not m.caps.vision:
        return -1e9
    if req.min_context and (m.context_length or 0) < req.min_context:
        return -1e9

    # Prefer free when asked.
    if req.prefer_free:
        s += 50.0 if m.is_free else -10.0
    else:
        s += 5.0 if not m.is_free else 0.0

    # Difficulty heuristic: hard -> prefer codex/openai-class, easy -> free.
    if req.difficulty == "hard":
        if m.source == "codex":
            s += 40.0
        if "gpt-5" in m.model_id:
            s += 10.0
        if "codex" in m.model_id:
            s += 10.0
    elif req.difficulty == "medium":
        if m.source in {"codex", "opencode"}:
            s += 10.0
    else:
        # easy
        if m.is_free:
            s += 10.0

    hint = (req.task_hint or "").lower()
    if any(k in hint for k in ["code", ".ts", ".js", ".py", "bug", "diff", "patch", "修复", "代码"]):
        if "coder" in (m.model_id or "").lower():
            s += 20.0
        if "codex" in (m.model_id or "").lower():
            s += 15.0
    if any(k in hint for k in ["math", "proof", "推理", "reason"]):
        if m.caps.reasoning:
            s += 10.0

    # Tie-break: larger context is better.
    if m.context_length:
        s += min(30.0, float(m.context_length) / 100000.0 * 10.0)

    # Avoid giant models for easy/medium unless explicitly needed.
    if req.difficulty in {"easy", "medium"}:
        mid = ((m.model_id or "") + " " + (m.display_name or "")).lower()
        # Common patterns: "480b", "120b", "70b", etc.
        mm = re.search(r"(\d+)\s*b", mid)
        if mm:
            try:
                b = int(mm.group(1))
                if b >= 120:
                    s -= 15.0
                elif b >= 70:
                    s -= 8.0
            except Exception:
                pass

    # Tie-break: cheaper is slightly better when not hard.
    if req.difficulty != "hard" and m.cost.input is not None and m.cost.output is not None:
        if m.cost.input == 0 and m.cost.output == 0:
            s += 5.0
        else:
            s -= min(5.0, float(m.cost.input + m.cost.output))

    return s


def choose_model(req: RouteRequest, models: Iterable[ModelRecord]) -> ModelRecord:
    ranked: List[Tuple[float, ModelRecord]] = []
    for m in models:
        ranked.append((_score_model(req, m), m))
    ranked.sort(key=lambda x: x[0], reverse=True)
    if not ranked or ranked[0][0] <= -1e8:
        raise RuntimeError("no eligible model for request")
    return ranked[0][1]
