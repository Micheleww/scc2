import { URL } from "node:url"

function createRouter() {
  const routes = new Map()
  const wildcards = [] // Array of { method, pattern, handler }

  function key(method, pathname) {
    return `${String(method).toUpperCase()} ${pathname}`
  }

  function get(pathname, handler) {
    if (pathname.includes('*')) {
      wildcards.push({ method: "GET", pattern: pathname, handler })
    } else {
      routes.set(key("GET", pathname), handler)
    }
  }

  function post(pathname, handler) {
    if (pathname.includes('*')) {
      wildcards.push({ method: "POST", pattern: pathname, handler })
    } else {
      routes.set(key("POST", pathname), handler)
    }
  }

  function all(pathname, handler) {
    if (pathname.includes('*')) {
      wildcards.push({ method: "ALL", pattern: pathname, handler })
    } else {
      routes.set(key("GET", pathname), handler)
      routes.set(key("POST", pathname), handler)
      routes.set(key("PUT", pathname), handler)
      routes.set(key("DELETE", pathname), handler)
      routes.set(key("PATCH", pathname), handler)
    }
  }

  function matchWildcard(method, pathname) {
    for (const route of wildcards) {
      if (route.method !== "ALL" && route.method !== method) continue
      
      // Convert pattern to regex
      // Replace * with capture group
      const pattern = route.pattern
        .replace(/\*/g, '([^/]+)')
        .replace(/\//g, '\\/')
      
      const regex = new RegExp(`^${pattern}$`)
      const match = pathname.match(regex)
      
      if (match) {
        return { handler: route.handler, params: match.slice(1) }
      }
    }
    return null
  }

  async function handle(req, res, ctx) {
    const method = String(req?.method ?? "GET").toUpperCase()
    const url = new URL(req.url ?? "/", `http://127.0.0.1:${ctx?.gatewayPort ?? 18788}`)
    const pathname = url.pathname

    // Try exact match first
    const h = routes.get(key(method, pathname))
    if (h) {
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
        // If handler returns handled: false, continue to next route
        if (out.handled === false) {
          return { handled: false, url, pathname }
        }
        ctx.sendJson(res, 500, { ok: false, error: "router_handler_unknown_type", type: String(out.type ?? "") })
        return { handled: true, url, pathname }
      } catch (e) {
        ctx.errSink?.note?.({ level: "error", where: `router:${method} ${pathname}`, err: ctx.log?.errToObject ? ctx.log.errToObject(e) : String(e?.message ?? e) })
        ctx.sendJson(res, 500, { ok: false, error: "router_handler_failed", route: `${method} ${pathname}`, message: String(e?.message ?? e) })
        return { handled: true, url, pathname }
      }
    }

    // Try wildcard match
    const wildcardMatch = matchWildcard(method, pathname)
    if (wildcardMatch) {
      try {
        const out = await wildcardMatch.handler({ 
          ...ctx, 
          url, 
          pathname, 
          method, 
          req, 
          res,
          params: wildcardMatch.params 
        })
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
        if (out.handled === false) {
          return { handled: false, url, pathname }
        }
        ctx.sendJson(res, 500, { ok: false, error: "router_handler_unknown_type", type: String(out.type ?? "") })
        return { handled: true, url, pathname }
      } catch (e) {
        ctx.errSink?.note?.({ level: "error", where: `router:${method} ${pathname}`, err: ctx.log?.errToObject ? ctx.log.errToObject(e) : String(e?.message ?? e) })
        ctx.sendJson(res, 500, { ok: false, error: "router_handler_failed", route: `${method} ${pathname}`, message: String(e?.message ?? e) })
        return { handled: true, url, pathname }
      }
    }

    return { handled: false, url, pathname }
  }

  return { get, post, all, handle }
}

export { createRouter }
