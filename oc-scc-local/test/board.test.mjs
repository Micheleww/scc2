import test from "node:test"
import assert from "node:assert/strict"
import fs from "node:fs"
import os from "node:os"
import path from "node:path"

import { computeJobPriorityForTask, loadBoard, loadMission, normalizeLane, saveBoard, saveMission } from "../src/lib/board.mjs"

test("normalizeLane only accepts known lanes", () => {
  assert.equal(normalizeLane("mainlane"), "mainlane")
  assert.equal(normalizeLane("nope"), null)
})

test("computeJobPriorityForTask uses lane defaults", () => {
  const p = computeJobPriorityForTask({ lane: "fastlane" }, null)
  assert.ok(p >= 900)
})

test("mission + board persistence", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "scc-board-"))
  const missionFile = path.join(dir, "mission.json")
  const boardFile = path.join(dir, "tasks.json")

  const m0 = loadMission({ missionFile, gatewayPort: 18788 })
  assert.equal(m0.id, "mission")

  saveMission({ missionFile, mission: { id: "mission", title: "t" }, strictWrites: true })
  const m1 = loadMission({ missionFile, gatewayPort: 18788 })
  assert.equal(m1.title, "t")

  saveBoard({ boardFile, tasksArray: [{ id: "1", status: "ready" }], strictWrites: true })
  const b1 = loadBoard({ boardFile })
  assert.equal(b1.length, 1)
  assert.equal(b1[0].id, "1")
})

