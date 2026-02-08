import { readJson, updateJsonLocked } from "./state_store.mjs"

function loadRepoHealthState({ file }) {
  const fallback = {
    schema_version: "scc.repo_health_state.v1",
    updated_at: new Date().toISOString(),
    failures: [],
    unhealthy_until: 0,
    unhealthy_reason: null,
    unhealthy_task_created_at: null,
  }
  const parsed = readJson(file, null)
  if (!parsed || typeof parsed !== "object") return fallback
  const failures = Array.isArray(parsed?.failures) ? parsed.failures.map((x) => Number(x)).filter((n) => Number.isFinite(n) && n > 0) : []
  return {
    schema_version: "scc.repo_health_state.v1",
    updated_at: parsed?.updated_at ?? new Date().toISOString(),
    failures,
    unhealthy_until: Number(parsed?.unhealthy_until ?? 0) || 0,
    unhealthy_reason: parsed?.unhealthy_reason ?? null,
    unhealthy_task_created_at: parsed?.unhealthy_task_created_at ?? null,
  }
}

function saveRepoHealthState({ file, state, strictWrites }) {
  try {
    updateJsonLocked(file, {}, () => state, { lockTimeoutMs: 6000 })
  } catch (e) {
    if (strictWrites) throw e
  }
}

function repoUnhealthyActive(state, nowMs = Date.now()) {
  const until = Number(state?.unhealthy_until ?? 0)
  return Number.isFinite(until) && until > 0 && nowMs < until
}

export { loadRepoHealthState, saveRepoHealthState, repoUnhealthyActive }

