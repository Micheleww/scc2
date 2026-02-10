import test from "node:test"
import assert from "node:assert/strict"

import { toYaml } from "../../L1_code_layer/gateway/lib/yaml.mjs"

test("toYaml uses real newlines (not literal \\\\n)", () => {
  const out = toYaml({ a: 1, b: { c: true } })
  assert.match(out, /\n/)
  assert.ok(!out.includes("\\n"), "should not contain literal backslash-n sequences")
})

test("toYaml renders arrays and nested objects deterministically", () => {
  const out = toYaml({ arr: [1, { k: "v" }] })
  assert.ok(out.includes("arr:"))
  assert.ok(out.includes('- 1') || out.includes('- "1"') || out.includes("- 1"))
  assert.ok(out.includes("k:"))
})

