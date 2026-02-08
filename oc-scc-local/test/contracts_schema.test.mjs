import test from "node:test"
import assert from "node:assert/strict"
import fs from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"

import Ajv from "ajv"
import addFormats from "ajv-formats"

function repoRootFromHere() {
  const __filename = fileURLToPath(import.meta.url)
  const __dirname = path.dirname(__filename)
  // oc-scc-local/test -> repo root
  return path.resolve(__dirname, "..", "..")
}

function loadJson(p) {
  const raw = fs.readFileSync(p, "utf8").replace(/^\uFEFF/, "")
  return JSON.parse(raw)
}

test("contracts schemas enforce minimal strictness", () => {
  const root = repoRootFromHere()
  const envelopePath = path.join(root, "contracts", "envelope", "envelope.schema.json")
  const eventPath = path.join(root, "contracts", "event", "event.schema.json")
  const submitPath = path.join(root, "contracts", "submit", "submit.schema.json")
  const verdictPath = path.join(root, "contracts", "verdict", "verdict.schema.json")

  const envelope = loadJson(envelopePath)
  const event = loadJson(eventPath)
  const submit = loadJson(submitPath)
  const verdict = loadJson(verdictPath)

  const ajv = new Ajv({ allErrors: true, strict: false })
  addFormats(ajv)

  const vEnvelope = ajv.compile(envelope)
  const vEvent = ajv.compile(event)
  const vSubmit = ajv.compile(submit)
  const vVerdict = ajv.compile(verdict)

  assert.equal(
    vEnvelope({ schema_version: "scc.envelope.v1", protocol: "x", payload: { a: 1 } }),
    true,
    "envelope valid should pass",
  )
  assert.equal(
    vEnvelope({ schema_version: "scc.envelope.v1", protocol: "x", payload: {} }),
    false,
    "envelope empty payload should fail",
  )

  const okEvent = { schema_version: "scc.event.v1", t: new Date().toISOString(), event_type: "SUCCESS", task_id: "t1" }
  assert.equal(vEvent(okEvent), true, "event minimal valid should pass")
  assert.equal(vEvent({ ...okEvent, extra_field: 1 }), false, "event additionalProperties should be rejected")

  const okSubmit = {
    schema_version: "scc.submit.v1",
    task_id: "t1",
    status: "DONE",
    changed_files: ["README.md"],
    tests: { commands: ["node --version"], passed: true, summary: "ok" },
    artifacts: { report_md: "a", selftest_log: "b", evidence_dir: "c", patch_diff: "d", submit_json: "e" },
    exit_code: 0,
    needs_input: [],
  }
  assert.equal(vSubmit(okSubmit), true, "submit minimal valid should pass")
  assert.equal(vSubmit({ ...okSubmit, extra_field: 1 }), false, "submit additionalProperties should be rejected")

  const okVerdict = {
    schema_version: "scc.verdict.v1",
    task_id: "t1",
    verdict: "RETRY",
    reasons: ["x"],
    actions: [{ type: "retry", notes: "n" }],
  }
  assert.equal(vVerdict(okVerdict), true, "verdict minimal valid should pass")
  assert.equal(vVerdict({ ...okVerdict, actions: [{ type: "retry", extra: 1 }] }), false, "verdict action additionalProperties should be rejected")
})

test("all contract schemas are AJV-valid and compile", () => {
  const root = repoRootFromHere()
  const contractsDir = path.join(root, "contracts")

  const ajv = new Ajv({ allErrors: true, strict: false })
  addFormats(ajv)

  function normalizeRefs(obj) {
    if (!obj || typeof obj !== "object") return obj
    if (Array.isArray(obj)) {
      for (let i = 0; i < obj.length; i++) normalizeRefs(obj[i])
      return obj
    }
    for (const [k, v] of Object.entries(obj)) {
      if (k === "$ref" && typeof v === "string" && v.startsWith("contracts/")) {
        // The repo uses repo-root-relative refs; AJV resolves refs relative to schema $id.
        // For the test harness, rewrite them to absolute IDs under a synthetic base.
        obj[k] = `https://scc.local/${v}`
      } else {
        normalizeRefs(v)
      }
    }
    return obj
  }

  /** @type {string[]} */
  const schemaFiles = []
  for (const dirent of fs.readdirSync(contractsDir, { withFileTypes: true })) {
    if (!dirent.isDirectory()) continue
    const sub = path.join(contractsDir, dirent.name)
    for (const f of fs.readdirSync(sub)) {
      if (f.endsWith(".schema.json")) schemaFiles.push(path.join(sub, f))
    }
  }
  schemaFiles.sort()
  assert.ok(schemaFiles.length > 0, "expected to find at least 1 schema file")

  for (const p of schemaFiles) {
    const rel = path.relative(root, p).replaceAll("\\", "/")
    const schema = loadJson(p)
    const id = `https://scc.local/${rel}`
    if (!schema.$id) schema.$id = id
    normalizeRefs(schema)
    ajv.addSchema(schema, id)
    const ok = ajv.validateSchema(schema)
    assert.equal(ok, true, `schema should be valid: ${rel}`)
  }

  // Ensure they compile (catches $ref cycles/missing defs early).
  for (const p of schemaFiles) {
    const rel = path.relative(root, p).replaceAll("\\", "/")
    const id = `https://scc.local/${rel}`
    const validate = ajv.getSchema(id)
    assert.ok(validate, `schema should compile: ${rel}`)
  }
})
