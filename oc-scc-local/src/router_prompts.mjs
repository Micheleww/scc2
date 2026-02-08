function registerPromptsRoutes({ router }) {
  router.get("/prompts/registry", async (ctx) => {
    const { promptRegistry } = ctx
    const info = promptRegistry.info()
    const code = info.ok ? 200 : 500
    return { type: "json", status: code, body: info }
  })

  router.post("/prompts/render", async (ctx) => {
    const { promptRegistry, readRequestBody } = ctx
    const body = await readRequestBody(ctx.req)
    if (!body.ok) {
      return { type: "json", status: 400, body: { ok: false, error: body.error, message: body.message } }
    }

    let payload = null
    try {
      payload = JSON.parse(body.raw || "{}")
    } catch (e) {
      return { type: "json", status: 400, body: { ok: false, error: "bad_json", message: String(e) } }
    }

    const role_id = payload?.role_id ?? payload?.roleId ?? null
    const preset_id = payload?.preset_id ?? payload?.presetId ?? null
    const params = payload?.params && typeof payload.params === "object" ? payload.params : {}
    const out = promptRegistry.render({ role_id, preset_id, params })
    const code = out.ok ? 200 : 400
    return { type: "json", status: code, body: out }
  })
}

export { registerPromptsRoutes }
