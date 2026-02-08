// Minimal plugin skeleton (v1).
//
// Host MUST provide ctx:
// - leader(event)
// - createTask(payload)
// - dispatch(taskId)
// - readJson(path)
// - writeJson(path, obj)
//
// Plugin MUST be fail-closed: if fields are missing, do nothing.

export function register(ctx) {
  return {
    id: "example.echo",
    plugin_api: "v1",
    hooks: {
      after_job_finished: async (ev) => {
        if (!ev || !ev.job || !ev.task) return
        ctx.leader({ level: "info", type: "plugin_example_echo", task_id: ev.task.id, job_id: ev.job.id })
      },
    },
    commands: {
      echo: async ({ message }) => {
        ctx.leader({ level: "info", type: "plugin_command_echo", message: String(message ?? "") })
        return { ok: true }
      },
    },
  }
}

