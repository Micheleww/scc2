import fs from "node:fs"
import path from "node:path"
import crypto from "node:crypto"

function sha256Hex(text) {
  return crypto.createHash("sha256").update(String(text ?? ""), "utf8").digest("hex")
}

function isPlainObject(v) {
  return Boolean(v && typeof v === "object" && !Array.isArray(v))
}

function deepMergeJson(base, patch) {
  if (!isPlainObject(base) || !isPlainObject(patch)) return patch
  const out = { ...base }
  for (const [k, v] of Object.entries(patch)) {
    if (isPlainObject(out[k]) && isPlainObject(v)) out[k] = deepMergeJson(out[k], v)
    else out[k] = v
  }
  return out
}

function safeResolveUnderRoot(rootDir, relPath) {
  const root = path.resolve(String(rootDir ?? ""))
  const rel = String(relPath ?? "")
  const abs = path.resolve(root, rel)
  const rootLc = root.toLowerCase()
  const absLc = abs.toLowerCase()
  if (absLc === rootLc) return null
  if (!absLc.startsWith(rootLc + path.sep)) return null
  return abs
}

function stringifyForText(v) {
  if (v == null) return ""
  if (typeof v === "string") return v
  try {
    return JSON.stringify(v, null, 2)
  } catch {
    return String(v)
  }
}

function substituteText(template, vars) {
  const t = String(template ?? "")
  return t.replace(/{{\s*([a-zA-Z0-9_.-]+)\s*}}/g, (_m, key) => stringifyForText(vars?.[key]))
}

function substituteJson(node, vars) {
  if (typeof node === "string") {
    const m = node.match(/^{{\s*([a-zA-Z0-9_.-]+)\s*}}$/)
    if (m) {
      const v = vars?.[m[1]]
      return v === undefined ? node : v
    }
    return node.replace(/{{\s*([a-zA-Z0-9_.-]+)\s*}}/g, (_m, key) => {
      const v = vars?.[key]
      return v === undefined ? "" : String(v)
    })
  }
  if (Array.isArray(node)) return node.map((x) => substituteJson(x, vars))
  if (isPlainObject(node)) {
    const out = {}
    for (const [k, v] of Object.entries(node)) out[k] = substituteJson(v, vars)
    return out
  }
  return node
}

function normalizeContentToString(block, content) {
  if (typeof content === "string") return content
  if (Array.isArray(content)) return content.map((x) => String(x ?? "")).join("\n")
  if (content == null && typeof block?.src === "string") return null
  return String(content ?? "")
}

