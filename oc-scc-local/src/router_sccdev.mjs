function boardCounts(boardAll) {
  const counts = { total: boardAll.length }
  for (const t of boardAll) {
    const st = String(t?.status ?? "unknown")
    counts[st] = (counts[st] ?? 0) + 1
  }
  return counts
}

function registerSccDevRoutes({ router }) {
  router.get("/sccdev/api/v1/snapshot", async (ctx) => {
    const { url, sendJson } = ctx
    // NOTE: sendJson is intentionally unused here (router handles JSON),
    // but exists in ctx for consistency with other extracted routes.
    void sendJson

    const taskLimit = Number(url.searchParams.get("tasks") ?? "200")
    const eventLimit = Number(url.searchParams.get("events") ?? "120")
    const jobLimit = Number(url.searchParams.get("jobs") ?? "200")

    const capTasks = Number.isFinite(taskLimit) ? Math.max(0, Math.min(1000, Math.floor(taskLimit))) : 200
    const capEvents = Number.isFinite(eventLimit) ? Math.max(0, Math.min(2000, Math.floor(eventLimit))) : 120
    const capJobs = Number.isFinite(jobLimit) ? Math.max(0, Math.min(2000, Math.floor(jobLimit))) : 200

    const boardAll = ctx.listBoardTasks()
    const tasks = boardAll
      .slice()
      .sort((a, b) => (b.updatedAt ?? b.createdAt ?? 0) - (a.updatedAt ?? a.createdAt ?? 0))
      .slice(0, capTasks)

    const jobArrAll = Array.from(ctx.jobs.values())
    const jobArr = jobArrAll
      .slice()
      .sort((a, b) => (b.lastUpdate ?? b.startedAt ?? 0) - (a.lastUpdate ?? a.startedAt ?? 0))
      .slice(0, capJobs)

    const byStatus = {}
    for (const j of jobArrAll) {
      const s = String(j?.status ?? "unknown")
      byStatus[s] = (byStatus[s] ?? 0) + 1
    }

    const workersAll = ctx.listWorkers()
    const activeWindowMs = Number(process.env.WORKER_ACTIVE_WINDOW_MS ?? "120000")
    const now = Date.now()
    const active = workersAll.filter((w) => typeof w.lastSeen === "number" && now - w.lastSeen <= activeWindowMs)
    const byExecutorActive = {}
    for (const w of active) {
      const ex = Array.isArray(w.executors) ? w.executors.join(",") : "unknown"
      byExecutorActive[ex] = (byExecutorActive[ex] ?? 0) + 1
    }

    const ev = ctx.readJsonlTail(ctx.stateEventsFile, capEvents).filter(Boolean)

    const limits = ctx.wipLimits()
    const snap = ctx.runningInternalByLane()
    const degradation = ctx.computeDegradationState({ snap })
    const effective_limits = ctx.applyDegradationToWipLimitsV1({ limits, action: degradation.action })

    const models = {
      codexDefault: ctx.codexModelDefault,
      codexPreferred: ctx.codexPreferredOrder ?? [],
      strictDesignerModel: ctx.STRICT_DESIGNER_MODEL,
      routerStatsSummary: ctx.summarizeRouterStatsForUi(),
    }

    return {
      type: "json",
      status: 200,
      body: {
        ok: true,
        schema_version: "scc.sccdev_snapshot.v1",
        t: new Date().toISOString(),
        repoRoot: ctx.SCC_REPO_ROOT,
        board: { counts: boardCounts(boardAll), tasks },
        executor: {
          jobs: { byStatus, items: jobArr },
          workers: { items: workersAll, activeWindowMs, byExecutorActive },
        },
        factory: { wip: { limits, effective_limits, running: snap }, degradation, repo_health: ctx.repoHealthState },
        models,
        events: { file: ctx.stateEventsFile, items: ev },
      },
    }
  })
}

export { registerSccDevRoutes }

