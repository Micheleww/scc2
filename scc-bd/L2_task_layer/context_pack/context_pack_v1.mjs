import fs from "node:fs"
import path from "node:path"
import crypto from "node:crypto"

import { sha256Hex, stableStringify } from "../../L1_code_layer/gateway/utils.mjs"

const RUNS_SUBDIR = path.join("artifacts", "scc_runs")

function ensureDir(p) {
  try {
    fs.mkdirSync(p, { recursive: true })
  } catch {
    // ignore
  }
}

function copyFileBestEffort(srcAbs, dstAbs) {
  try {
    if (!fs.existsSync(srcAbs)) return false
    ensureDir(path.dirname(dstAbs))
    fs.copyFileSync(srcAbs, dstAbs)
    return true
  } catch {
    return false
  }
}

function sha256File(absPath) {
  const p = String(absPath ?? "").trim()
  if (!p) return null
  try {
    const buf = fs.readFileSync(p)
    return `sha256:${crypto.createHash("sha256").update(buf).digest("hex")}`
  } catch {
    return null
  }
}

function writeJsonAtomicBestEffort(absPath, obj) {
  try {
    ensureDir(path.dirname(absPath))
    const tmp = `${absPath}.tmp.${process.pid}.${Math.random().toString(16).slice(2)}`
    fs.writeFileSync(tmp, JSON.stringify(obj, null, 2) + "\n", "utf8")
    fs.renameSync(tmp, absPath)
    return true
  } catch {
    return false
  }
}

function writeTaskBundleToRunDir({ repoRoot, runId, taskId, getBoardTask }) {
  const runDir = safeRunDir({ repoRoot, runId })
  if (!runDir) return { ok: false, error: "invalid_run_dir" }
  const tbDir = path.join(runDir, "task_bundle")
  ensureDir(tbDir)

  const tid = String(taskId ?? "").trim()
  const t = typeof getBoardTask === "function" ? getBoardTask(tid) : null

  const srcPins = path.join(repoRoot, "artifacts", tid, "pins", "pins.json")
  const srcPre = path.join(repoRoot, "artifacts", tid, "preflight.json")
  const srcReplay = path.join(repoRoot, "artifacts", tid, "replay_bundle.json")

  const dstPins = path.join(tbDir, "pins.json")
  const dstPre = path.join(tbDir, "preflight.json")
  const dstReplay = path.join(tbDir, "replay_bundle.json")
  const dstTask = path.join(tbDir, "task.json")
  const dstManifest = path.join(tbDir, "manifest.json")

  const copied = []
  if (copyFileBestEffort(srcPins, dstPins)) copied.push({ kind: "pins", src: `artifacts/${tid}/pins/pins.json`, dst: `artifacts/scc_runs/${runId}/task_bundle/pins.json` })
  if (copyFileBestEffort(srcPre, dstPre)) copied.push({ kind: "preflight", src: `artifacts/${tid}/preflight.json`, dst: `artifacts/scc_runs/${runId}/task_bundle/preflight.json` })
  if (copyFileBestEffort(srcReplay, dstReplay)) copied.push({ kind: "replay_bundle", src: `artifacts/${tid}/replay_bundle.json`, dst: `artifacts/scc_runs/${runId}/task_bundle/replay_bundle.json` })

  const taskObj = {
    schema_version: "scc.task_bundle.task.v1",
    task_id: tid,
    task: t
      ? {
          kind: t.kind ?? null,
          title: t.title ?? "",
          goal: t.goal ?? "",
          role: t.role ?? null,
          area: t.area ?? null,
          lane: t.lane ?? null,
          task_class: t.task_class_id ?? t.task_class_candidate ?? null,
          files: Array.isArray(t.files) ? t.files : [],
          allowedTests: Array.isArray(t.allowedTests) ? t.allowedTests : [],
        }
      : null,
  }
  writeJsonAtomicBestEffort(dstTask, taskObj)

  const manifest = {
    schema_version: "scc.task_bundle.manifest.v1",
    run_id: runId,
    task_id: tid,
    created_at: new Date().toISOString(),
    files: [
      { path: `artifacts/scc_runs/${runId}/task_bundle/pins.json`, sha256: sha256File(dstPins) },
      { path: `artifacts/scc_runs/${runId}/task_bundle/preflight.json`, sha256: sha256File(dstPre) },
      { path: `artifacts/scc_runs/${runId}/task_bundle/replay_bundle.json`, sha256: fs.existsSync(dstReplay) ? sha256File(dstReplay) : null },
      { path: `artifacts/scc_runs/${runId}/task_bundle/task.json`, sha256: sha256File(dstTask) },
    ],
    copied,
  }
  writeJsonAtomicBestEffort(dstManifest, manifest)
  return { ok: true, task_bundle_dir: `artifacts/scc_runs/${runId}/task_bundle` }
}

