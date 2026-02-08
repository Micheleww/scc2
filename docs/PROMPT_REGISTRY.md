# Prompt Registry (SSOT for Prompts)

Goal: treat prompts as versioned, composable, auditable assets (not ad-hoc strings inside code).

## Where It Lives
- Registry file: `C:/scc/oc-scc-local/prompts/registry.json`
- Blocks directory: `C:/scc/oc-scc-local/prompts/blocks/`
- Renderer: `C:/scc/oc-scc-local/src/prompt_registry.mjs`
- Integration (gateway): `C:/scc/oc-scc-local/src/gateway.mjs`

## Composition Model
- A prompt is built from `blocks[]` (text or json), then rendered with `params` (e.g. `{{batch_id}}`).
- Each `role_id` in the registry defines:
  - `render_kind`: `text` or `json_string`
  - `composition.blocks`: ordered block list
  - optional `defaults`, `required_params`

## Auditability
- Each render produces a `prompt_ref` containing:
  - `registry_version`, `role_id`, `blocks[]`
  - `rendered_sha256`, `rendered_bytes`, `rendered_at`
- Gateway writes `prompt_ref` into `artifacts/executor_logs/jobs.jsonl` per finished job.

## Endpoints
- `GET /prompts/registry` - list registry metadata (blocks/roles/presets).
- `POST /prompts/render` - debug render (local): `{ role_id, preset_id?, params:{} }`.

## Governance Rules (Operational)
- Prefer `src` blocks (files) for long prompts; avoid embedding large text directly in JSON.
- Keep blocks small and reusable; do not duplicate long constraints in many places.
- Changes should be semver bumps in `registry_version` and block `version`.
- Default policy: blocks must be `status=active` to be used (fail-closed).

