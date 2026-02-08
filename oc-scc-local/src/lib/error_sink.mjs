import fs from "node:fs"
import path from "node:path"

function createJsonlErrorSink({ file }) {
  const abs = String(file ?? "").trim()
  function note({ level = "warn", where = "unknown", err = null, ...fields }) {
    try {
      if (!abs) return
      fs.mkdirSync(path.dirname(abs), { recursive: true })
      const row = {
        t: new Date().toISOString(),
        level: String(level ?? "warn"),
        where: String(where ?? "unknown"),
        err,
        ...fields,
      }
      fs.appendFileSync(abs, JSON.stringify(row) + "\n", "utf8")
    } catch {
      // Never throw from sink.
    }
  }
  return { note, file: abs }
}

export { createJsonlErrorSink }