function safeRunDir({ repoRoot, runId }) {
  const root = path.resolve(String(repoRoot ?? ""))
  const rid = String(runId ?? "").trim()
  if (!root || !rid) return null
  const runsRoot = path.resolve(root, RUNS_SUBDIR)
  const d = path.resolve(runsRoot, rid)
  if (!(d === runsRoot || d.startsWith(runsRoot + path.sep))) return null
  return d
}

function packJsonPathForId({ repoRoot, id }) {
  const d = safeRunDir({ repoRoot, runId: id })
  return d ? path.join(d, "rendered_context_pack.json") : null
}

function packTxtPathForId({ repoRoot, id }) {
  const d = safeRunDir({ repoRoot, runId: id })
  return d ? path.join(d, "rendered_context_pack.txt") : null
}

function packMetaPathForId({ repoRoot, id }) {
  const d = safeRunDir({ repoRoot, runId: id })
  return d ? path.join(d, "meta.json") : null
}

function sha256FileHex(absPath) {
  const p = String(absPath ?? "").trim()
  if (!p) return null
  try {
    const buf = fs.readFileSync(p)
    return crypto.createHash("sha256").update(buf).digest("hex")
  } catch {
    return null
  }
}

function loadJsonFile(absPath) {
  try {
    const raw = fs.readFileSync(absPath, "utf8")
    return JSON.parse(raw.replace(/^\uFEFF/, ""))
  } catch {
    return null
  }
}

function loadTextFile(absPath, maxBytes = 300_000) {
  const p = String(absPath ?? "").trim()
  if (!p) return null
  try {
    const buf = fs.readFileSync(p)
    const slice = buf.length > maxBytes ? buf.subarray(0, maxBytes) : buf
    return slice.toString("utf8")
  } catch {
    return null
  }
}

function renderLegalPrefixV1({ repoRoot }) {
  const p = path.join(repoRoot, "docs", "prompt_os", "compiler", "legal_prefix_v1.txt")
  const text = loadTextFile(p, 200_000)
  if (!text) return { ok: false, error: "legal_prefix_missing_or_unreadable", path: p }
  return { ok: true, text }
}

function renderBindingRefsV1({ repoRoot, role, mode }) {
  const refsPath = path.join(repoRoot, "docs", "prompt_os", "compiler", "refs_index_v1.json")
  const refsIndex = loadJsonFile(refsPath)
  if (!refsIndex || typeof refsIndex !== "object") return { ok: false, error: "refs_index_missing_or_invalid", path: refsPath }
  if (refsIndex.schema_version !== "scc.refs_index.v1") return { ok: false, error: "refs_index_schema_mismatch", path: refsPath }

  const roleName = String(role ?? "").trim() || "*"
  const m = String(mode ?? "").trim() || "*"
  const refs = Array.isArray(refsIndex.refs) ? refsIndex.refs : []

  const picked = []
  for (const r of refs) {
    if (!r || typeof r !== "object") continue
    const scope = Array.isArray(r.scope) ? r.scope.map((x) => String(x)) : []
    const always = r.always_include === true
    const scoped = scope.includes("*") || scope.includes(roleName) || scope.includes(m)
    if (always || scoped) picked.push(r)
  }

  const errors = []
  for (const r of picked) {
    const rel = String(r.path ?? "").trim()
    if (!rel) {
      errors.push({ id: r.id ?? null, error: "missing_path" })
      continue
    }
    const abs = path.join(repoRoot, rel)
    const hex = sha256FileHex(abs)
    if (!hex) {
      errors.push({ id: r.id ?? null, path: rel, error: "ref_read_failed" })
      continue
    }
    const want = String(r.hash ?? "").trim()
    const got = `sha256:${hex}`
    if (!want || want !== got) errors.push({ id: r.id ?? null, path: rel, error: "ref_hash_mismatch", want, got })
    const ver = String(r.version ?? "").trim()
    if (!ver) errors.push({ id: r.id ?? null, path: rel, error: "missing_version" })
  }
  if (errors.length) return { ok: false, error: "refs_integrity_failed", errors: errors.slice(0, 50), path: refsPath }

  return { ok: true, refs_index: { ...refsIndex, refs: picked } }
}

