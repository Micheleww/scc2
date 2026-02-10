import test from "node:test"
import assert from "node:assert/strict"
import fs from "node:fs"
import os from "node:os"
import path from "node:path"

import { loadCircuitBreakerState, quarantineActive, saveCircuitBreakerState } from "../../L13_security_layer/circuit_breaker/circuit_breaker_store.mjs"

test("circuit_breaker_store load/save + quarantineActive", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "scc-cb-"))
  const file = path.join(dir, "cb.json")

  let st = loadCircuitBreakerState({ file })
  assert.equal(st.schema_version, "scc.circuit_breaker_state.v1")
  assert.equal(quarantineActive(st, Date.now()), false)

  st = { ...st, quarantine_until: Date.now() + 50_000, quarantine_reason: "x" }
  saveCircuitBreakerState({ file, state: st, strictWrites: true })

  const st2 = loadCircuitBreakerState({ file })
  assert.equal(st2.quarantine_reason, "x")
  assert.equal(quarantineActive(st2, Date.now()), true)
})

