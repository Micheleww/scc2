function yamlEscapeScalar(v) {
  const s = String(v ?? "")
  // Quote scalars by default to keep output stable even if it contains ":" or "#".
  const escaped = s.replace(/\\/g, "\\\\").replace(/"/g, '\\"')
  return `"${escaped}"`
}

function toYaml(value, indent = 0) {
  const pad = " ".repeat(indent)
  if (value === null || value === undefined) return "null"
  if (typeof value === "number" || typeof value === "boolean") return String(value)
  if (typeof value === "string") return yamlEscapeScalar(value)
  if (Array.isArray(value)) {
    if (!value.length) return "[]"
    const lines = []
    for (const item of value) {
      if (item && typeof item === "object") {
        lines.push(`${pad}- ${toYaml(item, indent + 2).replace(/^\s*/, "")}`)
      } else {
        lines.push(`${pad}- ${toYaml(item, 0)}`)
      }
    }
    return lines.join("\n")
  }
  if (typeof value === "object") {
    const keys = Object.keys(value)
    if (!keys.length) return "{}"
    const lines = []
    for (const k of keys) {
      const v = value[k]
      if (v && typeof v === "object") {
        const rendered = toYaml(v, indent + 2)
        lines.push(`${pad}${k}:\n${rendered}`)
      } else {
        lines.push(`${pad}${k}: ${toYaml(v, 0)}`)
      }
    }
    return lines.join("\n")
  }
  return yamlEscapeScalar(String(value))
}

export { toYaml, yamlEscapeScalar }