function renderRoleCapsuleV1({ repoRoot, role }) {
  const r = String(role ?? "").trim().toLowerCase()
  if (!r) return { ok: false, error: "missing_role" }
  const p = path.join(repoRoot, "roles", `${r}.json`)
  const policy = loadJsonFile(p)
  if (!policy || typeof policy !== "object") return { ok: false, error: "role_policy_missing_or_invalid", path: p }
  if (policy.schema_version !== "scc.role_policy.v1") return { ok: false, error: "role_policy_schema_mismatch", path: p }
  if (String(policy.role ?? "").trim().toLowerCase() !== r) return { ok: false, error: "role_policy_role_mismatch", path: p }

  const capsule = {
    schema_version: "scc.role_capsule.v1",
    role: policy.role,
    context_mode: policy.context_mode ?? null,
    allowed_context_refs: policy.allowed_context_refs ?? [],
    capabilities: policy.capabilities ?? {},
    permissions: policy.permissions ?? {},
    required_outputs: policy.required_outputs ?? {},
    gates: policy.gates ?? {},
    events: policy.events ?? {},
  }
  return { ok: true, capsule }
}

function renderTaskBundleV1({ repoRoot, taskId, getBoardTask }) {
  const tid = String(taskId ?? "").trim()
  if (!tid) return { ok: false, error: "missing_task_id" }

  const t = typeof getBoardTask === "function" ? getBoardTask(tid) : null
  const artDir = path.join(repoRoot, "artifacts", tid)
  const pinsPath = path.join(artDir, "pins", "pins.json")
  const preflightPath = path.join(artDir, "preflight.json")
  const replayPath = path.join(artDir, "replay_bundle.json")

  const pins = fs.existsSync(pinsPath) ? loadJsonFile(pinsPath) : null
  const preflight = fs.existsSync(preflightPath) ? loadJsonFile(preflightPath) : null
  const replay = fs.existsSync(replayPath) ? loadJsonFile(replayPath) : null

  const allowPaths = Array.isArray(pins?.allowed_paths)
    ? pins.allowed_paths.map((x) => String(x))
    : Array.isArray(t?.pins?.allowed_paths)
      ? t.pins.allowed_paths.map((x) => String(x))
      : []
  const denyPaths = Array.isArray(t?.pins?.forbidden_paths) ? t.pins.forbidden_paths.map((x) => String(x)) : []

  const bundle = {
    schema_version: "scc.task_bundle.v1",
    task_id: tid,
    task: t
      ? {
          kind: t.kind ?? null,
          title: t.title ?? "",
          goal: t.goal ?? "",
          role: t.role ?? null,
          area: t.area ?? null,
          lane: t.lane ?? null,
          task_class: t.task_class_id ?? t.task_class_candidate ?? null,
          allowedTests: Array.isArray(t.allowedTests) ? t.allowedTests : [],
          allowedExecutors: Array.isArray(t.allowedExecutors) ? t.allowedExecutors : [],
          allowedModels: Array.isArray(t.allowedModels) ? t.allowedModels : [],
        }
      : null,
    pins: {
      pins_json_path: fs.existsSync(pinsPath) ? `artifacts/${tid}/pins/pins.json` : null,
      allowed_paths: allowPaths.slice(0, 512),
      forbidden_paths: denyPaths.slice(0, 512),
    },
    preflight: preflight ? { preflight_json_path: `artifacts/${tid}/preflight.json`, preflight } : null,
    replay_bundle: replay ? { replay_bundle_json_path: `artifacts/${tid}/replay_bundle.json` } : null,
  }

  const missing = []
  if (!pins) missing.push("missing_pins")
  if (!preflight) missing.push("missing_preflight")
  if (missing.length) return { ok: false, error: "task_bundle_incomplete", missing, bundle }
  return { ok: true, bundle }
}

