import test from "node:test"
import assert from "node:assert/strict"
import fs from "node:fs"
import os from "node:os"
import path from "node:path"

import { loadJobsState, saveJobsState } from "../src/lib/jobs_store.mjs"

test("jobs_store persists and loads jobs array", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "scc-jobs-"))
  const file = path.join(dir, "jobs_state.json")

  saveJobsState({ file, jobsArray: [{ id: "j1", status: "queued" }], strictWrites: true })
  const arr = loadJobsState({ file })
  assert.equal(arr.length, 1)
  assert.equal(arr[0].id, "j1")
})

