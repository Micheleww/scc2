function uniq(arr) {
  const out = []
  const seen = new Set()
  for (const x of Array.isArray(arr) ? arr : []) {
    const s = String(x ?? "").trim()
    if (!s) continue
    if (seen.has(s)) continue
    seen.add(s)
    out.push(s)
  }
  return out
}

export function computeVerdictV1({ taskId, submit, job, ciGate, policyGate, hygiene }) {
  const tid = String(taskId ?? submit?.task_id ?? job?.boardTaskId ?? "").trim()
  const s = submit && typeof submit === "object" ? submit : null
  const j = job && typeof job === "object" ? job : {}
  const ci = ciGate && typeof ciGate === "object" ? ciGate : j.ci_gate
  const pg = policyGate && typeof policyGate === "object" ? policyGate : j.policy_gate
  const hy = hygiene && typeof hygiene === "object" ? hygiene : null

  const reasons = []
  const actions = []

  const submitStatus = s?.status ? String(s.status) : null
  const exitCode = Number.isFinite(Number(s?.exit_code)) ? Number(s.exit_code) : null
  const testsPassed = typeof s?.tests?.passed === "boolean" ? Boolean(s.tests.passed) : null

  const jobStatus = j?.status ? String(j.status) : null
  const jobError = j?.error ? String(j.error) : null
  const jobReason = j?.reason ? String(j.reason) : null

  if (!tid) {
    return {
      schema_version: "scc.verdict.v1",
      task_id: "unknown",
      verdict: "ESCALATE",
      reasons: ["missing_task_id"],
      actions: [{ type: "needs_input", notes: "Missing task_id; cannot judge." }],
    }
  }

  if (submitStatus === "NEED_INPUT") {
    reasons.push("submit:NEED_INPUT")
    actions.push({ type: "needs_input", notes: "Executor reported NEED_INPUT; cannot proceed automatically." })
    return { schema_version: "scc.verdict.v1", task_id: tid, verdict: "ESCALATE", reasons: uniq(reasons), actions }
  }

  if (ci && ci.required && !ci.ran) {
    reasons.push("ci_gate:required_but_not_ran")
    actions.push({ type: "retry", notes: "CI gate required but not executed." })
  } else if (ci && ci.ran && ci.ok === false) {
    reasons.push("ci_gate:failed")
    actions.push({ type: "create_task:ci_fixup_v1", notes: "CI gate failed; trigger CI fixup." })
  }

  if (pg && pg.required && pg.ran && pg.ok === false) {
    reasons.push("policy_gate:failed")
    actions.push({ type: "create_task:policy_fixup_v1", notes: "Policy gate failed; fix schema/SSOT/docs/contracts." })
  }

  if (hy && hy.ok === false) {
    reasons.push(`hygiene:${String(hy.reason ?? "failed")}`)
    actions.push({ type: "retry", notes: "Hygiene checks failed; fix artifacts/scope/selftest." })
  }

  if (jobError) reasons.push(`job_error:${jobError}`)
  if (jobReason) reasons.push(`job_reason:${jobReason}`)

  // DONE criteria: submit says DONE + exit_code==0 + tests passed (if present) + CI/policy gates (if required) passed.
  const gatesOk = !reasons.some((r) => r.includes(":failed") || r.includes("required_but_not_ran"))
  const submitOk =
    submitStatus === "DONE" && (exitCode === null || exitCode === 0) && (testsPassed === null || testsPassed === true)

  if (jobStatus === "done" && submitOk && gatesOk) {
    return { schema_version: "scc.verdict.v1", task_id: tid, verdict: "DONE", reasons: uniq(reasons), actions }
  }

  // Escalate on clear policy/scope violations to avoid infinite retries.
  if (jobError === "patch_scope_violation" || jobReason === "patch_scope_violation") {
    reasons.push("policy:patch_scope_violation")
    actions.push({ type: "escalate", notes: "Patch scope violation; requires contract/pins scope change." })
    return { schema_version: "scc.verdict.v1", task_id: tid, verdict: "ESCALATE", reasons: uniq(reasons), actions }
  }

  // Default: retry.
  if (!actions.length) actions.push({ type: "retry", notes: "Not DONE; retry with tighter scope or fixups." })
  return { schema_version: "scc.verdict.v1", task_id: tid, verdict: "RETRY", reasons: uniq(reasons), actions }
}

