function registerFactoryRoutes({ router }) {
  router.get("/pools", async (ctx) => ({ type: "json", status: 200, body: ctx.poolSnapshot() }))

  router.get("/factory/policy", async (ctx) => {
    const fp = ctx.getFactoryPolicy()
    if (!fp) return { type: "json", status: 404, body: { error: "missing_factory_policy", file: "config/factory_policy.json" } }
    return { type: "json", status: 200, body: fp }
  })

  router.get("/factory/wip", async (ctx) => {
    const limits = ctx.wipLimits()
    const snap = ctx.runningInternalByLane()
    const degradation = ctx.computeDegradationState({ snap })
    const effective_limits = ctx.applyDegradationToWipLimitsV1({ limits, action: degradation.action })
    return { type: "json", status: 200, body: { limits, effective_limits, running: snap, degradation } }
  })

  router.get("/factory/degradation", async (ctx) => {
    const snap = ctx.runningInternalByLane()
    const state = ctx.computeDegradationState({ snap })
    return { type: "json", status: 200, body: state }
  })

  router.get("/factory/health", async (ctx) => {
    const snap = ctx.runningInternalByLane()
    const degradation = ctx.computeDegradationState({ snap })
    return {
      type: "json",
      status: 200,
      body: {
        repo_health: ctx.repoHealthState,
        circuit_breakers: ctx.circuitBreakerState,
        quarantine_active: ctx.quarantineActive(),
        degradation,
      },
    }
  })

  router.post("/factory/health/reset", async (ctx) => {
    const next = {
      schema_version: "scc.repo_health_state.v1",
      updated_at: new Date().toISOString(),
      failures: [],
      unhealthy_until: 0,
      unhealthy_reason: null,
      unhealthy_task_created_at: null,
    }
    ctx.setRepoHealthState(next)
    ctx.saveRepoHealthState(next)
    ctx.leader({ level: "warn", type: "repo_health_reset", reason: "manual_api" })
    return { type: "json", status: 200, body: { ok: true, repo_health: next } }
  })

  router.get("/factory/routing", async (ctx) => {
    const et = String(ctx.url.searchParams.get("event_type") ?? "").trim()
    if (!et) return { type: "json", status: 400, body: { error: "missing_event_type" } }
    const lane = ctx.routeLaneForEventType(et)
    return { type: "json", status: 200, body: { event_type: et, lane, factory_policy: "config/factory_policy.json" } }
  })
}

export { registerFactoryRoutes }

