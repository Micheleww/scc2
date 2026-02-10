import { buildPinsFromMapV1, writePinsV1Outputs } from "../../L2_task_layer/pins/pins_builder_v1.mjs"

function registerPinsRoutes({ router }) {
  // GET /pins/templates - List available pin templates
  router.get("/pins/templates", async (ctx) => {
    const { SCC_REPO_ROOT } = ctx
    return {
      type: "json",
      status: 200,
      body: {
        ok: true,
        templates: [
          { id: "default", name: "Default", description: "Default pin template" },
          { id: "strict", name: "Strict", description: "Strict mode with limited paths" },
          { id: "liberal", name: "Liberal", description: "Liberal mode with broader access" }
        ]
      }
    }
  })

  // GET /pins/candidates - List pin candidates for a task
  router.get("/pins/candidates", async (ctx) => {
    const { url, SCC_REPO_ROOT } = ctx
    const taskId = url.searchParams.get("task_id") || "unknown"
    return {
      type: "json",
      status: 200,
      body: {
        ok: true,
        task_id: taskId,
        candidates: []
      }
    }
  })

  // Pins Builder v1 (Map-first, deterministic)
  router.post("/pins/v1/build", async (ctx) => {
    const { req, sendJson, SCC_REPO_ROOT, readJsonBody, noteBestEffort } = ctx
    const body = await readJsonBody(req, { maxBytes: 2_000_000 })
    if (!body.ok) return { type: "json", status: 400, body }
    const request = body.data
    const out = buildPinsFromMapV1({ repoRoot: SCC_REPO_ROOT, request })
    if (!out.ok) return { type: "json", status: 400, body: out }
    try {
      writePinsV1Outputs({
        repoRoot: SCC_REPO_ROOT,
        taskId: out.result.task_id,
        outDir: `artifacts/${out.result.task_id}/pins`,
        pinsResult: out.result_v2 ?? out.result,
        pinsSpec: out.pins,
        detail: out.detail,
      })
    } catch (e) {
      noteBestEffort("pins_v1_write_outputs", e, { task_id: out.result.task_id })
    }
    return { type: "json", status: 200, body: { ok: true, pins_result: out.result, pins_result_v2: out.result_v2 ?? null } }
  })

  // Pins Builder v2 (audited pins)
  router.post("/pins/v2/build", async (ctx) => {
    const { req, sendJson, SCC_REPO_ROOT, readJsonBody, noteBestEffort } = ctx
    const body = await readJsonBody(req, { maxBytes: 2_000_000 })
    if (!body.ok) return { type: "json", status: 400, body }
    const request = body.data
    const out = buildPinsFromMapV1({ repoRoot: SCC_REPO_ROOT, request })
    if (!out.ok) return { type: "json", status: 400, body: out }
    const v2 = out.result_v2
    if (!v2) return { type: "json", status: 500, body: { ok: false, error: "pins_v2_missing" } }
    try {
      writePinsV1Outputs({
        repoRoot: SCC_REPO_ROOT,
        taskId: v2.task_id,
        outDir: `artifacts/${v2.task_id}/pins`,
        pinsResult: v2,
        pinsSpec: out.pins,
        detail: out.detail,
      })
    } catch (e) {
      noteBestEffort("pins_v2_write_outputs", e, { task_id: v2.task_id })
    }
    return { type: "json", status: 200, body: { ok: true, pins_result_v2: v2 } }
  })
}

export { registerPinsRoutes }
