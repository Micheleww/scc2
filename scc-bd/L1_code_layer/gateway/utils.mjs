/**
 * Gateway utilities
 */

export function sendJson(res, status, body) {
  const data = JSON.stringify(body ?? {})
  res.statusCode = status
  res.setHeader("Content-Type", "application/json; charset=utf-8")
  res.setHeader("Content-Length", Buffer.byteLength(data))
  res.end(data)
}

export function sendText(res, status, text, contentType = "text/plain; charset=utf-8") {
  const data = String(text ?? "")
  res.statusCode = status
  res.setHeader("Content-Type", contentType)
  res.setHeader("Content-Length", Buffer.byteLength(data))
  res.end(data)
}

export async function readJsonBody(req, { maxBytes = 10 * 1024 * 1024 } = {}) {
  return new Promise((resolve) => {
    let body = ""
    let length = 0
    req.on("data", (chunk) => {
      length += chunk.length
      if (length > maxBytes) {
        resolve({ ok: false, error: "payload_too_large", message: `max ${maxBytes} bytes` })
        req.destroy()
        return
      }
      body += chunk
    })
    req.on("end", () => {
      try {
        const data = JSON.parse(body || "{}")
        resolve({ ok: true, data, raw: body })
      } catch (e) {
        resolve({ ok: false, error: "json_parse_failed", message: String(e?.message ?? e) })
      }
    })
    req.on("error", (e) => {
      resolve({ ok: false, error: "read_failed", message: String(e?.message ?? e) })
    })
  })
}

export async function readRequestBody(req, { maxBytes = 10 * 1024 * 1024 } = {}) {
  return readJsonBody(req, { maxBytes })
}

export async function sha1(data) {
  const crypto = await import("node:crypto")
  return crypto.createHash("sha1").update(data).digest("hex")
}

export async function sha256Hex(data) {
  const crypto = await import("node:crypto")
  return crypto.createHash("sha256").update(data).digest("hex")
}

export function stableStringify(obj) {
  return JSON.stringify(obj, Object.keys(obj ?? {}).sort())
}
