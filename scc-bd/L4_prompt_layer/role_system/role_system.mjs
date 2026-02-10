import fs from "node:fs"
import path from "node:path"
import Ajv from "ajv"
import addFormats from "ajv-formats"

function readJsonFile(file) {
  const raw = fs.readFileSync(file, "utf8")
  const parsed = JSON.parse(raw)
  if (!parsed || typeof parsed !== "object") throw new Error(`Invalid JSON object: ${file}`)
  return parsed
}

function tryReadJsonFile(file) {
  try {
    if (!fs.existsSync(file)) return { ok: false, error: "missing_file" }
    return { ok: true, value: readJsonFile(file) }
  } catch (e) {
    return { ok: false, error: "parse_failed", message: String(e?.message ?? e) }
  }
}

function asStringArray(v) {
  return Array.isArray(v) ? v.map((x) => String(x)).filter((s) => s.trim().length) : []
}

function validateSkillShape(skill) {
  const required = ["schema_version", "skill_id", "version", "owner_role", "summary", "applies_to", "contracts", "enablement"]
  for (const k of required) if (!(k in (skill || {}))) return { ok: false, error: "missing_field", field: k }
  if (skill.schema_version !== "scc.skill.v1") return { ok: false, error: "bad_schema_version" }
  if (typeof skill.skill_id !== "string" || !skill.skill_id.trim()) return { ok: false, error: "bad_skill_id" }
  if (typeof skill.version !== "string" || !skill.version.trim()) return { ok: false, error: "bad_version" }
  if (typeof skill.owner_role !== "string" || !skill.owner_role.trim()) return { ok: false, error: "bad_owner_role" }
  if (typeof skill.summary !== "string" || !skill.summary.trim()) return { ok: false, error: "bad_summary" }
  if (!skill.contracts || typeof skill.contracts !== "object") return { ok: false, error: "bad_contracts" }
  if (typeof skill.contracts.input_schema !== "string" || !skill.contracts.input_schema.trim()) return { ok: false, error: "bad_input_schema" }
  if (typeof skill.contracts.output_schema !== "string" || !skill.contracts.output_schema.trim()) return { ok: false, error: "bad_output_schema" }
  return { ok: true }
}

