import fs from "node:fs"
import path from "node:path"
import process from "node:process"
import Ajv from "ajv"
import addFormats from "ajv-formats"
import { buildMapV1, writeMapV1Outputs } from "../src/map_v1.mjs"
import { buildPinsFromMapV1, writePinsV1Outputs } from "../src/pins_builder_v1.mjs"
import { runPreflightV1, writePreflightV1Output } from "../src/preflight_v1.mjs"

function mustReadJson(file) {
  const raw = fs.readFileSync(file, "utf8").replace(/^\uFEFF/, "")
  return JSON.parse(raw)
}

function relPosix(root, file) {
  return path.relative(root, file).replaceAll("\\", "/")
}

const repoRoot = path.resolve(process.env.SCC_REPO_ROOT ?? path.join(process.cwd(), ".."))
const outDir = path.join(repoRoot, "artifacts", "pins_preflight_selfcheck")
fs.mkdirSync(outDir, { recursive: true })

console.log(`[selfcheck:pins_preflight_v1] repoRoot=${repoRoot}`)
console.log(`[selfcheck:pins_preflight_v1] outDir=${outDir}`)

const startedAt = Date.now()
const built = buildMapV1({ repoRoot, incremental: false })
const wrote = writeMapV1Outputs({ repoRoot, outDir: relPosix(repoRoot, outDir), buildResult: built })
console.log(`[selfcheck:pins_preflight_v1] map hash=${built.version.hash} durationMs=${Date.now() - startedAt}`)

const taskId = "pins_preflight_selfcheck_v1"
const child_task = {
  title: "Selfcheck: pins builder + preflight gate",
  goal: "Build minimal pins from Map, then run preflight and ensure PASS.",
  role: "executor",
  files: ["oc-scc-local/src/gateway.mjs", "tools/scc/gates/run_ci_gates.py"],
  allowedTests: ["npm --prefix oc-scc-local run smoke"],
  pins: { allowed_paths: ["oc-scc-local/src/gateway.mjs"] },
}

const pins_request = {
  schema_version: "scc.pins_request.v1",
  task_id: taskId,
  child_task,
  signals: { keywords: ["gateway", "preflight", "pins"] },
  map_ref: { path: relPosix(repoRoot, wrote.mapPath), hash: built.version.hash },
  budgets: { max_files: 20, max_loc: 240, default_line_window: 140 },
}

const builtPins = buildPinsFromMapV1({ repoRoot, request: pins_request })
if (!builtPins.ok) {
  console.error("[selfcheck:pins_preflight_v1] pins build failed:", JSON.stringify(builtPins, null, 2))
  process.exit(2)
}

writePinsV1Outputs({ repoRoot, taskId, outDir: `artifacts/${taskId}/pins`, pinsSpec: builtPins.pins, detail: builtPins.detail })

const policy = mustReadJson(path.join(repoRoot, "roles", "executor.json"))
const pre = runPreflightV1({ repoRoot, taskId, childTask: child_task, pinsSpec: builtPins.pins, rolePolicy: policy })
if (!pre.ok) {
  console.error("[selfcheck:pins_preflight_v1] preflight run failed:", JSON.stringify(pre, null, 2))
  process.exit(3)
}
writePreflightV1Output({ repoRoot, taskId, outPath: `artifacts/${taskId}/preflight.json`, preflight: pre.preflight })
if (!pre.preflight.pass) {
  console.error("[selfcheck:pins_preflight_v1] preflight FAIL:", JSON.stringify(pre.preflight, null, 2))
  process.exit(4)
}

const ajv = new Ajv({ allErrors: true, strict: false, allowUnionTypes: true })
addFormats(ajv)
const childSchema = mustReadJson(path.join(repoRoot, "contracts", "child_task", "child_task.schema.json"))
const pinsReqSchema = mustReadJson(path.join(repoRoot, "contracts", "pins", "pins_request.schema.json"))
const pinsResSchema = mustReadJson(path.join(repoRoot, "contracts", "pins", "pins_result.schema.json"))
const preflightSchema = mustReadJson(path.join(repoRoot, "contracts", "preflight", "preflight.schema.json"))
ajv.addSchema(childSchema, childSchema.$id)
ajv.addSchema(pinsReqSchema, pinsReqSchema.$id)
ajv.addSchema(pinsResSchema, pinsResSchema.$id)
ajv.addSchema(preflightSchema, preflightSchema.$id)

const vPinsReq = ajv.getSchema(pinsReqSchema.$id)
const vPinsRes = ajv.getSchema(pinsResSchema.$id)
const vPre = ajv.getSchema(preflightSchema.$id)
if (!vPinsReq || !vPinsRes || !vPre) {
  console.error("[selfcheck:pins_preflight_v1] AJV schema registration failed")
  process.exit(5)
}

if (!vPinsReq(pins_request)) {
  console.error("[selfcheck:pins_preflight_v1] pins_request schema errors:", JSON.stringify(vPinsReq.errors?.slice(0, 20) ?? null, null, 2))
  process.exit(6)
}
if (!vPinsRes(builtPins.result)) {
  console.error("[selfcheck:pins_preflight_v1] pins_result schema errors:", JSON.stringify(vPinsRes.errors?.slice(0, 20) ?? null, null, 2))
  process.exit(7)
}
if (!vPre(pre.preflight)) {
  console.error("[selfcheck:pins_preflight_v1] preflight schema errors:", JSON.stringify(vPre.errors?.slice(0, 20) ?? null, null, 2))
  process.exit(8)
}

console.log("[selfcheck:pins_preflight_v1] OK")
process.exitCode = 0