function newRunId() {
  return `${new Date().toISOString().replace(/[-:.]/g, "").replace("Z", "Z")}-${crypto.randomUUID().slice(0, 8)}`
}

function renderSccContextPackV1({ repoRoot, taskId, role, mode, budgetTokens, getBoardTask }) {
  const run_id = newRunId()
  const runDir = safeRunDir({ repoRoot, runId: run_id })
  if (!runDir) return { ok: false, error: "invalid_run_id" }
  ensureDir(runDir)

  const slot0 = renderLegalPrefixV1({ repoRoot })
  if (!slot0.ok) return { ok: false, error: slot0.error, detail: slot0 }
  const slot1 = renderBindingRefsV1({ repoRoot, role, mode })
  if (!slot1.ok) return { ok: false, error: slot1.error, detail: slot1 }
  const slot2 = renderRoleCapsuleV1({ repoRoot, role })
  if (!slot2.ok) return { ok: false, error: slot2.error, detail: slot2 }
  const slot3 = renderTaskBundleV1({ repoRoot, taskId, getBoardTask })
  if (!slot3.ok) return { ok: false, error: slot3.error, detail: slot3 }

  const pack = {
    schema_version: "scc.context_pack.v1",
    context_pack_id: run_id,
    run_id,
    created_at: new Date().toISOString(),
    mode: String(mode ?? "execute"),
    budget_tokens: Number.isFinite(Number(budgetTokens)) ? Number(budgetTokens) : null,
    slots: [
      { slot: 0, kind: "LEGAL_PREFIX", text: slot0.text },
      { slot: 1, kind: "BINDING_REFS", refs_index: slot1.refs_index },
      { slot: 2, kind: "ROLE_CAPSULE", role_capsule: slot2.capsule },
      { slot: 3, kind: "TASK_BUNDLE", task_bundle: slot3.bundle },
      { slot: 4, kind: "STATE", state: null },
      { slot: 5, kind: "TOOLS", tools: null },
      { slot: 6, kind: "OPTIONAL_CONTEXT", optional_context: null },
    ],
  }

  const stable = stableStringify(pack)
  const hash = `sha256:${sha256Hex(stable)}`
  pack.hash = hash

  const txt = [
    `SCC Context Pack v1`,
    `context_pack_id: ${run_id}`,
    `run_id: ${run_id}`,
    `created_at: ${pack.created_at}`,
    `mode: ${pack.mode}`,
    `hash: ${hash}`,
    ``,
    `SLOT0 LEGAL_PREFIX`,
    String(slot0.text ?? "").trimEnd(),
    ``,
    `SLOT1 BINDING_REFS`,
    JSON.stringify(slot1.refs_index, null, 2),
    ``,
    `SLOT2 ROLE_CAPSULE`,
    JSON.stringify(slot2.capsule, null, 2),
    ``,
    `SLOT3 TASK_BUNDLE`,
    JSON.stringify(slot3.bundle, null, 2),
    ``,
    `SLOT4 STATE`,
    `null`,
    ``,
    `SLOT5 TOOLS`,
    `null`,
    ``,
    `SLOT6 OPTIONAL_CONTEXT (NON-BINDING)`,
    `null`,
    ``,
  ].join("\n")

  try {
    fs.writeFileSync(packJsonPathForId({ repoRoot, id: run_id }), JSON.stringify(pack, null, 2) + "\n", "utf8")
    fs.writeFileSync(packTxtPathForId({ repoRoot, id: run_id }), txt, "utf8")
    // Materialize a deterministic task bundle snapshot inside the run directory (replay input).
    writeTaskBundleToRunDir({ repoRoot, runId: run_id, taskId, getBoardTask })
    fs.writeFileSync(
      packMetaPathForId({ repoRoot, id: run_id }),
      JSON.stringify(
        {
          schema_version: "scc.run_meta.v1",
          run_id,
          task_id: String(taskId ?? ""),
          role: String(role ?? ""),
          mode: String(mode ?? "execute"),
          budget_tokens: pack.budget_tokens,
          rendered_paths: {
            pack_json: `artifacts/scc_runs/${run_id}/rendered_context_pack.json`,
            pack_txt: `artifacts/scc_runs/${run_id}/rendered_context_pack.txt`,
          },
          hash,
        },
        null,
        2,
      ) + "\n",
      "utf8",
    )
  } catch (e) {
    return { ok: false, error: "pack_write_failed", message: String(e?.message ?? e), run_id }
  }

  return {
    ok: true,
    run_id,
    context_pack_id: run_id,
    rendered_paths: {
      pack_json: `artifacts/scc_runs/${run_id}/rendered_context_pack.json`,
      pack_txt: `artifacts/scc_runs/${run_id}/rendered_context_pack.txt`,
    },
    hash,
  }
}