export function loadRoleSystem({ repoRoot, strict = true } = {}) {
  const root = path.resolve(repoRoot || process.cwd())
  const errors = []

  // 17层分层架构后的路径
  const roleRegistryPath = path.join(root, "L4_prompt_layer", "roles", "registry.json")
  const roleMatrixPath = path.join(root, "L4_prompt_layer", "roles", "role_skill_matrix.json")
  const rolePolicySchemaPath = path.join(root, "L2_task_layer", "contracts", "roles", "role_policy.schema.json")
  const skillsRegistryPath = path.join(root, "L4_prompt_layer", "skills", "registry.json")

  const registryRes = tryReadJsonFile(roleRegistryPath)
  const matrixRes = tryReadJsonFile(roleMatrixPath)
  const schemaRes = tryReadJsonFile(rolePolicySchemaPath)
  const skillsRegistryRes = tryReadJsonFile(skillsRegistryPath)

  if (!registryRes.ok) errors.push({ file: roleRegistryPath, error: registryRes.error, message: registryRes.message ?? null })
  if (!matrixRes.ok) errors.push({ file: roleMatrixPath, error: matrixRes.error, message: matrixRes.message ?? null })
  if (!schemaRes.ok) errors.push({ file: rolePolicySchemaPath, error: schemaRes.error, message: schemaRes.message ?? null })
  if (!skillsRegistryRes.ok) errors.push({ file: skillsRegistryPath, error: skillsRegistryRes.error, message: skillsRegistryRes.message ?? null })

  const roleRegistry = registryRes.ok ? registryRes.value : null
  const roleMatrix = matrixRes.ok ? matrixRes.value : null
  const rolePolicySchema = schemaRes.ok ? schemaRes.value : null
  const skillsRegistry = skillsRegistryRes.ok ? skillsRegistryRes.value : null

  const ajv = new Ajv({ allErrors: true, strict: false, allowUnionTypes: true })
  addFormats(ajv)
  let validateRolePolicy = null
  if (rolePolicySchema) {
    try {
      validateRolePolicy = ajv.compile(rolePolicySchema)
    } catch (e) {
      errors.push({ file: rolePolicySchemaPath, error: "schema_compile_failed", message: String(e?.message ?? e) })
    }
  }

  const roles = new Set()
  const policiesByRole = new Map()
  const policyFilesByRole = new Map()

  const registryRoles = Array.isArray(roleRegistry?.roles) ? roleRegistry.roles : []
  for (const entry of registryRoles) {
    const role = String(entry?.role ?? "").trim().toLowerCase()
    const policyRel = String(entry?.policy ?? "").trim()
    if (!role || !policyRel) {
      errors.push({ file: roleRegistryPath, error: "bad_registry_entry", role: role || null, policy: policyRel || null })
      continue
    }
    roles.add(role)
    policyFilesByRole.set(role, policyRel)
  }

  for (const role of roles) {
    const rel = policyFilesByRole.get(role)
    // 修复路径：注册表中的路径如 "roles/architect.json" 需要映射到 L4_prompt_layer/roles/architect.json
    // 去掉路径中的 "roles/" 前缀，避免重复
    const cleanRel = rel ? rel.replace(/^roles\//, "") : rel
    const policyPath = rel ? path.join(root, "L4_prompt_layer", "roles", cleanRel) : null
    if (!policyPath || !fs.existsSync(policyPath)) {
      errors.push({ file: roleRegistryPath, error: "missing_policy_file", role, policy: rel ?? null })
      continue
    }
    const res = tryReadJsonFile(policyPath)
    if (!res.ok) {
      errors.push({ file: policyPath, error: res.error, message: res.message ?? null, role })
      continue
    }
    const policy = res.value
    if (validateRolePolicy) {
      const valid = validateRolePolicy(policy)
      if (!valid) {
        errors.push({ file: policyPath, error: "policy_validation_failed", role, details: validateRolePolicy.errors })
        continue
      }
    }
    policiesByRole.set(role, policy)
  }

  const skills = new Map()
  const skillFiles = Array.isArray(skillsRegistry?.skills) ? skillsRegistry.skills : []
  for (const entry of skillFiles) {
    const skillId = String(entry?.skill_id ?? "").trim()
    const skillPathRel = String(entry?.path ?? "").trim()
    if (!skillId || !skillPathRel) {
      errors.push({ file: skillsRegistryPath, error: "bad_skills_entry", skill_id: skillId || null, path: skillPathRel || null })
      continue
    }
    // 修复路径：注册表中的路径如 "skills/acceptance_criteria/skill.json" 需要映射到 L4_prompt_layer/skills/acceptance_criteria/skill.json
    // 去掉路径中的 "skills/" 前缀，避免重复
    const cleanSkillPathRel = skillPathRel.replace(/^skills\//, "")
    const skillPath = path.join(root, "L4_prompt_layer", "skills", cleanSkillPathRel)
    if (!fs.existsSync(skillPath)) {
      errors.push({ file: skillsRegistryPath, error: "missing_skill_file", skill_id: skillId, path: skillPathRel })
      continue
    }
    const res = tryReadJsonFile(skillPath)
    if (!res.ok) {
      errors.push({ file: skillPath, error: res.error, message: res.message ?? null, skill_id: skillId })
      continue
    }
    const shape = validateSkillShape(res.value)
    if (!shape.ok) {
      errors.push({ file: skillPath, error: shape.error, field: shape.field ?? null, skill_id: skillId })
      continue
    }
    skills.set(skillId, res.value)
  }

  const matrixRoles = roleMatrix?.roles ? Object.keys(roleMatrix.roles) : []
  const matrixSkillIds = new Set()
  for (const role of matrixRoles) {
    const arr = asStringArray(roleMatrix.roles[role])
    for (const sid of arr) matrixSkillIds.add(sid)
  }

  for (const role of matrixRoles) {
    if (!roles.has(role)) {
      errors.push({ file: roleMatrixPath, error: "matrix_role_not_in_registry", role })
    }
  }

  const skillIds = Array.from(skills.keys())
  for (const sid of skillIds) {
    if (!matrixSkillIds.has(sid)) {
      errors.push({ file: skillsRegistryPath, error: "skill_not_in_matrix", skill_id: sid })
    }
  }

  for (const sid of matrixSkillIds) {
    if (!skills.has(sid)) {
      errors.push({ file: roleMatrixPath, error: "matrix_skill_not_found", skill_id: sid })
    }
  }

  const skillToRole = new Map()
  for (const [role, arr] of Object.entries(roleMatrix?.roles ?? {})) {
    for (const sid of asStringArray(arr)) {
      const owners = skillToRole.get(sid) || new Set()
      owners.add(role)
      skillToRole.set(sid, owners)
    }
  }

  for (const [sid, skill] of skills) {
    const declared = String(skill?.owner_role ?? "").trim().toLowerCase()
    const owners = skillToRole.get(sid) || new Set()
    if (!declared) {
      errors.push({ file: skillsRegistryPath, error: "missing_owner_role", skill_id: sid })
    } else if (!owners.has(declared)) {
      errors.push({ file: skillsRegistryPath, error: "owner_role_not_in_matrix", skill_id: sid, owner_role: declared, matrix_roles: Array.from(owners) })
    }
  }

  if (strict && errors.length > 0) {
    const err = new Error(`Role system invalid (${errors.length} errors). See loadRoleSystem().errors for details.`)
    err.roleSystemErrors = errors
    throw err
  }

  return {
    ok: true,
    roles: Array.from(roles),
    policiesByRole,
    skills,
    errors,
    registry: roleRegistry,
    matrix: roleMatrix,
    skillsRegistry,
  }
}

export function normalizeRoleName(name) {
  return String(name ?? "").trim().toLowerCase()
}

export function validateRoleSkills(roleName, skillIds, { roleMatrix, strict = false } = {}) {
  const normalized = normalizeRoleName(roleName)
  const allowed = asStringArray(roleMatrix?.roles?.[normalized])
  const invalid = []
  for (const sid of skillIds) {
    if (!allowed.includes(sid)) invalid.push(sid)
  }
  if (strict && invalid.length > 0) {
    throw new Error(`Role "${normalized}" does not have skills: ${invalid.join(", ")}`)
  }
  return { valid: invalid.length === 0, invalid, allowed }
}

export function roleRequiresRealTestsFromPolicy(roleName, policiesByRole) {
  const policy = policiesByRole?.get(normalizeRoleName(roleName))
  return !!policy?.requires_real_tests
}
