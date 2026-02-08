import { readJson, writeJsonAtomic, updateJsonLocked } from "./state_store.mjs"

const BOARD_STATUS = ["backlog", "needs_split", "ready", "in_progress", "blocked", "done", "failed"]
const BOARD_LANES = ["fastlane", "mainlane", "batchlane", "quarantine", "dlq"]

function normalizeBoardStatus(v) {
  const s = String(v ?? "").trim()
  return BOARD_STATUS.includes(s) ? s : null
}

function normalizeLane(v) {
  const s = String(v ?? "").trim()
  return BOARD_LANES.includes(s) ? s : null
}

function lanePriorityScore(lane, factoryPolicy) {
  const l = normalizeLane(lane) ?? "mainlane"
  const fromPolicy = factoryPolicy?.lanes?.[l]?.priority
  const p = Number(fromPolicy)
  if (Number.isFinite(p)) return Math.floor(p) * 10
  if (l === "fastlane") return 900
  if (l === "mainlane") return 500
  if (l === "batchlane") return 100
  if (l === "quarantine") return 50
  if (l === "dlq") return 0
  return 500
}

function computeJobPriorityForTask(task, factoryPolicy) {
  const base = lanePriorityScore(task?.lane, factoryPolicy)
  const extra = Number.isFinite(Number(task?.priority)) ? Number(task.priority) : 0
  return base + extra
}

function loadMission({ missionFile, gatewayPort }) {
  const fallback = {
    id: "mission",
    title: "SCC automated code factory",
    goal: "SCC becomes a fully automated code-generation factory. Current parent task: SCC x OpenCode fusion.",
    statusDocUrl: `http://127.0.0.1:${gatewayPort}/docs/STATUS.md`,
    worklogUrl: `http://127.0.0.1:${gatewayPort}/docs/WORKLOG.md`,
    missionDocUrl: `http://127.0.0.1:${gatewayPort}/docs/MISSION.md`,
    updatedAt: Date.now(),
  }
  const parsed = readJson(missionFile, null)
  return { ...fallback, ...(parsed && typeof parsed === "object" ? parsed : {}) }
}

function saveMission({ missionFile, mission, strictWrites }) {
  try {
    writeJsonAtomic(missionFile, mission)
  } catch (e) {
    if (strictWrites) throw e
  }
}

function loadBoard({ boardFile }) {
  const parsed = readJson(boardFile, null)
  return Array.isArray(parsed) ? parsed : []
}

function saveBoard({ boardFile, tasksArray, strictWrites }) {
  try {
    updateJsonLocked(boardFile, [], () => tasksArray, { lockTimeoutMs: 6000 })
  } catch (e) {
    if (strictWrites) throw e
  }
}

export {
  BOARD_LANES,
  BOARD_STATUS,
  computeJobPriorityForTask,
  lanePriorityScore,
  loadBoard,
  loadMission,
  normalizeBoardStatus,
  normalizeLane,
  saveBoard,
  saveMission,
}

