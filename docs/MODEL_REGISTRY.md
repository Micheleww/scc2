# Model Registry + Router

This repo maintains a normalized model registry under `artifacts/model_registry/` so SCC tasks can route between paid and free models based on task difficulty.

## Sync

```powershell
cd c:\scc
python -m tools.scc.models sync
```

Outputs:
- `artifacts/model_registry/codex_models.json`
- `artifacts/model_registry/opencode_models.json`
- `artifacts/model_registry/opencode_free_models.json`
- `artifacts/model_registry/openrouter_models.json`
- `artifacts/model_registry/openrouter_free_models.json`
- `artifacts/model_registry/all_models.json`
- `artifacts/model_registry/all_free_models.json`

OpenRouter requires `OPENROUTER_API_KEY` (or pass `--openrouter-key`).

## Route

```powershell
python -m tools.scc.models route --difficulty easy --prefer-free --hint "fix small bug"
python -m tools.scc.models route --difficulty hard --hint "large refactor"
```

## One-Off Calls (Optional)

```powershell
# OpenRouter direct
python -m tools.scc.models chat --provider openrouter --model "qwen/qwen3-coder:free" --message "hi"

# Codex CLI (uses your codex login; read-only sandbox)
python -m tools.scc.models chat --provider codex --model "gpt-5.2-codex" --message "hi"

# OpenCode CLI
python -m tools.scc.models chat --provider opencodecli --model "openrouter/qwen/qwen3-coder:free" --message "hi"
```

