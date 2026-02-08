import crypto from "node:crypto"

function sendJson(res, status, obj) {
  const body = JSON.stringify(obj, null, 2)
  res.statusCode = status
  res.setHeader("content-type", "application/json; charset=utf-8")
  res.setHeader("content-length", Buffer.byteLength(body))
  res.end(body)
}

function sendText(res, status, body) {
  res.statusCode = status
  res.setHeader("content-type", "text/plain; charset=utf-8")
  res.setHeader("content-length", Buffer.byteLength(body))
  res.end(body)
}

function readRequestBody(req, { maxBytes = 2_000_000 } = {}) {
  return new Promise((resolve) => {
    const chunks = []
    let total = 0
    const limit = Number.isFinite(maxBytes) && maxBytes > 0 ? maxBytes : 2_000_000
    req.on("data", (buf) => {
      total += buf.length
      if (total > limit) {
        resolve({ ok: false, error: "body_too_large", maxBytes: limit })
        try {
          req.destroy()
        } catch {
          // ignore
        }
        return
      }
      chunks.push(buf)
    })
    req.on("end", () => {
      const raw = Buffer.concat(chunks).toString("utf8")
      resolve({ ok: true, raw })
    })
    req.on("error", (e) => resolve({ ok: false, error: "read_failed", message: String(e?.message ?? e) }))
  })
}

async function readJsonBody(req, { maxBytes = 2_000_000 } = {}) {
  const body = await readRequestBody(req, { maxBytes })
  if (!body.ok) return body
  try {
    const data = JSON.parse(String(body.raw ?? "").replace(/^\uFEFF/, ""))
    return { ok: true, data }
  } catch (e) {
    return { ok: false, error: "json_invalid", message: String(e?.message ?? e) }
  }
}

function sha1(text) {
  return crypto.createHash("sha1").update(String(text ?? ""), "utf8").digest("hex")
}

function sha256Hex(text) {
  return crypto.createHash("sha256").update(String(text ?? ""), "utf8").digest("hex")
}

function stableStringify(value) {
  const seen = new WeakSet()
  const normalize = (v) => {
    if (v && typeof v === "object") {
      if (seen.has(v)) throw new Error("stableStringify: cyclic object")
      seen.add(v)
      if (Array.isArray(v)) return v.map(normalize)
      const keys = Object.keys(v).sort((a, b) => (a < b ? -1 : a > b ? 1 : 0))
      const out = {}
      for (const k of keys) out[k] = normalize(v[k])
      return out
    }
    return v
  }
  return JSON.stringify(normalize(value))
}

export { readJsonBody, readRequestBody, sendJson, sendText, sha1, sha256Hex, stableStringify }

