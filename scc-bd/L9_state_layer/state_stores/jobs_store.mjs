import { readJson, updateJsonLocked } from "./state_store.mjs"

function loadJobsState({ file }) {
  const parsed = readJson(file, null)
  if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
    return parsed
  }
  // Return default structure
  return { jobs: {}, updatedAt: Date.now() }
}

function saveJobsState({ file, state, strictWrites }) {
  try {
    state.updatedAt = Date.now()
    updateJsonLocked(file, { jobs: {} }, () => state, { lockTimeoutMs: 6000 })
  } catch (e) {
    if (strictWrites) throw e
  }
}

export { loadJobsState, saveJobsState }

