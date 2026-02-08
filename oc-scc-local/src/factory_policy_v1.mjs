export function computeDegradationActionV1({ factoryPolicy, signals }) {
  const fp = factoryPolicy && typeof factoryPolicy === "object" ? factoryPolicy : {}
  const matrix = Array.isArray(fp.degradation_matrix) ? fp.degradation_matrix : []
  const sig = signals && typeof signals === "object" ? signals : {}

  for (const entry of matrix) {
    if (!entry || typeof entry !== "object") continue
    const when = entry.when && typeof entry.when === "object" ? entry.when : {}
    let match = true
    for (const [k, v] of Object.entries(when)) {
      if (v === true && sig[k] !== true) {
        match = false
        break
      }
      if (v === false && sig[k] !== false) {
        match = false
        break
      }
    }
    if (!match) continue
    const action = entry.do && typeof entry.do === "object" ? entry.do : null
    return action
  }

  return null
}

export function applyDegradationToWipLimitsV1({ limits, action }) {
  const base = limits && typeof limits === "object" ? limits : { total: 0, exec: 0, batch: 0 }
  const a = action && typeof action === "object" ? action : null
  const out = { ...base }
  const execMax = Number(a?.reduce_WIP_EXEC_MAX_to)
  if (Number.isFinite(execMax) && execMax >= 0) {
    const n = Math.floor(execMax)
    out.exec = n
    // If runner-specific exec limits exist, treat reduce_WIP_EXEC_MAX_to as a hard ceiling.
    if (Number.isFinite(Number(out.exec_external))) out.exec_external = Math.min(Number(out.exec_external), n)
    if (Number.isFinite(Number(out.exec_internal))) out.exec_internal = Math.min(Number(out.exec_internal), n)
  }
  return out
}

export function shouldAllowTaskUnderStopTheBleedingV1({ action, task }) {
  const a = action && typeof action === "object" ? action : null
  if (!a || String(a.mode ?? "") !== "stop_the_bleeding") return { ok: true }
  const allow = Array.isArray(a.allow_task_classes) ? a.allow_task_classes.map((x) => String(x)) : []
  const allowSet = new Set(allow.filter(Boolean))
  const t = task && typeof task === "object" ? task : {}
  const cls = String(t.task_class_id ?? "").trim()
  if (cls && allowSet.has(cls)) return { ok: true }
  if (String(t.area ?? "") === "control_plane") return { ok: true }
  const role = String(t.role ?? "").trim().toLowerCase()
  if (["doc", "doc_adr_scribe", "ssot_curator"].includes(role)) return { ok: true }
  const files = Array.isArray(t.files) ? t.files.map((x) => String(x ?? "").replaceAll("\\", "/")).filter(Boolean) : []
  const docsOnly = files.length > 0 && files.every((p) => p.startsWith("docs/"))
  if (docsOnly) {
    const pins = t.pins && typeof t.pins === "object" ? t.pins : null
    const allowed = Array.isArray(pins?.allowed_paths) ? pins.allowed_paths.map((x) => String(x ?? "").replaceAll("\\", "/")).filter(Boolean) : []
    const pinsDocsOnly = allowed.length === 0 || allowed.every((p) => p.startsWith("docs/"))
    if (pinsDocsOnly) return { ok: true }
  }
  return { ok: false, error: "stop_the_bleeding" }
}
