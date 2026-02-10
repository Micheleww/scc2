import fs from "node:fs"
import path from "node:path"
import process from "node:process"
import Ajv from "ajv"
import addFormats from "ajv-formats"
import { loadRoleSystem } from "../../L4_prompt_layer/role_system/role_system.mjs"

function mustReadJson(file) {
  const raw = fs.readFileSync(file, "utf8")
  return JSON.parse(raw)
}

function listSchemaFiles(contractsDir) {
  const out = []
  const stack = [contractsDir]
  while (stack.length) {
    const dir = stack.pop()
    for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, ent.name)
      if (ent.isDirectory()) stack.push(full)
      else if (ent.isFile() && ent.name.endsWith(".schema.json")) out.push(full)
    }
  }
  return out
}

function relPosix(root, file) {
  return path.relative(root, file).replaceAll("\\", "/")
}

function addSchemasInStableOrder(ajv, repoRoot) {
  const contractsDir = path.join(repoRoot, "L2_task_layer", "contracts")
  const schemaFiles = listSchemaFiles(contractsDir).sort()
  const schemas = []
  for (const f of schemaFiles) {
    try {
      const s = mustReadJson(f)
      if (s && s.$id) {
        ajv.addSchema(s, s.$id)
        schemas.push({ id: s.$id, file: relPosix(repoRoot, f) })
      }
    } catch {}
  }
  return schemas
}

function validateExample(ajv, repoRoot, schemaRel, exampleRel) {
  const schemaPath = path.join(repoRoot, "L2_task_layer", schemaRel)
  const examplePath = path.join(repoRoot, "L2_task_layer", exampleRel)
  const schema = mustReadJson(schemaPath)
  const example = mustReadJson(examplePath)
  // 使用已有的 schema，避免重复编译
  const schemaId = schema.$id || schemaRel
  let validate
  try {
    validate = ajv.getSchema(schemaId) || ajv.compile(schema)
  } catch (e) {
    // 如果 schema 已存在，直接使用
    validate = ajv.getSchema(schemaId)
  }
  const ok = validate(example)
  if (!ok) {
    const details = JSON.stringify(validate.errors, null, 2)
    throw new Error(`Example validation failed: ${exampleRel}\n${details}`)
  }
  console.log(`[selfcheck] example ok: ${exampleRel}`)
}

// 修复：使用当前工作目录作为 repoRoot（应该在 scc-bd 目录内）
const repoRoot = process.env.SCC_REPO_ROOT ? path.resolve(process.env.SCC_REPO_ROOT) : process.cwd()

console.log(`[selfcheck] repoRoot=${repoRoot}`)

// 1) Role system must load (fail-closed).
const roleSystem = loadRoleSystem({ repoRoot, strict: true })
console.log(`[selfcheck] role_system roles=${roleSystem.roles.length} skills=${roleSystem.skills.size}`)

// 2) JSON schemas must compile.
const ajv = new Ajv({ allErrors: true, strict: false, allowUnionTypes: true })
addFormats(ajv)
const schemas = addSchemasInStableOrder(ajv, repoRoot)
console.log(`[selfcheck] schemas=${schemas.length} compiled`)

// 3) Examples must validate.
validateExample(ajv, repoRoot, "contracts/child_task/child_task.schema.json", "contracts/examples/child_task.example.json")
validateExample(ajv, repoRoot, "contracts/task_graph/task_graph.schema.json", "contracts/examples/task_graph.example.json")
validateExample(ajv, repoRoot, "contracts/pins/pins_request.schema.json", "contracts/examples/pins_request.example.json")

console.log("[selfcheck] all passed")
