import test from "node:test"
import assert from "node:assert/strict"
import fs from "node:fs"
import os from "node:os"
import path from "node:path"

import { readJsonlTail } from "../../L16_observability_layer/logging/jsonl_tail.mjs"

test("readJsonlTail returns last N parsed rows without reading whole file", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "scc-jsonl-"))
  const file = path.join(dir, "x.jsonl")
  const lines = []
  for (let i = 0; i < 2000; i++) lines.push(JSON.stringify({ i }) + "\n")
  fs.writeFileSync(file, lines.join(""), "utf8")

  const out = readJsonlTail(file, 10)
  assert.equal(out.length, 10)
  assert.equal(out[0].i, 1990)
  assert.equal(out[9].i, 1999)
})

