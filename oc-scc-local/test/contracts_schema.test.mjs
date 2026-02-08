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

  const envelope = loadJson(envelopePath)
  const event = loadJson(eventPath)

  const ajv = new Ajv({ allErrors: true, strict: false })
  addFormats(ajv)

  const vEnvelope = ajv.compile(envelope)
  const vEvent = ajv.compile(event)

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
})

