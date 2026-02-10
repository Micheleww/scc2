import fs from "node:fs"
import path from "node:path"
import process from "node:process"
import Ajv from "ajv"
import addFormats from "ajv-formats"
import { buildMapV1, writeMapV1Outputs, queryMapV1 } from "../../L17_ontology_layer/map_v1/map_v1.mjs"

function mustReadJson(file) {
  const raw = fs.readFileSync(file, "utf8").replace(/^\uFEFF/, "")
  return JSON.parse(raw)
}

function relPosix(root, file) {
  return path.relative(root, file).replaceAll("\\", "/")
}

const repoRoot = path.resolve(process.env.SCC_REPO_ROOT ?? path.join(process.cwd(), ".."))
const outDir = path.join(repoRoot, "artifacts", "map_v1_selfcheck")
fs.mkdirSync(outDir, { recursive: true })

console.log(`[selfcheck:map_v1] repoRoot=${repoRoot}`)
console.log(`[selfcheck:map_v1] outDir=${outDir}`)

const startedAt = Date.now()
const built = buildMapV1({ repoRoot, incremental: false })
const wrote = writeMapV1Outputs({ repoRoot, outDir: relPosix(repoRoot, outDir), buildResult: built })
console.log(`[selfcheck:map_v1] built hash=${built.version.hash} durationMs=${Date.now() - startedAt}`)

const ajv = new Ajv({ allErrors: true, strict: false, allowUnionTypes: true })
addFormats(ajv)
const mapSchema = mustReadJson(path.join(repoRoot, "contracts", "map", "map.schema.json"))
const versionSchema = mustReadJson(path.join(repoRoot, "contracts", "map", "map_version.schema.json"))
const linkSchema = mustReadJson(path.join(repoRoot, "contracts", "map", "link_report.schema.json"))
const validateMap = ajv.compile(mapSchema)
const validateVersion = ajv.compile(versionSchema)
const validateLink = ajv.compile(linkSchema)

const mapJson = mustReadJson(wrote.mapPath)
const verJson = mustReadJson(wrote.versionPath)
const linkJson = mustReadJson(wrote.linkReportPath)

if (!validateMap(mapJson)) {
  console.error("[selfcheck:map_v1] map schema errors:", JSON.stringify(validateMap.errors?.slice(0, 20) ?? null, null, 2))
  process.exit(1)
}
if (!validateVersion(verJson)) {
  console.error("[selfcheck:map_v1] version schema errors:", JSON.stringify(validateVersion.errors?.slice(0, 20) ?? null, null, 2))
  process.exit(1)
}
if (!validateLink(linkJson)) {
  console.error("[selfcheck:map_v1] link_report schema errors:", JSON.stringify(validateLink.errors?.slice(0, 20) ?? null, null, 2))
  process.exit(1)
}

const q = queryMapV1({ map: mapJson, q: "gateway", limit: 5 })
if (!q.ok || !Array.isArray(q.results) || q.results.length === 0) {
  console.error("[selfcheck:map_v1] query failed or empty:", JSON.stringify(q, null, 2))
  process.exit(2)
}

console.log("[selfcheck:map_v1] OK")
process.exitCode = 0

