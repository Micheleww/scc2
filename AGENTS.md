# SCC Agents Instructions (c:\scc)

## Entry Point
- System navigation entrypoint: `scc-top/docs/START_HERE.md`
- Navigation pins index (P0/P1 pins and start_here references): `docs/core_navigation_pins.md`

## Hard Rules (Fail-Closed)
1. **No execution without a rendered Context Pack**: any task execution MUST be preceded by rendering a slot-based Context Pack v1 and writing it to disk.
2. **Legal semantics come from slots, not paths**: “priority/effectiveness/order” is determined by Context Pack slot order (`SLOT0..SLOT6`), not by document folder structure.
3. **No repo scanning for authority**: authoritative inputs MUST be explicit versioned refs (path + version + sha256) carried in `SLOT1 BINDING_REFS`.
4. **Out-of-scope read/write is a hard failure**: execution must stay within the allowlisted scope from the task bundle/pins; attempts to bypass guards are FAIL.

## Context Pack v1 (Slot-Based)
Fixed slots (order is binding):
- `SLOT0 LEGAL_PREFIX` (always-on)
- `SLOT1 BINDING_REFS` (always-on, versioned + hashed)
- `SLOT2 ROLE_CAPSULE` (conditional)
- `SLOT3 TASK_BUNDLE` (conditional, required for execution)
- `SLOT4 STATE` (conditional)
- `SLOT5 TOOLS` (conditional)
- `SLOT6 OPTIONAL_CONTEXT` (conditional, **non-binding**)

## API (Gateway 18788)
- Render: `POST /scc/context/render` with `{ "task_id": "...", "role": "executor", "mode": "execute", "budget_tokens": 4000 }`
- Fetch: `GET /scc/context/pack/{context_pack_id}` (append `?format=txt` for text form)
- Validate: `POST /scc/context/validate` with `{ "context_pack_id": "..." }` or `{ "pack": { ... } }`

## Run Output Layout
Rendered Context Pack MUST be written under:
- `artifacts/scc_runs/<run_id>/rendered_context_pack.json`
- `artifacts/scc_runs/<run_id>/rendered_context_pack.txt`
- `artifacts/scc_runs/<run_id>/meta.json`

## Document Layer vs Pack Layer
- Document layer: `docs/**` (content, SSOT, manuals)
- Pack layer: `docs/context_pack/**` (protocol/spec/schemas/templates for rendering and validation)
- Runtime pack outputs: `artifacts/scc_runs/**` (rendered packs, run metadata)

