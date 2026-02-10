from __future__ import annotations

import argparse
import json
import os
import pathlib
from typing import Any, Dict, List

from tools.scc.models.adapters import ChatMessage, codex_cli_chat_completion, opencode_cli_chat_completion
from tools.scc.models.router import RouteRequest, choose_model
from tools.scc.models.sources import (
    codex_models_from_cache,
    load_codex_models_cache,
    load_opencode_models_cache,
    now_iso,
    opencode_models_from_cache,
)
from tools.scc.models.model_types import ModelRecord


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


def _write_json(path: pathlib.Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _to_jsonable_model(m: ModelRecord) -> Dict[str, Any]:
    return {
        "canonical_id": m.canonical_id,
        "source": m.source,
        "model_id": m.model_id,
        "display_name": m.display_name,
        "description": m.description,
        "context_length": m.context_length,
        "is_free": m.is_free,
        "cost": {
            "input": m.cost.input,
            "output": m.cost.output,
            "cache_read": m.cost.cache_read,
            "cache_write": m.cost.cache_write,
        },
        "caps": {
            "toolcall": m.caps.toolcall,
            "reasoning": m.caps.reasoning,
            "vision": m.caps.vision,
            "temperature": m.caps.temperature,
        },
        "raw": m.raw,
    }


def sync_registry() -> Dict[str, Any]:
    codex_cache = load_codex_models_cache()
    codex_models = codex_models_from_cache(codex_cache)

    opencode_cache = load_opencode_models_cache()
    opencode_models = opencode_models_from_cache(opencode_cache)

    all_models = [*codex_models, *opencode_models]
    free_models = [m for m in all_models if m.is_free]

    out_dir = REPO_ROOT / "artifacts" / "model_registry"
    _write_json(out_dir / "codex_models.json", {"t": now_iso(), "count": len(codex_models), "models": [_to_jsonable_model(m) for m in codex_models]})
    _write_json(out_dir / "opencode_models.json", {"t": now_iso(), "count": len(opencode_models), "models": [_to_jsonable_model(m) for m in opencode_models]})
    _write_json(out_dir / "opencode_free_models.json", {"t": now_iso(), "count": len([m for m in opencode_models if m.is_free]), "models": [_to_jsonable_model(m) for m in opencode_models if m.is_free]})
    _write_json(out_dir / "all_models.json", {"t": now_iso(), "count": len(all_models), "models": [_to_jsonable_model(m) for m in all_models]})
    _write_json(out_dir / "all_free_models.json", {"t": now_iso(), "count": len(free_models), "models": [_to_jsonable_model(m) for m in free_models]})

    return {"codex": len(codex_models), "opencode": len(opencode_models), "free_total": len(free_models)}


def _load_all_models_from_artifacts() -> List[ModelRecord]:
    # This keeps runtime simple: sync first, then route using the normalized json.
    p = REPO_ROOT / "artifacts" / "model_registry" / "all_models.json"
    obj = json.loads(p.read_text(encoding="utf-8"))
    ms = obj.get("models")
    if not isinstance(ms, list):
        return []
    out: List[ModelRecord] = []
    from tools.scc.models.model_types import ModelCaps, ModelCost, ModelRecord

    for m in ms:
        if not isinstance(m, dict):
            continue
        out.append(
            ModelRecord(
                canonical_id=str(m.get("canonical_id") or ""),
                source=str(m.get("source") or ""),
                model_id=str(m.get("model_id") or ""),
                display_name=str(m.get("display_name") or ""),
                description=str(m.get("description") or ""),
                context_length=m.get("context_length") if isinstance(m.get("context_length"), int) else None,
                is_free=bool(m.get("is_free", False)),
                cost=ModelCost(
                    input=m.get("cost", {}).get("input"),
                    output=m.get("cost", {}).get("output"),
                    cache_read=m.get("cost", {}).get("cache_read"),
                    cache_write=m.get("cost", {}).get("cache_write"),
                ),
                caps=ModelCaps(
                    toolcall=bool(m.get("caps", {}).get("toolcall", False)),
                    reasoning=bool(m.get("caps", {}).get("reasoning", False)),
                    vision=bool(m.get("caps", {}).get("vision", False)),
                    temperature=bool(m.get("caps", {}).get("temperature", False)),
                ),
                raw=m.get("raw") if isinstance(m.get("raw"), dict) else {},
            )
        )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Unified model registry + router for SCC.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("sync", help="Sync model registry (codex/opencode caches) into artifacts/")

    rp = sub.add_parser("route", help="Choose a model for a task request using the synced registry")
    rp.add_argument("--difficulty", choices=["easy", "medium", "hard"], default="easy")
    rp.add_argument("--hint", default="", help="Free-text hint (goal/title) used for routing heuristics")
    rp.add_argument("--prefer-free", action="store_true", help="Prefer free models when possible")
    rp.add_argument("--need-tools", action="store_true")
    rp.add_argument("--need-vision", action="store_true")
    rp.add_argument("--min-context", type=int, default=0)
    rp.add_argument("--allow-sources", default="", help="Comma-separated sources: opencode,codex")

    cp = sub.add_parser("chat", help="Send a single message to a model via codex/opencode")
    cp.add_argument("--provider", choices=["codex", "opencodecli"], required=True)
    cp.add_argument("--model", required=True, help="Model id (provider-specific)")
    cp.add_argument("--message", required=True)
    cp.add_argument("--codex-bin", default="codex")
    cp.add_argument("--opencode-bin", default="opencode")

    args = ap.parse_args()

    if args.cmd == "sync":
        counts = sync_registry()
        print(json.dumps({"ok": True, "t": now_iso(), "counts": counts}, ensure_ascii=False))
        return 0

    if args.cmd == "route":
        models = _load_all_models_from_artifacts()
        allow_sources = tuple([s.strip() for s in str(args.allow_sources or "").split(",") if s.strip()]) or None
        req = RouteRequest(
            difficulty=str(args.difficulty),
            task_hint=str(args.hint or ""),
            prefer_free=bool(args.prefer_free),
            need_tools=bool(args.need_tools),
            need_vision=bool(args.need_vision),
            min_context=int(args.min_context or 0),
            allow_sources=allow_sources,
        )
        chosen = choose_model(req, models)
        print(json.dumps({"ok": True, "request": req.__dict__, "chosen": _to_jsonable_model(chosen)}, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "chat":
        provider = str(args.provider)
        model = str(args.model)
        msg = str(args.message)
        if provider == "codex":
            text = codex_cli_chat_completion(str(args.codex_bin), model, msg, cwd=REPO_ROOT)
            print(text)
            return 0
        if provider == "opencodecli":
            text = opencode_cli_chat_completion(str(args.opencode_bin), model, msg, cwd=REPO_ROOT)
            print(text)
            return 0
        raise SystemExit("unknown provider")


if __name__ == "__main__":
    raise SystemExit(main())
