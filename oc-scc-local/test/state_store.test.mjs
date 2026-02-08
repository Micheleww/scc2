import test from "node:test"
import assert from "node:assert/strict"
import fs from "node:fs"
import os from "node:os"
import path from "node:path"

import { readJson, writeJsonAtomic, updateJsonLocked } from "../src/lib/state_store.mjs"

test("writeJsonAtomic writes readable JSON and preserves last write", async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "scc-state-"))
  const file = path.join(dir, "state.json")
  writeJsonAtomic(file, { a: 1 })
  writeJsonAtomic(file, { a: 2 })
  const obj = readJson(file, null)
  assert.equal(obj.a, 2)
})

test("updateJsonLocked applies updater sequentially", async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "scc-state-"))
  const file = path.join(dir, "state.json")

  const p1 = updateJsonLocked(file, { n: 0 }, (cur) => ({ n: (cur?.n ?? 0) + 1 }))
  const p2 = updateJsonLocked(file, { n: 0 }, (cur) => ({ n: (cur?.n ?? 0) + 1 }))
  await Promise.all([p1, p2])

  const obj = readJson(file, null)
  assert.equal(obj.n, 2)
})

