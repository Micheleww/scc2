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

  const roleRegistryPath = path.join(root, "roles", "registry.json")
  const roleMatrixPath = path.join(root, "roles", "role_skill_matrix.json")
  const rolePolicySchemaPath = path.join(root, "contracts", "roles", "role_policy.schema.json")
  const skillsRegistryPath = path.join(root, "skills", "registry.json")

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
    const policyPath = rel ? path.join(root, rel) : null
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
      const ok = Boolean(validateRolePolicy(policy))
      if (!ok) {
        errors.push({
          file: policyPath,
          error: "role_policy_schema_failed",
          role,
          details: validateRolePolicy.errors ? validateRolePolicy.errors.slice(0, 12) : null,
        })
        continue
      }
    }
    const declared = String(policy?.role ?? "").trim().toLowerCase()
    if (declared && declared !== role) {
      errors.push({ file: policyPath, error: "role_mismatch", role, declared })
      continue
    }
    policiesByRole.set(role, policy)
  }

  const skills = new Map()
  const skillsEntries = Array.isArray(skillsRegistry?.skills) ? skillsRegistry.skills : []
  for (const entry of skillsEntries) {
    const skillId = String(entry?.skill_id ?? "").trim()
    const skillPathRel = String(entry?.path ?? "").trim()
    if (!skillId || !skillPathRel) {
      errors.push({ file: skillsRegistryPath, error: "bad_skill_registry_entry", skill_id: skillId || null, path: skillPathRel || null })
      continue
    }
    const skillPath = path.join(root, skillPathRel)
    const skillRes = tryReadJsonFile(skillPath)
    if (!skillRes.ok) {
      errors.push({ file: skillPath, error: skillRes.error, message: skillRes.message ?? null, skill_id: skillId })
      continue
    }
    const skill = skillRes.value
    const shape = validateSkillShape(skill)
    if (!shape.ok) {
      errors.push({ file: skillPath, error: "skill_shape_failed", skill_id: skillId, details: shape })
      continue
    }
    if (String(skill.skill_id).trim() !== skillId) {
      errors.push({ file: skillPath, error: "skill_id_mismatch", registry: skillId, declared: skill.skill_id })
      continue
    }
    skills.set(skillId, skill)
  }

  const matrixRoles = roleMatrix && typeof roleMatrix === "object" ? roleMatrix.roles : null
  const skillsAllowedByRole = new Map()
  if (matrixRoles && typeof matrixRoles === "object") {
    for (const [role, list] of Object.entries(matrixRoles)) {
      const r = String(role ?? "").trim().toLowerCase()
      if (!r) continue
      const allowed = asStringArray(list)
      skillsAllowedByRole.set(r, allowed)
      for (const skillId of allowed) {
        if (!skills.has(skillId)) errors.push({ file: roleMatrixPath, error: "unknown_skill_in_matrix", role: r, skill_id: skillId })
      }
    }
  } else {
    errors.push({ file: roleMatrixPath, error: "bad_matrix_roles" })
  }

  for (const role of roles) {
    if (!skillsAllowedByRole.has(role)) {
      errors.push({ file: roleMatrixPath, error: "missing_role_in_matrix", role })
    }
  }

  const ok = errors.length === 0
  if (!ok && strict) {
    const msg = `Role system invalid (${errors.length} errors). See loadRoleSystem().errors for details.`
    const err = new Error(msg)
    err.roleSystemErrors = errors
    throw err
  }
  return {
    ok,
    repoRoot: root,
    roles,
    policiesByRole,
    skills,
    skillsAllowedByRole,
    errors,
  }
}

export function normalizeRoleName(roleSystem, v) {
  const s = String(v ?? "").trim().toLowerCase()
  if (!s) return null
  return roleSystem?.roles?.has(s) ? s : null
}

export function roleDefaultSkills(roleSystem, role) {
  const r = String(role ?? "").trim().toLowerCase()
  const list = roleSystem?.skillsAllowedByRole?.get(r)
  return Array.isArray(list) ? list.slice(0, 32) : []
}

export function roleRequiresRealTestsFromPolicy(roleSystem, role) {
  const r = String(role ?? "").trim().toLowerCase()
  const policy = roleSystem?.policiesByRole?.get(r)
  return Boolean(policy?.capabilities?.can_write_code)
}

export function validateRoleSkills(roleSystem, role, skills) {
  const r = String(role ?? "").trim().toLowerCase()
  const requested = asStringArray(skills)
  const allowed = roleSystem?.skillsAllowedByRole?.get(r)
  if (!allowed) return { ok: false, error: "role_not_in_matrix", role: r }
  const allowedSet = new Set(allowed)
  const unknown = requested.filter((s) => !allowedSet.has(s))
  if (unknown.length) return { ok: false, error: "skill_not_allowed", role: r, unknown: unknown.slice(0, 20) }
  return { ok: true }
}