function validateSccContextPackV1({ repoRoot, pack }) {
  if (!pack || typeof pack !== "object") return { ok: false, fail_code: "INVALID_PACK", error: "pack_not_object" }
  if (pack.schema_version !== "scc.context_pack.v1") return { ok: false, fail_code: "INVALID_PACK", error: "schema_version_mismatch" }
  const slots = Array.isArray(pack.slots) ? pack.slots : []

  const bySlot = new Map()
  for (const s of slots) {
    const idx = Number(s?.slot)
    if (!Number.isFinite(idx)) continue
    bySlot.set(idx, s)
  }
  const must = [0, 1, 3]
  for (const i of must) {
    if (!bySlot.has(i)) return { ok: false, fail_code: "MISSING_REQUIRED_SLOT", error: `missing_slot_${i}` }
  }
  if (String(bySlot.get(0)?.kind ?? "") !== "LEGAL_PREFIX") return { ok: false, fail_code: "INVALID_SLOT", error: "slot0_kind" }
  if (String(bySlot.get(1)?.kind ?? "") !== "BINDING_REFS") return { ok: false, fail_code: "INVALID_SLOT", error: "slot1_kind" }
  if (String(bySlot.get(3)?.kind ?? "") !== "TASK_BUNDLE") return { ok: false, fail_code: "INVALID_SLOT", error: "slot3_kind" }

  const stable = stableStringify({ ...pack, hash: undefined })
  const want = String(pack.hash ?? "").trim()
  const got = `sha256:${sha256Hex(stable)}`
  if (!want || want !== got) return { ok: false, fail_code: "PACK_HASH_MISMATCH", want, got }

  const refsIndex = bySlot.get(1)?.refs_index
  const refs = Array.isArray(refsIndex?.refs) ? refsIndex.refs : []
  for (const r of refs) {
    const rel = String(r?.path ?? "").trim()
    if (!rel) return { ok: false, fail_code: "REFS_INVALID", error: "ref_missing_path" }
    const abs = path.join(String(repoRoot ?? ""), rel)
    const hex = sha256FileHex(abs)
    if (!hex) return { ok: false, fail_code: "REFS_INVALID", error: "ref_read_failed", path: rel }
    const got2 = `sha256:${hex}`
    const want2 = String(r?.hash ?? "").trim()
    if (!want2 || want2 !== got2) return { ok: false, fail_code: "REF_HASH_MISMATCH", path: rel, want: want2, got: got2 }
    const ver = String(r?.version ?? "").trim()
    if (!ver) return { ok: false, fail_code: "REF_MISSING_VERSION", path: rel }
  }

  return { ok: true }
}

export { packJsonPathForId, packTxtPathForId, loadJsonFile, renderSccContextPackV1, validateSccContextPackV1 }
