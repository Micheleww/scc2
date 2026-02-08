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

  // G6 Schema tightening: submit schema should enforce maxItems and maxLength
  const longString = "x".repeat(2000)
  const longPath = "x".repeat(501)
  assert.equal(vSubmit({ ...okSubmit, task_id: longString }), false, "submit task_id maxLength should be enforced (max 100)")
  assert.equal(vSubmit({ ...okSubmit, changed_files: Array(1001).fill("file.md") }), false, "submit changed_files maxItems should be enforced (max 1000)")
  assert.equal(vSubmit({ ...okSubmit, tests: { ...okSubmit.tests, summary: longString } }), false, "submit tests.summary maxLength should be enforced (max 1000)")

  // G6: Test artifact path maxLength (max 500)
  assert.equal(vSubmit({ ...okSubmit, artifacts: { ...okSubmit.artifacts, report_md: longPath } }), false, "submit artifacts.report_md maxLength should be enforced (max 500)")
  assert.equal(vSubmit({ ...okSubmit, artifacts: { ...okSubmit.artifacts, selftest_log: longPath } }), false, "submit artifacts.selftest_log maxLength should be enforced (max 500)")
  assert.equal(vSubmit({ ...okSubmit, artifacts: { ...okSubmit.artifacts, evidence_dir: longPath } }), false, "submit artifacts.evidence_dir maxLength should be enforced (max 500)")
  assert.equal(vSubmit({ ...okSubmit, artifacts: { ...okSubmit.artifacts, patch_diff: longPath } }), false, "submit artifacts.patch_diff maxLength should be enforced (max 500)")
  assert.equal(vSubmit({ ...okSubmit, artifacts: { ...okSubmit.artifacts, submit_json: longPath } }), false, "submit artifacts.submit_json maxLength should be enforced (max 500)")
})

test("G6 schema tightening constraints are enforced", () => {
  const root = repoRootFromHere()
  const childTaskPath = path.join(root, "contracts", "child_task", "child_task.schema.json")
  const factoryPolicyPath = path.join(root, "contracts", "factory_policy", "factory_policy.schema.json")

  const childTask = loadJson(childTaskPath)
  const factoryPolicy = loadJson(factoryPolicyPath)

  const ajv = new Ajv({ allErrors: true, strict: false })
  addFormats(ajv)

  const vChildTask = ajv.compile(childTask)
  const vFactoryPolicy = ajv.compile(factoryPolicy)

  // Test child_task maxItems constraints
  const validChildTask = {
    title: "Test Task",
    goal: "Test goal",
    role: "executor",
    files: ["file1.js"],
    allowedTests: ["npm test"],
    pins: { allowed_paths: ["src/"] }
  }
  assert.equal(vChildTask(validChildTask), true, "child_task valid should pass")

  // Test maxItems: files (max 100), allowedTests (max 20), required_symbols (max 200)
  assert.equal(vChildTask({ ...validChildTask, files: Array(101).fill("file.js") }), false, "child_task files maxItems should be enforced (max 100)")
  assert.equal(vChildTask({ ...validChildTask, allowedTests: Array(21).fill("test") }), false, "child_task allowedTests maxItems should be enforced (max 20)")
  assert.equal(vChildTask({ ...validChildTask, required_symbols: Array(201).fill("symbol") }), false, "child_task required_symbols maxItems should be enforced (max 200)")

  // Test maxLength: goal (max 5000), role (max 100), task_class_id (max 100), task_class_candidate (max 100)
  assert.equal(vChildTask({ ...validChildTask, goal: "x".repeat(5001) }), false, "child_task goal maxLength should be enforced (max 5000)")
  assert.equal(vChildTask({ ...validChildTask, role: "x".repeat(101) }), false, "child_task role maxLength should be enforced (max 100)")
  assert.equal(vChildTask({ ...validChildTask, task_class_id: "x".repeat(101) }), false, "child_task task_class_id maxLength should be enforced (max 100)")
  assert.equal(vChildTask({ ...validChildTask, task_class_candidate: "x".repeat(101) }), false, "child_task task_class_candidate maxLength should be enforced (max 100)")

  // Test factory_policy maxItems and maxLength constraints
  const validFactoryPolicy = {
    schema_version: "scc.factory_policy.v1",
    updated_at: "2024-01-01T00:00:00Z",
    wip_limits: { WIP_TOTAL_MAX: 10, WIP_EXEC_MAX: 5, WIP_BATCH_MAX: 3 },
    lanes: {
      fastlane: { priority: 1, entity_roles_max: 5 },
      mainlane: { priority: 2, entity_roles_max: 10 },
      batchlane: { priority: 3, entity_roles_max: 15 }
    },
    budgets: { max_children: 5, max_depth: 3, max_total_attempts: 3, max_total_tokens_budget: 1000, max_total_verify_minutes: 60 },
    event_routing: { default: { lane: "mainlane", virtual_roles: [], entity_roles: [] }, by_event_type: {} },
    circuit_breakers: [],
    degradation_matrix: [],
    verification_tiers: { default: "smoke", by_task_class: {} }
  }
  assert.equal(vFactoryPolicy(validFactoryPolicy), true, "factory_policy valid should pass")
  
  // Test circuit_breakers maxItems (max 20)
  assert.equal(vFactoryPolicy({ ...validFactoryPolicy, circuit_breakers: Array(21).fill({ name: "cb", match: {}, trip: { consecutive_failures: 3 }, action: {} }) }), false, "factory_policy circuit_breakers maxItems should be enforced (max 20)")
  
  // Test degradation_matrix maxItems (max 20)
  assert.equal(vFactoryPolicy({ ...validFactoryPolicy, degradation_matrix: Array(21).fill({ when: {}, do: {} }) }), false, "factory_policy degradation_matrix maxItems should be enforced (max 20)")
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
