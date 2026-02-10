import test from "node:test"
import assert from "node:assert/strict"
import fs from "node:fs"
import os from "node:os"
import path from "node:path"

import {
  loadAuditTriggerState,
  loadFeedbackHookState,
  loadFlowManagerState,
  saveAuditTriggerState,
  saveFeedbackHookState,
  saveFlowManagerState,
} from "../../L9_state_layer/state_stores/flow_state_store.mjs"

test("flow_state_store load/save", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "scc-flow-"))
  const a = path.join(dir, "audit.json")
  const f = path.join(dir, "flow.json")
  const h = path.join(dir, "hook.json")

  const a0 = loadAuditTriggerState({ file: a })
  assert.equal(a0.total_done, 0)
  saveAuditTriggerState({ file: a, state: { ...a0, total_done: 12 }, strictWrites: true })
  assert.equal(loadAuditTriggerState({ file: a }).total_done, 12)

  const f0 = loadFlowManagerState({ file: f })
  assert.equal(f0.last_created_at, 0)
  saveFlowManagerState({ file: f, state: { last_created_at: 123, last_reasons_key: "k" }, strictWrites: true })
  assert.equal(loadFlowManagerState({ file: f }).last_reasons_key, "k")

  const h0 = loadFeedbackHookState({ file: h })
  assert.ok(typeof h0.last_created_at === "object")
  saveFeedbackHookState({ file: h, state: { last_created_at: { x: 1 } }, strictWrites: true })
  assert.equal(loadFeedbackHookState({ file: h }).last_created_at.x, 1)
})

