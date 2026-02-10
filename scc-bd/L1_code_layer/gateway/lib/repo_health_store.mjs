import { readJson, updateJsonLocked } from "../../../L9_state_layer/state_stores/state_store.mjs"

function loadRepoHealthState({ file }) {
  const fallback = { 
    schema_version: "scc.repo_health_state.v1", 
    updated_at: new Date().toISOString(), 
    failures: [], 
    unhealthy_until: 0,
    unhealthy_reason: null,
    unhealthy_task_created_at: null 
  }
  const parsed = readJson(file, null)
  if (!parsed || typeof parsed !== "object") return fallback
  return {
    schema_version: "scc.repo_health_state.v1",
    updated_at: parsed.updated_at ?? new Date().toISOString(),
    failures: Array.isArray(parsed.failures) ? parsed.failures : [],
    unhealthy_until: Number(parsed.unhealthy_until ?? 0) || 0,
    unhealthy_reason: parsed.unhealthy_reason ?? null,
    unhealthy_task_created_at: parsed.unhealthy_task_created_at ?? null,
  }
}

function saveRepoHealthState({ file, state, strictWrites }) {
  try {
    updateJsonLocked(file, {}, () => state, { lockTimeoutMs: 6000 })
  } catch (e) {
    if (strictWrites) throw e
  }
}

function repoUnhealthyActive({ state, nowMs }) {
  const until = Number(state?.unhealthy_until ?? 0)
  if (!until) return false
  return nowMs ? nowMs < until : Date.now() < until
}

export { loadRepoHealthState, saveRepoHealthState, repoUnhealthyActive }
