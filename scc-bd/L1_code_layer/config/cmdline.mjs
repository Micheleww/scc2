function hasShellMetacharacters(s) {
  // Conservative set for Windows cmd.exe and POSIX shells.
  return /[&|;<>`\r\n]/.test(String(s ?? "")) || (process.platform === "win32" && /[%^]/.test(String(s ?? "")))
}

function parseCmdline(cmd) {
  // Minimal argv parser: supports double-quoted segments.
  // This is intentionally conservative; for complex pipelines use explicit scripts instead of shell.
  const s = String(cmd ?? "").trim()
  if (!s) return []

  const out = []
  let cur = ""
  let inQuotes = false

  for (let i = 0; i < s.length; i++) {
    const ch = s[i]
    if (ch === '"') {
      inQuotes = !inQuotes
      continue
    }
    if (!inQuotes && /\s/.test(ch)) {
      if (cur) out.push(cur)
      cur = ""
      continue
    }
    cur += ch
  }
  if (cur) out.push(cur)
  return out
}

export { hasShellMetacharacters, parseCmdline }

