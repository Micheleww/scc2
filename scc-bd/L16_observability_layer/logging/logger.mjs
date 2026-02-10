function safeString(x) {
  try {
    if (typeof x === "string") return x
    if (x instanceof Error) return x.message || String(x)
    return JSON.stringify(x)
  } catch {
    return String(x)
  }
}

function errToObject(e) {
  if (!e) return null
  if (e instanceof Error) {
    return {
      name: e.name,
      message: e.message,
      stack: e.stack,
    }
  }
  return { message: safeString(e) }
}

function levelRank(lvl) {
  if (lvl === "debug") return 10
  if (lvl === "info") return 20
  if (lvl === "warn") return 30
  if (lvl === "error") return 40
  return 20
}

function createLogger({ component }) {
  const json = String(process.env.SCC_LOG_JSON ?? "").trim() === "1"
  const minLevel = String(process.env.SCC_LOG_LEVEL ?? "info").trim().toLowerCase()
  const minRank = levelRank(minLevel)

  function emit(level, msg, fields) {
    if (levelRank(level) < minRank) return
    const base = {
      t: new Date().toISOString(),
      level,
      component,
      msg: safeString(msg),
      ...(fields && typeof fields === "object" ? fields : {}),
    }
    if (json) {
      // Prefer structured logs for later ingestion.
      const out = JSON.stringify(base)
      if (level === "error") console.error(out)
      else if (level === "warn") console.warn(out)
      else console.log(out)
      return
    }

    const suffix = fields ? ` ${safeString(fields)}` : ""
    const line = `[${base.t}] ${String(level).toUpperCase()} ${component}: ${base.msg}${suffix}`
    if (level === "error") console.error(line)
    else if (level === "warn") console.warn(line)
    else console.log(line)
  }

  return {
    debug: (msg, fields) => emit("debug", msg, fields),
    info: (msg, fields) => emit("info", msg, fields),
    warn: (msg, fields) => emit("warn", msg, fields),
    error: (msg, fields) => emit("error", msg, fields),
    errToObject,
  }
}

export { createLogger }

