import fs from "node:fs"
import path from "node:path"
import process from "node:process"
import Ajv from "ajv"
import addFormats from "ajv-formats"
import { loadRoleSystem } from "../src/role_system.mjs"

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
  const contractsDir = path.join(repoRoot, "contracts")
  const schemas = listSchemaFiles(contractsDir)
    .map((file) => ({ file, rel: relPosix(repoRoot, file), json: mustReadJson(file) }))
    .sort((a, b) => a.rel.localeCompare(b.rel))

  // First pass: add all schemas by $id (or by rel path as fallback).
  for (const s of schemas) {
    const id = typeof s.json?.$id === "string" && s.json.$id.trim().length ? s.json.$id : s.rel
    ajv.addSchema(s.json, id)
  }
  return schemas
}

function validateExample(ajv, repoRoot, schemaId, exampleRelPath) {
  const file = path.join(repoRoot, exampleRelPath)
  const data = mustReadJson(file)
  const validate = ajv.getSchema(schemaId)
  if (!validate) throw new Error(`Missing compiled schema: ${schemaId}`)
  const ok = validate(data)
  if (!ok) {
    const errs = validate.errors ? validate.errors.slice(0, 20) : null
    throw new Error(`Example failed schema validation: ${exampleRelPath}\n${JSON.stringify(errs, null, 2)}`)
  }
}

const repoRoot = path.resolve(process.env.SCC_REPO_ROOT ?? path.join(process.cwd(), ".."))

console.log(`[selfcheck] repoRoot=${repoRoot}`)

// 1) Role system must load (fail-closed).
const roleSystem = loadRoleSystem({ repoRoot, strict: true })
console.log(`[selfcheck] role_system roles=${roleSystem.roles.size} skills=${roleSystem.skills.size}`)

// 2) JSON schemas must compile.
const ajv = new Ajv({ allErrors: true, strict: false, allowUnionTypes: true })
addFormats(ajv)
const schemas = addSchemasInStableOrder(ajv, repoRoot)
console.log(`[selfcheck] schemas=${schemas.length} compiled`)

// 3) Examples must validate.
validateExample(ajv, repoRoot, "contracts/child_task/child_task.schema.json", "contracts/examples/child_task.example.json")
validateExample(ajv, repoRoot, "contracts/task_graph/task_graph.schema.json", "contracts/examples/task_graph.example.json")
validateExample(ajv, repoRoot, "contracts/pins/pins_request.schema.json", "contracts/examples/pins_request.example.json")
validateExample(ajv, repoRoot, "contracts/pins/pins_result.schema.json", "contracts/examples/pins_result.example.json")
validateExample(ajv, repoRoot, "contracts/preflight/preflight.schema.json", "contracts/examples/preflight.example.json")
validateExample(ajv, repoRoot, "contracts/submit/submit.schema.json", "contracts/examples/submit.example.json")
validateExample(ajv, repoRoot, "contracts/verdict/verdict.schema.json", "contracts/examples/verdict.example.json")
validateExample(ajv, repoRoot, "contracts/event/event.schema.json", "contracts/examples/event.example.json")
validateExample(ajv, repoRoot, "contracts/roles/role_policy.schema.json", "contracts/examples/role_policy.example.json")

console.log("[selfcheck] OK")
process.exitCode = 0

