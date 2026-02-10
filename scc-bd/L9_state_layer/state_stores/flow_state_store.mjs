import { readJson, updateJsonLocked } from "./state_store.mjs"

function loadAuditTriggerState({ file }) {
  const fallback = {
    done_since_last: 0,
    total_done: 0,
    last_audit_at: null,
    last_audit_batch: null,
    last_audit_task_id: null,
  }
  const parsed = readJson(file, null)
  if (!parsed || typeof parsed !== "object") return fallback
  return {
    done_since_last: Number(parsed.done_since_last ?? 0),
    total_done: Number(parsed.total_done ?? 0),
    last_audit_at: parsed.last_audit_at ?? null,
    last_audit_batch: parsed.last_audit_batch ?? null,
    last_audit_task_id: parsed.last_audit_task_id ?? null,
  }
}

function saveAuditTriggerState({ file, state, strictWrites }) {
  try {
    updateJsonLocked(file, {}, () => state, { lockTimeoutMs: 6000 })
  } catch (e) {
    if (strictWrites) throw e
  }
}

function loadFlowManagerState({ file }) {
  const fallback = { last_created_at: 0, last_reasons_key: null }
  const parsed = readJson(file, null)
  if (!parsed || typeof parsed !== "object") return fallback
  return { last_created_at: Number(parsed.last_created_at ?? 0), last_reasons_key: parsed.last_reasons_key ?? null }
}

function saveFlowManagerState({ file, state, strictWrites }) {
  try {
    updateJsonLocked(file, {}, () => state, { lockTimeoutMs: 6000 })
  } catch (e) {
    if (strictWrites) throw e
  }
}

function loadFeedbackHookState({ file }) {
  const fallback = { last_created_at: {} }
  const parsed = readJson(file, null)
  if (!parsed || typeof parsed !== "object") return fallback
  const last = parsed.last_created_at && typeof parsed.last_created_at === "object" ? parsed.last_created_at : {}
  return { last_created_at: last }
}

function saveFeedbackHookState({ file, state, strictWrites }) {
  try {
    updateJsonLocked(file, {}, () => state, { lockTimeoutMs: 6000 })
  } catch (e) {
    if (strictWrites) throw e
  }
}

export {
  loadAuditTriggerState,
  loadFeedbackHookState,
  loadFlowManagerState,
  saveAuditTriggerState,
  saveFeedbackHookState,
  saveFlowManagerState,
}

