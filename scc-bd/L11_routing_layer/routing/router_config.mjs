function registerConfigRoutes({ router }) {
  router.get("/config/schema", async (ctx) => {
    const { runtimeEnvFile, configRegistry } = ctx
    return {
      type: "json",
      status: 200,
      body: {
        runtimeEnvFile,
        registry: configRegistry,
        note: "POST /config/set writes config/runtime.env (requires daemon restart to take effect).",
      },
    }
  })

  router.get("/config", async (ctx) => {
    const {
      readRuntimeEnv,
      configRegistry,
      gatewayPort,
      sccUpstream,
      opencodeUpstream,
      codexMax,
      occliMax,
      externalMaxCodex,
      externalMaxOccli,
      desiredRatioCodex,
      desiredRatioOccli,
      timeoutCodexMs,
      timeoutOccliMs,
      modelsFree,
      modelsVision,
      preferFreeModels,
      codexPreferredOrder,
      autoCreateSplitOnTimeout,
      autoDispatchSplitTasks,
      occliModelDefault,
      autoAssignOccliModels,
      failureReportTickMs,
      failureReportTail,
      autoCancelStaleExternal,
      autoCancelExternalTickMs,
      cfg,
    } = ctx

    const runtime = readRuntimeEnv()
    const live = {
      GATEWAY_PORT: gatewayPort,
      SCC_UPSTREAM: sccUpstream.toString(),
      OPENCODE_UPSTREAM: opencodeUpstream.toString(),
      EXEC_CONCURRENCY_CODEX: codexMax,
      EXEC_CONCURRENCY_OPENCODE: occliMax,
      EXTERNAL_MAX_CODEX: externalMaxCodex,
      EXTERNAL_MAX_OPENCODECLI: externalMaxOccli,
      DESIRED_RATIO_CODEX: desiredRatioCodex,
      DESIRED_RATIO_OPENCODECLI: desiredRatioOccli,
      EXEC_TIMEOUT_CODEX_MS: timeoutCodexMs,
      EXEC_TIMEOUT_OPENCODE_MS: timeoutOccliMs,
      MODEL_POOL_FREE: modelsFree.join(","),
      MODEL_POOL_VISION: modelsVision.join(","),
      PREFER_FREE_MODELS: preferFreeModels,
      CODEX_MODEL_PREFERRED: codexPreferredOrder.join(","),
      AUTO_CREATE_SPLIT_ON_TIMEOUT: autoCreateSplitOnTimeout,
      AUTO_DISPATCH_SPLIT_TASKS: autoDispatchSplitTasks,
      OPENCODE_MODEL: occliModelDefault,
      AUTO_ASSIGN_OPENCODE_MODELS: autoAssignOccliModels,
      FAILURE_REPORT_TICK_MS: failureReportTickMs,
      FAILURE_REPORT_TAIL: failureReportTail,
      AUTO_CANCEL_STALE_EXTERNAL: autoCancelStaleExternal,
      AUTO_CANCEL_STALE_EXTERNAL_TICK_MS: autoCancelExternalTickMs,
    }

    return {
      type: "json",
      status: 200,
      body: {
        runtime,
        live,
        restartHint: {
          daemonStart: ctx.path.join(cfg.repoRoot, "oc-scc-local", "scripts", "daemon-start.ps1").replaceAll("\\\\", "/"),
          daemonStop: ctx.path.join(cfg.repoRoot, "oc-scc-local", "scripts", "daemon-stop.ps1").replaceAll("\\\\", "/"),
          note: "Changes in runtime.env apply on next daemon restart.",
        },
      },
    }
  })

  router.post("/config/set", async (ctx) => {
    const { readRuntimeEnv, writeRuntimeEnv, configRegistry, leader, runtimeEnvFile, readRequestBody } = ctx
    const body = await readRequestBody(ctx.req)
    if (!body.ok) {
      return { type: "json", status: 400, body: { error: body.error, message: body.message } }
    }

    let payload = null
    try {
      payload = JSON.parse(body.raw || "{}")
    } catch (e) {
      return { type: "json", status: 400, body: { error: "bad_json", message: String(e) } }
    }

    const allowedKeys = new Set(configRegistry.map((x) => x.key))
    const incoming = payload?.values && typeof payload.values === "object" ? payload.values : payload
    const updates = {}
    for (const [k0, v0] of Object.entries(incoming || {})) {
      const k = String(k0)
      if (!allowedKeys.has(k)) continue
      updates[k] = v0
    }

    const current = readRuntimeEnv()
    const next = { ...(current.values ?? {}) }

    const typeByKey = Object.fromEntries(configRegistry.map((x) => [x.key, x.type]))
    const errors = []
    for (const [k, v] of Object.entries(updates)) {
      const t = typeByKey[k] ?? "string"
      if (v == null) {
        delete next[k]
        continue
      }
      if (t === "number") {
        const n = Number(v)
        if (!Number.isFinite(n)) {
          errors.push({ key: k, error: "not_a_number" })
          continue
        }
        next[k] = String(n)
        continue
      }
      if (t === "bool") {
        const s = String(v).toLowerCase()
        if (!["true", "false", "1", "0"].includes(s)) {
          errors.push({ key: k, error: "not_a_bool" })
          continue
        }
        next[k] = s === "1" ? "true" : s === "0" ? "false" : s
        continue
      }
      next[k] = String(v)
    }

    if (errors.length) {
      leader({ level: "warn", type: "config_set_rejected", errors })
      return { type: "json", status: 400, body: { error: "validation_failed", errors } }
    }

    writeRuntimeEnv(next)
    leader({ level: "info", type: "config_set", keys: Object.keys(updates).sort() })
    return { type: "json", status: 200, body: { ok: true, runtimeEnvFile, values: next, restartRequired: true } }
  })
}

export { registerConfigRoutes }
