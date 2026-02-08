import test from "node:test"
import assert from "node:assert/strict"
import fs from "node:fs"
import os from "node:os"
import path from "node:path"
import crypto from "node:crypto"

import { renderSccContextPackV1, validateSccContextPackV1, loadJsonFile } from "./context_pack_v1.mjs"

function write(p, text) {
  fs.mkdirSync(path.dirname(p), { recursive: true })
  fs.writeFileSync(p, text, "utf8")
}

function writeJson(p, obj) {
  write(p, JSON.stringify(obj, null, 2) + "\n")
}

test("context_pack_v1: render + validate in a synthetic repo", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "scc-cpv1-"))

  // Minimal doc refs required by renderer.
  write(path.join(root, "docs/prompt_os/compiler/legal_prefix_v1.txt"), "LEGAL_PREFIX\n")
  write(path.join(root, "docs/prompt_os/constitution.md"), "CONSTITUTION\n")
  const constitutionHash = `sha256:${crypto.createHash("sha256").update("CONSTITUTION\n", "utf8").digest("hex")}`
  writeJson(path.join(root, "docs/prompt_os/compiler/refs_index_v1.json"), {
    $schema: "http://json-schema.org/draft-07/schema#",
    schema_version: "scc.refs_index.v1",
    updated_at: "2099-01-01",
    description: "test refs",
    refs: [
      {
        id: "constitution",
        path: "docs/prompt_os/constitution.md",
        version: "v1.0.0",
        hash: constitutionHash,
        scope: ["*"],
        priority: "L0",
        always_include: true,
      },
    ],
  })

  // Minimal role policy required by renderer.
  writeJson(path.join(root, "roles/executor.json"), { schema_version: "scc.role_policy.v1", role: "executor", permissions: {} })

  // Minimal artifacts required by task bundle (pins + preflight).
  const taskId = "T-0001"
  writeJson(path.join(root, `artifacts/${taskId}/pins/pins.json`), { schema_version: "scc.pins_result.v2", task_id: taskId, pins: { items: [{ path: "README.md", reason: "test", read_only: true, write_intent: false }] } })
  writeJson(path.join(root, `artifacts/${taskId}/preflight.json`), { schema_version: "scc.preflight.v1", task_id: taskId, pass: true, missing: { files: [], symbols: [], tests: [], write_scope: [] } })

  const out = renderSccContextPackV1({ repoRoot: root, taskId, role: "executor", mode: "execute", budgetTokens: 123, getBoardTask: () => null })
  assert.equal(out.ok, true)
  assert.ok(out.context_pack_id)
  assert.ok(out.rendered_paths?.pack_json)

  const packPath = path.join(root, out.rendered_paths.pack_json)
  const pack = loadJsonFile(packPath)
  assert.equal(pack.schema_version, "scc.context_pack.v1")

  const verdict = validateSccContextPackV1({ repoRoot: root, pack })
  assert.deepEqual(verdict, { ok: true })
})
