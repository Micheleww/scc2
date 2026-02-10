function registerModelsRoutes({ router }) {
  router.get("/models", async (ctx) => {
    const {
      modelsFree,
      modelsVision,
      occliModelDefault,
      codexModelDefault,
      codexPreferredOrder,
      modelsPaid,
      STRICT_DESIGNER_MODEL,
    } = ctx
    return {
      type: "json",
      status: 200,
      body: {
        free: modelsFree,
        vision: modelsVision,
        opencodeDefault: occliModelDefault,
        codexDefault: codexModelDefault,
        codexPreferred: codexPreferredOrder,
        codexPaidPool: modelsPaid,
        strictDesignerModel: STRICT_DESIGNER_MODEL,
        note: "POST /models/set to update in-memory + runtime.env (opencode + codex). Back-compat fields: free/vision/opencodeDefault.",
      },
    }
  })

  router.post("/models/set", async (ctx) => {
    const {
      updateModelPools,
      updateCodexModelPolicy,
      readRuntimeEnv,
      writeRuntimeEnv,
      runtimeEnvFile,
      leader,
      modelsFree,
      modelsVision,
      modelsPaid,
      occliModelDefault,
      codexModelDefault,
      codexPreferredOrder,
      STRICT_DESIGNER_MODEL,
      readRequestBody,
    } = ctx

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

    const free = Array.isArray(payload?.free) ? payload.free.map((x) => String(x).trim()).filter(Boolean) : null
    const vision = Array.isArray(payload?.vision) ? payload.vision.map((x) => String(x).trim()).filter(Boolean) : null
    const opDefault = payload?.opencodeDefault ? String(payload.opencodeDefault).trim() : null
    const codexDefault = payload?.codexDefault != null ? String(payload.codexDefault).trim() : null
    const codexPreferred = Array.isArray(payload?.codexPreferred) ? payload.codexPreferred : null
    const codexPaidPool = Array.isArray(payload?.codexPaidPool) ? payload.codexPaidPool : null
    const strictDesignerModel = payload?.strictDesignerModel != null ? String(payload.strictDesignerModel).trim() : null

    if (free && !free.length) return { type: "json", status: 400, body: { error: "free_empty" } }
    if (vision && !vision.length) return { type: "json", status: 400, body: { error: "vision_empty" } }

    updateModelPools({ free, vision, occliDefault: opDefault })
    const codexOut = updateCodexModelPolicy({ codexDefault, codexPreferred, paidPool: codexPaidPool, strictDesignerModel })
    if (!codexOut.ok) return { type: "json", status: 400, body: { error: codexOut.error ?? "codex_policy_invalid" } }

    // persist to runtime.env for next restart
    const current = readRuntimeEnv()
    const next = { ...(current.values ?? {}) }
    next.MODEL_POOL_FREE = modelsFree.join(",")
    next.MODEL_POOL_VISION = modelsVision.join(",")
    next.OPENCODE_MODEL = occliModelDefault
    next.CODEX_MODEL = codexModelDefault
    next.CODEX_MODEL_PREFERRED = codexPreferredOrder.join(",")
    next.MODEL_POOL_PAID = modelsPaid.join(",")
    next.STRICT_DESIGNER_MODEL = STRICT_DESIGNER_MODEL
    writeRuntimeEnv(next)

    leader({
      level: "info",
      type: "models_updated",
      free: modelsFree,
      vision: modelsVision,
      opencodeDefault: occliModelDefault,
      codexDefault: codexModelDefault,
      codexPreferred: codexPreferredOrder,
      strictDesignerModel: STRICT_DESIGNER_MODEL,
    })

    return {
      type: "json",
      status: 200,
      body: {
        ok: true,
        free: modelsFree,
        vision: modelsVision,
        opencodeDefault: occliModelDefault,
        codexDefault: codexModelDefault,
        codexPreferred: codexPreferredOrder,
        codexPaidPool: modelsPaid,
        strictDesignerModel: STRICT_DESIGNER_MODEL,
        persisted: runtimeEnvFile,
        restartRequired: false,
      },
    }
  })
}

export { registerModelsRoutes }
