import process from "node:process"

const base = process.env.SCC_BASE_URL ?? "http://127.0.0.1:18788"

async function sleep(ms) {
  await new Promise((r) => setTimeout(r, ms))
}

async function getJson(path) {
  const r = await fetch(`${base}${path}`, { method: "GET" })
  if (!r.ok) throw new Error(`GET ${path} -> ${r.status}`)
  return await r.json()
}

async function postJson(path, body) {
  const r = await fetch(`${base}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body ?? {}),
  })
  const text = await r.text()
  let parsed = null
  try {
    parsed = text ? JSON.parse(text) : null
  } catch {}
  if (!r.ok) throw new Error(`POST ${path} -> ${r.status} ${text?.slice?.(0, 240) ?? ""}`)
  return parsed
}

async function waitJobDone(jobId, { timeoutMs = 180_000 } = {}) {
  const start = Date.now()
  while (Date.now() - start < timeoutMs) {
    const job = await getJson(`/executor/jobs/${jobId}`)
    if (job.status === "done") return job
    if (job.status === "failed") return job
    await sleep(500)
  }
  throw new Error(`timeout waiting job ${jobId}`)
}

function assert(cond, msg) {
  if (!cond) throw new Error(`ASSERT_FAIL: ${msg}`)
}

console.log(`[selfcheck:parent_flow_v1] base=${base}`)

// 0) Health
await getJson("/health")

// 1) Create a parent task that will be split by the designer (codex forced model).
const parentPayload = {
  kind: "parent",
  title: "Selfcheck: parent->split->apply (no dispatch)",
  goal: [
    "Produce a JSON array of 2 atomic tasks for SCC.",
    "Hard requirements for each child item:",
    "- include title, goal, role, files (>=1), allowedTests (>=1 real cmd; must NOT include task_selftest), pins.allowed_paths (>=1).",
    "- keep tasks safe and deterministic: goal should be a no-op (do not change repo files) and only generate artifacts + run `python -m compileall docs` (do NOT require pins.allow_paths='.' which violates role policies).",
    "- set runner=internal and lane=fastlane.",
    "",
    "Role policy reminder (fail-closed): do not set pins.allowed_paths to '.'; keep pins scope under docs/** only for these selfcheck tasks.",
    "",
    "Suggested child skeleton (copy shape, but unique titles):",
    JSON.stringify(
      [
        {
          title: "No-op task (artifacts only)",
          goal: "No-op: do not change any repo file; only produce SCC artifacts and run python -m compileall docs",
          role: "doc",
          files: ["docs/INDEX.md"],
          allowedExecutors: ["codex"],
          allowedModels: ["gpt-5.3-codex"],
          allowedTests: ["python -m compileall docs"],
          runner: "internal",
          lane: "fastlane",
          pins: { allowed_paths: ["docs/INDEX.md", "docs/NAVIGATION.md", "docs/AI_CONTEXT.md", "docs/EXECUTOR.md"], forbidden_paths: [".git", "node_modules", "artifacts", "secrets"], max_files: 4, max_loc: 200 },
        },
      ],
      null,
      2,
    ),
    "",
    "Output MUST be JSON only (no prose outside JSON).",
  ].join("\n"),
  status: "ready",
  role: "designer",
  lane: "fastlane",
  runner: "internal",
  allowedExecutors: ["codex"],
  allowedModels: ["gpt-5.3-codex"],
  files: ["oc-scc-local/src/gateway.mjs", "docs/INDEX.md"],
}

const parent = await postJson("/board/tasks", parentPayload)
assert(parent?.id, "parent.id missing")
const parentId = parent.id
console.log(`[selfcheck:parent_flow_v1] parentId=${parentId}`)

// 2) Start split, wait job done.
const splitStart = await postJson(`/board/tasks/${parentId}/split`, {})
assert(splitStart?.job?.id, "splitStart.job.id missing")
const splitJobId = splitStart.job.id
console.log(`[selfcheck:parent_flow_v1] splitJobId=${splitJobId}`)

const job = await waitJobDone(splitJobId, { timeoutMs: 240_000 })
assert(job.status === "done", `split job status=${job.status}`)

// 3) Apply split, ensure atomic children created and schema-enforced fields exist.
const applied = await postJson(`/board/tasks/${parentId}/split/apply`, { jobId: splitJobId })
assert(applied?.ok === true, "split/apply ok!=true")
assert(Array.isArray(applied?.created), "split/apply created not array")
assert(applied.created.length >= 1, "split/apply created empty")

for (const t of applied.created) {
  assert(t.kind === "atomic", "child.kind != atomic")
  assert(String(t.title ?? "").trim().length > 0, "child.title empty")
  assert(String(t.goal ?? "").trim().length > 0, "child.goal empty")
  assert(Array.isArray(t.files) && t.files.length > 0, "child.files empty")
  assert(Array.isArray(t.allowedTests) && t.allowedTests.some((x) => !String(x).toLowerCase().includes("task_selftest")), "child.allowedTests missing real cmd")
  assert(t.pins && Array.isArray(t.pins.allowed_paths) && t.pins.allowed_paths.length > 0, "child.pins.allowed_paths empty")
}

console.log(`[selfcheck:parent_flow_v1] created=${applied.created.length}`)
console.log("[selfcheck:parent_flow_v1] OK")
