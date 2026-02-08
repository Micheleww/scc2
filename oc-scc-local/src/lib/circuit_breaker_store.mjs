import { readJson, updateJsonLocked } from "./state_store.mjs"

function loadCircuitBreakerState({ file }) {
  const fallback = { schema_version: "scc.circuit_breaker_state.v1", updated_at: new Date().toISOString(), breakers: {}, quarantine_until: 0 }
  const parsed = readJson(file, null)
  if (!parsed || typeof parsed !== "object") return fallback
  return {
    schema_version: "scc.circuit_breaker_state.v1",
    updated_at: parsed.updated_at ?? new Date().toISOString(),
    breakers: parsed.breakers && typeof parsed.breakers === "object" ? parsed.breakers : {},
    quarantine_until: Number(parsed.quarantine_until ?? 0) || 0,
    quarantine_reason: parsed.quarantine_reason ?? null,
    quarantine_breaker: parsed.quarantine_breaker ?? null,
  }
}

function saveCircuitBreakerState({ file, state, strictWrites }) {
  try {
    updateJsonLocked(file, {}, () => state, { lockTimeoutMs: 6000 })
  } catch (e) {
    if (strictWrites) throw e
  }
}

function quarantineActive(state, nowMs = Date.now()) {
  const until = Number(state?.quarantine_until ?? 0)
  return Number.isFinite(until) && until > 0 && nowMs < until
}

export { loadCircuitBreakerState, saveCircuitBreakerState, quarantineActive }

