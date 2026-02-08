// Core routes extracted from gateway.mjs to start chipping away at the god-file.
// This module is intentionally small and self-contained.

function registerCoreRoutes({ router }) {
  // Prometheus-style metrics (minimal).
  router.get("/metrics", async (ctx) => {
    const { listBoardTasks, runningCounts, jobs, quarantineActive } = ctx
    const board = listBoardTasks()
    const statusCounts = {}
    for (const t of board) {
      const st = String(t?.status ?? "unknown")
      statusCounts[st] = (statusCounts[st] ?? 0) + 1
    }
    const running = runningCounts()
    const now = Date.now()

    const lines = []
    lines.push("# HELP scc_gateway_up 1 if gateway is running")
    lines.push("# TYPE scc_gateway_up gauge")
    lines.push("scc_gateway_up 1")

    lines.push("# HELP scc_gateway_time_ms Current unix time in ms")
    lines.push("# TYPE scc_gateway_time_ms gauge")
    lines.push(`scc_gateway_time_ms ${now}`)

    lines.push("# HELP scc_board_tasks_total Total tasks on board")
    lines.push("# TYPE scc_board_tasks_total gauge")
    lines.push(`scc_board_tasks_total ${board.length}`)

    lines.push("# HELP scc_jobs_total Total jobs in queue map")
    lines.push("# TYPE scc_jobs_total gauge")
    lines.push(`scc_jobs_total ${jobs.size}`)

    lines.push("# HELP scc_running_codex Running codex jobs")
    lines.push("# TYPE scc_running_codex gauge")
    lines.push(`scc_running_codex ${running.codex}`)

    lines.push("# HELP scc_running_opencodecli Running opencodecli jobs")
    lines.push("# TYPE scc_running_opencodecli gauge")
    lines.push(`scc_running_opencodecli ${running.opencodecli}`)

    lines.push("# HELP scc_quarantine_active Whether circuit breaker quarantine is active (0/1)")
    lines.push("# TYPE scc_quarantine_active gauge")
    lines.push(`scc_quarantine_active ${quarantineActive() ? 1 : 0}`)

    lines.push("# HELP scc_board_tasks_by_status Tasks by status")
    lines.push("# TYPE scc_board_tasks_by_status gauge")
    for (const [st, n] of Object.entries(statusCounts)) {
      const label = String(st).replace(/\\/g, "_").replace(/\"/g, "'")
      lines.push(`scc_board_tasks_by_status{status=\"${label}\"} ${n}`)
    }

    return { type: "text", status: 200, contentType: "text/plain; version=0.0.4; charset=utf-8", body: lines.join("\n") + "\n" }
  })

  router.get("/health", async () => ({ type: "json", status: 200, body: { ok: true } }))

  router.get("/healthz", async (ctx) => {
    const { http, fs, path, URL, execLogDir, boardDir, docsRoot, sccUpstream, opencodeUpstream } = ctx
    const checks = []
    const t0 = Date.now()

    function checkFsWritableDir(name, dir) {
      const started = Date.now()
      try {
        fs.mkdirSync(dir, { recursive: true })
        const probe = path.join(dir, `.healthz_${process.pid}_${Math.random().toString(16).slice(2)}.tmp`)
        fs.writeFileSync(probe, "ok\n", "utf8")
        fs.unlinkSync(probe)
        checks.push({ name, ok: true, ms: Date.now() - started })
      } catch (e) {
        checks.push({ name, ok: false, ms: Date.now() - started, error: String(e?.message ?? e) })
      }
    }

    async function probeHttp(name, baseUrl) {
      const started = Date.now()
      const target = new URL("/health", baseUrl)
      const timeoutMs = 1200
      try {
        const ok = await new Promise((resolve, reject) => {
          const req2 = http.request(
            target,
            { method: "GET", timeout: timeoutMs },
            (resp) => {
              resp.on("data", () => {})
              resp.on("end", () => resolve(resp.statusCode >= 200 && resp.statusCode < 300))
            },
          )
          req2.on("timeout", () => req2.destroy(new Error("timeout")))
          req2.on("error", reject)
          req2.end()
        })
        checks.push({ name, ok: Boolean(ok), ms: Date.now() - started, url: String(target) })
      } catch (e) {
        checks.push({ name, ok: false, ms: Date.now() - started, url: String(target), error: String(e?.message ?? e) })
      }
    }

    checkFsWritableDir("exec_log_dir_writable", execLogDir)
    checkFsWritableDir("board_dir_writable", boardDir)
    checkFsWritableDir("docs_root_writable", docsRoot)
    await probeHttp("scc_upstream_health", sccUpstream)
    await probeHttp("opencode_upstream_health", opencodeUpstream)

    const ok = checks.every((c) => c.ok)
    return { type: "json", status: ok ? 200 : 503, body: { ok, t: new Date().toISOString(), ms: Date.now() - t0, checks } }
  })

  router.get("/debug/state", async (ctx) => {
    const { listBoardTasks, runningCounts, jobs, loadRepoHealthState, loadCircuitBreakerState, quarantineActive, repoUnhealthyActive, SCC_REPO_ROOT, execLogDir, boardDir, docsRoot } = ctx
    const board = listBoardTasks()
    const byStatus = {}
    for (const t of board) {
      const st = String(t?.status ?? "unknown")
      byStatus[st] = (byStatus[st] ?? 0) + 1
    }
    const running = runningCounts()
    const repoHealth = loadRepoHealthState()
    const breaker = loadCircuitBreakerState()
    return {
      type: "json",
      status: 200,
      body: {
        ok: true,
        t: new Date().toISOString(),
        repoRoot: SCC_REPO_ROOT,
        dirs: { execLogDir, boardDir, docsRoot },
        board: { total: board.length, byStatus },
        jobs: { total: jobs.size },
        running,
        factory: {
          quarantine_active: quarantineActive(),
          repo_unhealthy_active: repoUnhealthyActive(),
          repo_health: repoHealth,
          circuit_breaker: breaker,
        },
      },
    }
  })

  router.get("/debug/errors/recent", async (ctx) => {
    const { url, readJsonlTail, gatewayErrorsFile, sendJson } = ctx
    const n = Math.max(1, Math.min(5000, Number(url.searchParams.get("n") ?? "200")))
    const items = readJsonlTail(gatewayErrorsFile, Number.isFinite(n) ? n : 200)
    // Return JSON to preserve previous behavior (gateway uses sendJson).
    return { type: "json", status: 200, body: { ok: true, file: gatewayErrorsFile, n, items } }
  })
}

export { registerCoreRoutes }

