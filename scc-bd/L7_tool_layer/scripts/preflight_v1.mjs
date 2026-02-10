import fs from "node:fs"
import path from "node:path"
import process from "node:process"
import { runPreflightV1, writePreflightV1Output } from "../../L13_security_layer/preflight/preflight_v1.mjs"

function mustReadJson(p) {
  const raw = fs.readFileSync(p, "utf8").replace(/^\uFEFF/, "")
  return JSON.parse(raw)
}

function parseArgs(argv) {
  const args = { child: null, pins: null, policy: null, taskId: null, out: null }
  const a = Array.isArray(argv) ? argv.slice(2) : []
  for (let i = 0; i < a.length; i += 1) {
    const k = a[i]
    const v = a[i + 1]
    if (k === "--child") {
      args.child = v
      i += 1
      continue
    }
    if (k === "--pins") {
      args.pins = v
      i += 1
      continue
    }
    if (k === "--policy") {
      args.policy = v
      i += 1
      continue
    }
    if (k === "--taskId") {
      args.taskId = v
      i += 1
      continue
    }
    if (k === "--out") {
      args.out = v
      i += 1
      continue
    }
  }
  return args
}

const repoRoot = path.resolve(process.env.SCC_REPO_ROOT ?? path.join(process.cwd(), ".."))
const args = parseArgs(process.argv)
if (!args.child || !args.pins || !args.policy) {
  console.error("Usage: node ./scripts/preflight_v1.mjs --child <child_task.json> --pins <pins.json> --policy <roles/*.json> [--taskId <id>] [--out artifacts/<id>/preflight.json]")
  process.exit(2)
}

const child = mustReadJson(path.resolve(process.cwd(), args.child))
const pins = mustReadJson(path.resolve(process.cwd(), args.pins))
const policy = mustReadJson(path.resolve(process.cwd(), args.policy))
const taskId = String(args.taskId ?? child?.task_id ?? child?.id ?? "task_unknown")

const out = runPreflightV1({ repoRoot, taskId, childTask: child, pinsSpec: pins, rolePolicy: policy })
if (!out.ok) {
  console.error(JSON.stringify(out, null, 2))
  process.exit(1)
}

writePreflightV1Output({ repoRoot, taskId, outPath: args.out ? args.out : null, preflight: out.preflight })
process.stdout.write(JSON.stringify(out.preflight, null, 2) + "\n")
process.exit(out.preflight.pass ? 0 : 3)