export function createPromptRegistry({ registryFile, rootDir }) {
  const regPath = String(registryFile ?? "")
  const blocksRoot = String(rootDir ?? "")
  let cache = { mtimeMs: 0, parsed: null, compiled: null }

  function loadRegistryFresh() {
    if (!regPath) return { ok: false, error: "missing_registry_path" }
    if (!fs.existsSync(regPath)) return { ok: false, error: "registry_missing", file: regPath }
    let st
    try {
      st = fs.statSync(regPath)
    } catch {
      return { ok: false, error: "registry_stat_failed", file: regPath }
    }
    const mtimeMs = Number(st.mtimeMs ?? 0)
    let raw
    try {
      raw = fs.readFileSync(regPath, "utf8")
    } catch {
      return { ok: false, error: "registry_read_failed", file: regPath }
    }
    let parsed
    try {
      parsed = JSON.parse(raw)
    } catch (e) {
      return { ok: false, error: "registry_bad_json", message: String(e), file: regPath }
    }
    if (!parsed || typeof parsed !== "object") return { ok: false, error: "registry_bad_root", file: regPath }

    const blocks = Array.isArray(parsed.blocks) ? parsed.blocks : []
    const roles = Array.isArray(parsed.roles) ? parsed.roles : []
    const presets = Array.isArray(parsed.presets) ? parsed.presets : []
    const blockMap = new Map()
    for (const b of blocks) {
      if (!b || typeof b !== "object") continue
      const id = String(b.id ?? "").trim()
      if (!id) continue
      blockMap.set(id, b)
    }
    const roleMap = new Map()
    for (const r of roles) {
      if (!r || typeof r !== "object") continue
      const id = String(r.role_id ?? "").trim()
      if (!id) continue
      roleMap.set(id, r)
    }
    const presetMap = new Map()
    for (const p of presets) {
      if (!p || typeof p !== "object") continue
      const id = String(p.preset_id ?? "").trim()
      if (!id) continue
      presetMap.set(id, p)
    }

    const compiled = {
      registry_version: String(parsed.registry_version ?? "0.0.0"),
      updated_at: parsed.updated_at ?? null,
      globals: parsed.globals && typeof parsed.globals === "object" ? parsed.globals : {},
      blockMap,
      roleMap,
      presetMap,
    }
    cache = { mtimeMs, parsed, compiled }
    return { ok: true, registry: parsed, compiled }
  }

  function getCompiled() {
    if (!regPath) return { ok: false, error: "missing_registry_path" }
    let st
    try {
      st = fs.existsSync(regPath) ? fs.statSync(regPath) : null
    } catch {
      st = null
    }
    const mtimeMs = Number(st?.mtimeMs ?? 0)
    if (!cache.compiled || mtimeMs <= 0 || mtimeMs !== cache.mtimeMs) return loadRegistryFresh()
    return { ok: true, registry: cache.parsed, compiled: cache.compiled }
  }

  function readBlockSrc(rel) {
    const abs = safeResolveUnderRoot(blocksRoot, rel)
    if (!abs) return { ok: false, error: "block_src_path_escape", src: rel }
    if (!fs.existsSync(abs)) return { ok: false, error: "block_src_missing", src: rel }
    try {
      const text = fs.readFileSync(abs, "utf8")
      return { ok: true, abs, text }
    } catch {
      return { ok: false, error: "block_src_read_failed", src: rel }
    }
  }

  function render({ role_id, preset_id, params }) {
    const loaded = getCompiled()
    if (!loaded.ok) return loaded
    const { compiled } = loaded

    const roleId = String(role_id ?? "").trim()
    if (!roleId) return { ok: false, error: "missing_role_id" }
    const role = compiled.roleMap.get(roleId)
    if (!role) return { ok: false, error: "unknown_role_id", role_id: roleId }

    const presetId = preset_id != null ? String(preset_id).trim() : null
    const preset = presetId ? compiled.presetMap.get(presetId) ?? null : null
    if (presetId && !preset) return { ok: false, error: "unknown_preset_id", preset_id: presetId }
    if (preset && preset.role_id && String(preset.role_id) !== roleId) {
      return { ok: false, error: "preset_role_mismatch", role_id: roleId, preset_role_id: preset.role_id }
    }

    const globals = compiled.globals && typeof compiled.globals === "object" ? compiled.globals : {}
    const pointerPack = globals.pointer_pack && typeof globals.pointer_pack === "object" ? globals.pointer_pack : {}
    const defaults = role.defaults && typeof role.defaults === "object" ? role.defaults : {}
    const presetDefaults = preset?.defaults && typeof preset.defaults === "object" ? preset.defaults : {}
    const presetParams = preset?.params && typeof preset.params === "object" ? preset.params : {}
    const vars = {
      ...pointerPack,
      ...defaults,
      ...presetDefaults,
      ...presetParams,
      ...(params && typeof params === "object" ? params : {}),
      now_iso: new Date().toISOString(),
    }

    const requiredRole = Array.isArray(role.required_params) ? role.required_params.map((x) => String(x)) : []
    const requiredPreset = Array.isArray(preset?.required_params) ? preset.required_params.map((x) => String(x)) : []
    const required = Array.from(new Set([...requiredRole, ...requiredPreset])).filter(Boolean)
    const missing = required.filter((k) => vars[k] === undefined)
    if (missing.length) return { ok: false, error: "missing_params", missing }

    const roleBlocks = role?.composition && Array.isArray(role.composition.blocks) ? role.composition.blocks : []
    const blocks = preset?.composition && Array.isArray(preset.composition.blocks) ? preset.composition.blocks : roleBlocks
    if (!blocks.length) return { ok: false, error: "no_blocks_for_role", role_id: roleId }

    const renderKind = String(role.render_kind ?? "text")
    const usedBlocks = []
    const textParts = []
    let jsonAcc = null

    for (const ref of blocks) {
      const blockId = String(ref ?? "").trim()
      if (!blockId) continue
      const block = compiled.blockMap.get(blockId)
      if (!block) return { ok: false, error: "unknown_block_id", block_id: blockId, role_id: roleId }
      const status = String(block.status ?? "active")
      if (status !== "active") return { ok: false, error: "block_not_active", block_id: blockId, status }

      const version = String(block.version ?? "0.0.0")
      const type = String(block.type ?? "text")
      let srcRel = block?.src != null ? String(block.src) : null
      let content = block.content

      if (srcRel) {
        const read = readBlockSrc(srcRel)
        if (!read.ok) return read
        if (type === "json") {
          try {
            content = JSON.parse(read.text)
          } catch (e) {
            return { ok: false, error: "block_src_bad_json", block_id: blockId, src: srcRel, message: String(e) }
          }
        } else {
          content = read.text
        }
      }

      const blockParams = Array.isArray(block.params) ? block.params.map((x) => String(x)) : []
      const missingBlock = blockParams.filter((k) => vars[k] === undefined)
      if (missingBlock.length) return { ok: false, error: "missing_block_params", block_id: blockId, missing: missingBlock }

      if (type === "text") {
        const template = normalizeContentToString(block, content)
        if (template == null) return { ok: false, error: "block_missing_content", block_id: blockId }
        const rendered = substituteText(template, vars)
        textParts.push(rendered)
      } else if (type === "json") {
        const obj = substituteJson(content, vars)
        jsonAcc = jsonAcc == null ? obj : deepMergeJson(jsonAcc, obj)
      } else {
        return { ok: false, error: "unknown_block_type", block_id: blockId, type }
      }

      const rawForHash = type === "json" ? JSON.stringify(content) : normalizeContentToString(block, content) ?? ""
      usedBlocks.push({ id: blockId, version, type, src: srcRel, sha256: sha256Hex(rawForHash) })
    }

    let outputText = null
    let outputJson = null
    if (renderKind === "text") {
      outputText = textParts.join("\n\n").trimEnd() + "\n"
    } else if (renderKind === "json_string") {
      outputJson = jsonAcc ?? {}
      outputText = JSON.stringify(outputJson, null, 2) + "\n"
    } else if (renderKind === "json") {
      outputJson = jsonAcc ?? {}
    } else {
      return { ok: false, error: "unknown_render_kind", render_kind: renderKind }
    }

    const renderedSha256 = sha256Hex(outputText ?? JSON.stringify(outputJson ?? {}))
    const prompt_ref = {
      registry_file: regPath,
      registry_version: compiled.registry_version,
      updated_at: compiled.updated_at,
      role_id: roleId,
      preset_id: presetId,
      blocks: usedBlocks,
      rendered_sha256: renderedSha256,
      rendered_bytes: outputText != null ? Buffer.byteLength(outputText, "utf8") : null,
      rendered_at: vars.now_iso,
    }

    return { ok: true, text: outputText, json: outputJson, prompt_ref }
  }

  function info() {
    const loaded = getCompiled()
    if (!loaded.ok) return loaded
    const { compiled, registry } = loaded
    const blocks = Array.isArray(registry?.blocks) ? registry.blocks : []
    const roles = Array.isArray(registry?.roles) ? registry.roles : []
    const presets = Array.isArray(registry?.presets) ? registry.presets : []
    return {
      ok: true,
      registry_file: regPath,
      registry_version: compiled.registry_version,
      updated_at: compiled.updated_at,
      counts: { blocks: blocks.length, roles: roles.length, presets: presets.length },
      blocks: blocks.map((b) => ({
        id: b?.id ?? null,
        version: b?.version ?? null,
        status: b?.status ?? null,
        type: b?.type ?? null,
        src: b?.src ?? null,
        params: Array.isArray(b?.params) ? b.params : [],
      })),
      roles: roles.map((r) => ({
        role_id: r?.role_id ?? null,
        version: r?.version ?? null,
        status: r?.status ?? null,
        render_kind: r?.render_kind ?? null,
        blocks: Array.isArray(r?.composition?.blocks) ? r.composition.blocks : [],
        required_params: Array.isArray(r?.required_params) ? r.required_params : [],
      })),
      presets: presets.map((p) => ({
        preset_id: p?.preset_id ?? null,
        version: p?.version ?? null,
        status: p?.status ?? null,
        role_id: p?.role_id ?? null,
        blocks: Array.isArray(p?.composition?.blocks) ? p.composition.blocks : null,
      })),
    }
  }

  return { render, info, getCompiled }
}

