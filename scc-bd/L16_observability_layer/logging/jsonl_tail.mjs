import fs from "node:fs"

function readJsonlTail(file, limit) {
  try {
    if (!fs.existsSync(file)) return []

    // Streaming tail: read line-by-line, keep only the last N non-empty lines.
    // This avoids OOM from reading multi-GB logs into memory.
    const max = Number.isFinite(limit) && limit > 0 ? Math.min(20000, limit) : 20000
    const buf = []

    const fd = fs.openSync(file, "r")
    try {
      const stat = fs.fstatSync(fd)
      const size = Number(stat.size || 0)
      if (size <= 0) return []

      const chunkSize = 64 * 1024
      let pos = size
      let carry = ""
      while (pos > 0 && buf.length < max + 5000) {
        const readLen = Math.min(chunkSize, pos)
        pos -= readLen
        const b = Buffer.allocUnsafe(readLen)
        fs.readSync(fd, b, 0, readLen, pos)
        const txt = b.toString("utf8") + carry
        const parts = txt.split("\n")
        carry = parts.shift() ?? ""
        for (let i = parts.length - 1; i >= 0; i--) {
          const line = String(parts[i] ?? "").trim()
          if (!line) continue
          buf.push(line)
          if (buf.length >= max) break
        }
      }

      const lines = buf.reverse()
      return lines
        .map((l) => {
          try {
            return JSON.parse(l)
          } catch {
            return null
          }
        })
        .filter(Boolean)
    } finally {
      fs.closeSync(fd)
    }
  } catch {
    return []
  }
}

function countJsonlLines(file) {
  try {
    if (!fs.existsSync(file)) return 0
    const raw = fs.readFileSync(file, "utf8")
    if (!raw) return 0
    return raw.split("\n").filter((l) => String(l).trim().length > 0).length
  } catch {
    return 0
  }
}

export { readJsonlTail, countJsonlLines }

