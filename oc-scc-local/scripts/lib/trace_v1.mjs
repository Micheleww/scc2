import crypto from "node:crypto"
import fs from "node:fs"
import path from "node:path"

function sha256FileOrNull(file) {
  try {
    if (!fs.existsSync(file)) return null
    const buf = fs.readFileSync(file)
    return `sha256:${crypto.createHash("sha256").update(buf).digest("hex")}`
  } catch {
    return null
  }
}

export function writeTraceV1({ repoRoot, taskId, routing }) {
  const tid = String(taskId ?? "").trim()
  if (!tid) throw new Error("missing taskId")
  const root = String(repoRoot ?? "").trim()
  if (!root) throw new Error("missing repoRoot")

  const artDir = path.join(root, "artifacts", tid)
  const submitPath = path.join(artDir, "submit.json")
  if (!fs.existsSync(submitPath)) throw new Error(`missing submit.json: ${submitPath}`)

  const now = new Date().toISOString()
  const trace = {
    schema_version: "scc.trace.v1",
    task_id: tid,
    created_at: now,
    updated_at: now,
    config_hashes: {
      factory_policy_sha256: sha256FileOrNull(path.join(root, "factory_policy.json")),
      roles_registry_sha256: sha256FileOrNull(path.join(root, "roles", "registry.json")),
      skills_registry_sha256: sha256FileOrNull(path.join(root, "skills", "registry.json")),
    },
    routing: {
      executor: routing?.executor ?? null,
      model: routing?.model ?? null,
      model_effective: routing?.model_effective ?? null,
    },
    artifacts: {
      submit_json: `artifacts/${tid}/submit.json`,
      report_md: `artifacts/${tid}/report.md`,
      selftest_log: `artifacts/${tid}/selftest.log`,
      evidence_dir: `artifacts/${tid}/evidence/`,
      patch_diff: `artifacts/${tid}/patch.diff`,
      verdict_json: `artifacts/${tid}/verdict.json`,
    },
  }

  fs.mkdirSync(artDir, { recursive: true })
  fs.writeFileSync(path.join(artDir, "trace.json"), JSON.stringify(trace, null, 2) + "\n", "utf8")
  return { ok: true, file: `artifacts/${tid}/trace.json` }
}

