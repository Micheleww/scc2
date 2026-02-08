import { URL } from "node:url"

function createRouter() {
  const routes = new Map()

  function key(method, pathname) {
    return `${String(method).toUpperCase()} ${pathname}`
  }

  function get(pathname, handler) {
    routes.set(key("GET", pathname), handler)
  }

  function post(pathname, handler) {
    routes.set(key("POST", pathname), handler)
  }

  async function handle(req, res, ctx) {
    const method = String(req?.method ?? "GET").toUpperCase()
    const url = new URL(req.url ?? "/", `http://127.0.0.1:${ctx?.gatewayPort ?? 18788}`)
    const pathname = url.pathname

    const h = routes.get(key(method, pathname))
    if (!h) return { handled: false, url, pathname }

    try {
      const out = await h({ ...ctx, url, pathname, method, req, res })
      if (!out || typeof out !== "object") {
        ctx.sendJson(res, 500, { ok: false, error: "router_handler_invalid_return", route: `${method} ${pathname}` })
        return { handled: true, url, pathname }
      }
      if (out.type === "json") {
        ctx.sendJson(res, Number(out.status ?? 200), out.body ?? {})
        return { handled: true, url, pathname }
      }
      if (out.type === "text") {
        res.statusCode = Number(out.status ?? 200)
        if (out.contentType) res.setHeader("Content-Type", String(out.contentType))
        res.end(String(out.body ?? ""))
        return { handled: true, url, pathname }
      }
      ctx.sendJson(res, 500, { ok: false, error: "router_handler_unknown_type", type: String(out.type ?? "") })
      return { handled: true, url, pathname }
    } catch (e) {
      ctx.errSink?.note?.({ level: "error", where: `router:${method} ${pathname}`, err: ctx.log?.errToObject ? ctx.log.errToObject(e) : String(e?.message ?? e) })
      ctx.sendJson(res, 500, { ok: false, error: "router_handler_failed", route: `${method} ${pathname}`, message: String(e?.message ?? e) })
      return { handled: true, url, pathname }
    }
  }

  return { get, post, handle }
}

export { createRouter }

