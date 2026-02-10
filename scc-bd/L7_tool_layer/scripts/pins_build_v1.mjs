import fs from "node:fs"
import path from "node:path"
import process from "node:process"
import { buildPinsFromMapV1, writePinsV1Outputs } from "../../L2_task_layer/pins/pins_builder_v1.mjs"

function mustReadJson(p) {
  const raw = fs.readFileSync(p, "utf8").replace(/^\uFEFF/, "")
  return JSON.parse(raw)
}

function parseArgs(argv) {
  const args = { request: null, outDir: null, out: null }
  const a = Array.isArray(argv) ? argv.slice(2) : []
  for (let i = 0; i < a.length; i += 1) {
    const k = a[i]
    const v = a[i + 1]
    if (k === "--request") {
      args.request = v
      i += 1
      continue
    }
    if (k === "--outDir") {
      args.outDir = v
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
if (!args.request) {
  console.error("Usage: node ./scripts/pins_build_v1.mjs --request <pins_request.json> [--outDir artifacts/<task>/pins] [--out <pins_result.json>]")
  process.exit(2)
}

const requestPath = path.resolve(process.cwd(), args.request)
const req = mustReadJson(requestPath)
const out = buildPinsFromMapV1({ repoRoot, request: req })
if (!out.ok) {
  console.error(JSON.stringify(out, null, 2))
  process.exit(1)
}

const outDir = args.outDir ? path.resolve(process.cwd(), args.outDir) : path.join(repoRoot, "artifacts", String(req.task_id), "pins")
writePinsV1Outputs({
  repoRoot,
  taskId: req.task_id,
  outDir: path.relative(repoRoot, outDir),
  pinsResult: out.result_v2 ?? out.result ?? undefined,
  pinsSpec: out.pins,
  detail: out.detail,
})

if (args.out) {
  const outPath = path.resolve(process.cwd(), args.out)
  fs.mkdirSync(path.dirname(outPath), { recursive: true })
  fs.writeFileSync(outPath, JSON.stringify(out.result, null, 2) + "\n", "utf8")
} else {
  process.stdout.write(JSON.stringify(out.result, null, 2) + "\n")
}
