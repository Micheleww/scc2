import test from "node:test"
import assert from "node:assert/strict"
import fs from "node:fs"
import os from "node:os"
import path from "node:path"

import { loadRepoHealthState, repoUnhealthyActive, saveRepoHealthState } from "../src/lib/repo_health_store.mjs"

test("repo_health_store load/save + repoUnhealthyActive", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "scc-rh-"))
  const file = path.join(dir, "rh.json")

  let st = loadRepoHealthState({ file })
  assert.equal(st.schema_version, "scc.repo_health_state.v1")
  assert.equal(repoUnhealthyActive(st, Date.now()), false)

  st = { ...st, failures: [1, 2, 3], unhealthy_until: Date.now() + 10_000, unhealthy_reason: "tests" }
  saveRepoHealthState({ file, state: st, strictWrites: true })

  const st2 = loadRepoHealthState({ file })
  assert.equal(st2.failures.length, 3)
  assert.equal(st2.unhealthy_reason, "tests")
  assert.equal(repoUnhealthyActive(st2, Date.now()), true)
})

