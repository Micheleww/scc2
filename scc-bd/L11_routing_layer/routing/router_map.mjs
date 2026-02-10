import { execFileSync } from "node:child_process"

function registerMapRoutes({ router }) {
  // Map v1 (structured index): file-backed, deterministic, queryable.
  router.get("/map/v1/version", async (ctx) => {
    const { fs, path, SCC_REPO_ROOT } = ctx
    try {
      const p = path.join(SCC_REPO_ROOT, "map", "version.json")
      if (!fs.existsSync(p)) return { type: "json", status: 404, body: { error: "map_version_missing", path: p } }
      const raw = fs.readFileSync(p, "utf8")
      const data = JSON.parse(raw.replace(/^\uFEFF/, ""))
      return { type: "json", status: 200, body: { ok: true, path: p, data } }
    } catch (e) {
      return { type: "json", status: 500, body: { error: "map_version_read_failed", message: String(e?.message ?? e) } }
    }
  })

  router.get("/map/v1/link_report", async (ctx) => {
    const { fs, path, SCC_REPO_ROOT } = ctx
    try {
      const p = path.join(SCC_REPO_ROOT, "map", "link_report.json")
      if (!fs.existsSync(p)) return { type: "json", status: 404, body: { error: "link_report_missing", path: p } }
      const raw = fs.readFileSync(p, "utf8")
      const data = JSON.parse(raw.replace(/^\uFEFF/, ""))
      return { type: "json", status: 200, body: { ok: true, path: p, data } }
    } catch (e) {
      return { type: "json", status: 500, body: { error: "link_report_read_failed", message: String(e?.message ?? e) } }
    }
  })

  router.get("/map/v1/query", async (ctx) => {
    const { url, fs, path, SCC_REPO_ROOT, sendJson, loadMapV1, queryMapV1 } = ctx
    const q = url.searchParams.get("q") ?? ""
    const limit = Number(url.searchParams.get("limit") ?? "20")
    try {
      const backend = String(url.searchParams.get("backend") ?? process.env.MAP_QUERY_BACKEND ?? "").toLowerCase()
      const wantSqlite = backend === "sqlite"
      const strict = (() => {
        const v = String(process.env.MAP_QUERY_STRICT ?? "auto").toLowerCase()
        if (v === "auto") return wantSqlite
        return v === "1" || v === "true" || v === "yes" || v === "on"
      })()
      const sqlitePath = path.join(SCC_REPO_ROOT, "map", "map.sqlite")
      if (wantSqlite && strict && !fs.existsSync(sqlitePath)) {
        return { type: "json", status: 400, body: { ok: false, error: "missing_sqlite", db: "map/map.sqlite", hint: "Rebuild map with sqlite (POST /map/v1/build)" } }
      }
      if (wantSqlite && fs.existsSync(sqlitePath)) {
        const root = SCC_REPO_ROOT
        const stdout = execFileSync(
          "python",
          ["L17_ontology_layer/map/map_query_sqlite_v1.py", "--repo-root", root, "--db", "map/map.sqlite", "--q", String(q), "--limit", String(Number.isFinite(limit) ? limit : 20)],
          { cwd: root, windowsHide: true, timeout: 20000, maxBuffer: 10 * 1024 * 1024, encoding: "utf8" },
        )
        const out = JSON.parse(String(stdout ?? "").replace(/^\uFEFF/, ""))
        return { type: "json", status: 200, body: { ok: true, backend: "sqlite", ...out } }
      }

      const loaded = loadMapV1({ repoRoot: SCC_REPO_ROOT, mapPath: "map/map.json" })
      const out = queryMapV1({ map: loaded.data, q, limit: Number.isFinite(limit) ? limit : 20 })
      if (!out.ok) return { type: "json", status: 400, body: out }
      return { type: "json", status: 200, body: { ok: true, backend: "json", ...out } }
    } catch (e) {
      return { type: "json", status: 500, body: { error: "map_query_failed", message: String(e?.message ?? e) } }
    }
  })

  router.get("/map/v1", async (ctx) => {
    const { fs, path, SCC_REPO_ROOT } = ctx
    try {
      const versionPath = path.join(SCC_REPO_ROOT, "map", "version.json")
      const linkPath = path.join(SCC_REPO_ROOT, "map", "link_report.json")
      const version = fs.existsSync(versionPath) ? JSON.parse(fs.readFileSync(versionPath, "utf8").replace(/^\uFEFF/, "")) : null
      const link = fs.existsSync(linkPath) ? JSON.parse(fs.readFileSync(linkPath, "utf8").replace(/^\uFEFF/, "")) : null
      return {
        type: "json",
        status: 200,
        body: {
          ok: true,
          version: version ? { hash: version.hash ?? null, generated_at: version.generated_at ?? null, stats: version.stats ?? null } : null,
          link_report: link ? { generated_at: link.generated_at ?? null, counts: link.counts ?? null } : null,
          endpoints: {
            version: "/map/v1/version",
            query: "/map/v1/query?q=...&limit=20",
            link_report: "/map/v1/link_report",
            build: "/map/v1/build",
          },
        },
      }
    } catch (e) {
      return { type: "json", status: 500, body: { error: "map_v1_failed", message: String(e?.message ?? e) } }
    }
  })

  router.post("/map/v1/build", async (ctx) => {
    const { runMapBuild } = ctx
    const out = await runMapBuild({ reason: "api" })
    return { type: "json", status: out.ok ? 200 : 500, body: out }
  })

  // Legacy /map endpoint
  router.get("/map", async (ctx) => {
    const { fs, path, SCC_REPO_ROOT } = ctx
    const indexPath = path.join(SCC_REPO_ROOT, "map", "index.json")
    if (!fs.existsSync(indexPath)) {
      return { type: "json", status: 404, body: { error: "map_index_missing", path: "map/index.json" } }
    }
    try {
      const raw = fs.readFileSync(indexPath, "utf8")
      const data = JSON.parse(raw.replace(/^\uFEFF/, ""))
      return { type: "json", status: 200, body: { ok: true, data } }
    } catch (e) {
      return { type: "json", status: 500, body: { error: "map_index_read_failed", message: String(e?.message ?? e) } }
    }
  })
}

export { registerMapRoutes }
