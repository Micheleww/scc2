import { readJson, updateJsonLocked } from "./state_store.mjs"

function loadJobsState({ file }) {
  const parsed = readJson(file, null)
  return Array.isArray(parsed) ? parsed : []
}

function saveJobsState({ file, jobsArray, strictWrites }) {
  try {
    updateJsonLocked(file, [], () => jobsArray, { lockTimeoutMs: 6000 })
  } catch (e) {
    if (strictWrites) throw e
  }
}

export { loadJobsState, saveJobsState }

