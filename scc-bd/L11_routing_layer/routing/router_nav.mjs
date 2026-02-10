function registerNavRoutes({ router }) {
  router.get("/nav", async (ctx) => {
    const { gatewayPort, SCC_PREFIXES } = ctx

    return {
      type: "json",
      status: 200,
      body: {
        base: `http://127.0.0.1:${gatewayPort}`,
        scc: SCC_PREFIXES,
        opencode: "/opencode/*",
        docs: "/docs/*",
        board: "/board/*",
        pools: "/pools",
        config: {
          schema: "/config/schema",
          get: "/config",
          set: "/config/set",
        },
        models: {
          list: "/models",
          set: "/models/set",
        },
        designer: {
          state: "/designer/state",
          freeze: "/designer/freeze",
          context_pack: "/designer/context_pack",
        },
        map: "/map",
        map_v1: {
          summary: "/map/v1",
          version: "/map/v1/version",
          query: "/map/v1/query?q=...&limit=20",
          link_report: "/map/v1/link_report",
          build: "/map/v1/build",
        },
        axioms: "/axioms",
        task_classes: "/task_classes",
        pins_templates: "/pins/templates",
        pins_candidates: "/pins/candidates",
        pins_v1: { build: "/pins/v1/build" },
        events: "/events",
        preflight_v1: { check: "/preflight/v1/check" },
        dlq: "/dlq",
        learned_patterns: {
          list: "/learned_patterns",
          summary: "/learned_patterns/summary",
        },
        learn_v1: {
          mine: "/learn/v1/mine",
          tick: "/learn/v1/tick",
        },
        eval_v1: {
          replay: "/eval/v1/replay",
        },
        playbooks_v1: {
          publish: "/playbooks/v1/publish",
        },
        metrics_v1: {
          rollup: "/metrics/v1/rollup",
        },
        instinct: {
          patterns: "/instinct/patterns",
          schemas: "/instinct/schemas",
          playbooks: "/instinct/playbooks",
          skills_draft: "/instinct/skills_draft",
        },
        replay: {
          task: "/replay/task?task_id=...",
        },
        replay_v1: {
          smoke: "/replay/v1/smoke",
        },
        verdict: {
          get: "/verdict?task_id=...",
        },
        executor: {
          atomic: "/executor/jobs/atomic",
          jobs: "/executor/jobs",
          leader: "/executor/leader",
          failures: "/executor/debug/failures",
          summary: "/executor/debug/summary",
          workers: "/executor/workers",
        },
        prompts: {
          registry: "/prompts/registry",
          render: "/prompts/render",
        },
        factory: {
          policy: "/factory/policy",
          wip: "/factory/wip",
          degradation: "/factory/degradation",
          health: "/factory/health",
          routing: "/factory/routing?event_type=CI_FAILED",
        },
      },
    }
  })
}

export { registerNavRoutes }

