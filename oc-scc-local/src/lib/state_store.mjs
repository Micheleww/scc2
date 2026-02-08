import fs from "node:fs"
import path from "node:path"

function sleepMs(ms) {
  return new Promise((r) => setTimeout(r, ms))
}

function ensureDirForFile(file) {
  const dir = path.dirname(file)
  try {
    fs.mkdirSync(dir, { recursive: true })
  } catch {
    // caller decides strictness
  }
}

function lockPathFor(file) {
  return `${file}.lock`
}

async function withFileLock(file, fn, { timeoutMs = 4000, pollMs = 50 } = {}) {
  const lock = lockPathFor(file)
  ensureDirForFile(lock)
  const start = Date.now()
  let fh = null
  while (true) {
    try {
      fh = fs.openSync(lock, "wx")
      try {
        fs.writeFileSync(fh, `${process.pid} ${new Date().toISOString()}\n`, "utf8")
      } catch {
        // ignore
      }
      break
    } catch (e) {
      if (Date.now() - start > timeoutMs) {
        throw new Error(`lock_timeout: ${lock}`)
      }
      await sleepMs(pollMs)
      continue
    }
  }

  try {
    return await fn()
  } finally {
    try {
      if (fh != null) fs.closeSync(fh)
    } catch {
      // ignore
    }
    try {
      fs.unlinkSync(lock)
    } catch {
      // ignore
    }
  }
}

function _readTextBestEffort(file) {
  try {
    if (!fs.existsSync(file)) return null
    return fs.readFileSync(file, "utf8")
  } catch {
    return null
  }
}

function readJson(file, fallback = null) {
  // Recovery: if atomic write crashed mid-flight, we may have a .bak file.
  const raw = _readTextBestEffort(file)
  if (raw != null) {
    try {
      return JSON.parse(String(raw).replace(/^\uFEFF/, ""))
    } catch {
      // fall through to bak
    }
  }

  const bak = `${file}.bak`
  const bakRaw = _readTextBestEffort(bak)
  if (bakRaw != null) {
    try {
      return JSON.parse(String(bakRaw).replace(/^\uFEFF/, ""))
    } catch {
      // ignore
    }
  }
  return fallback
}

function writeJsonAtomic(file, obj, { indent = 2 } = {}) {
  ensureDirForFile(file)
  const tmp = `${file}.tmp.${process.pid}.${Math.random().toString(16).slice(2)}`
  const bak = `${file}.bak`
  const data = JSON.stringify(obj, null, indent) + "\n"
  fs.writeFileSync(tmp, data, "utf8")

  // Windows: rename over existing file is not reliable. Use a swap-through-bak pattern.
  // If we crash after moving `file` -> `file.bak`, reads can recover from `.bak`.
  if (fs.existsSync(file)) {
    try {
      if (fs.existsSync(bak)) fs.rmSync(bak, { force: true })
    } catch {
      // ignore
    }
    fs.renameSync(file, bak)
  }
  fs.renameSync(tmp, file)
  try {
    if (fs.existsSync(bak)) fs.rmSync(bak, { force: true })
  } catch {
    // ignore
  }
}

async function updateJsonLocked(file, fallback, updater, { lockTimeoutMs = 4000 } = {}) {
  return withFileLock(
    file,
    async () => {
      const cur = readJson(file, fallback)
      const next = updater(cur)
      writeJsonAtomic(file, next)
      return next
    },
    { timeoutMs: lockTimeoutMs },
  )
}

export { readJson, writeJsonAtomic, withFileLock, updateJsonLocked }

