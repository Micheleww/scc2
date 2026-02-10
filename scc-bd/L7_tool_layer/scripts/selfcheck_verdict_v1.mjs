import process from "node:process"
import { computeVerdictV1 } from "../../L8_evidence_layer/verdict/verifier_judge_v1.mjs"

function fail(msg) {
  console.error(`[selfcheck:verdict_v1] FAIL: ${msg}`)
  process.exit(1)
}

console.log("[selfcheck:verdict_v1] start")

{
  const v = computeVerdictV1({
    taskId: "t1",
    submit: { task_id: "t1", status: "DONE", exit_code: 0, tests: { passed: true } },
    job: { status: "done", error: null, reason: null },
    ciGate: { required: true, ran: true, ok: true },
    policyGate: { required: false, ran: false, ok: null },
    hygiene: { ok: true },
  })
  if (v.verdict !== "DONE") fail(`expected DONE, got ${v.verdict}`)
}

{
  const v = computeVerdictV1({
    taskId: "t2",
    submit: { task_id: "t2", status: "DONE", exit_code: 0, tests: { passed: true } },
    job: { status: "done", error: null, reason: null },
    ciGate: { required: true, ran: true, ok: false },
  })
  if (v.verdict !== "RETRY") fail(`expected RETRY (ci failed), got ${v.verdict}`)
}

{
  const v = computeVerdictV1({
    taskId: "t3",
    submit: { task_id: "t3", status: "NEED_INPUT", exit_code: 0, tests: { passed: false } },
    job: { status: "failed", error: "needs_input", reason: "needs_input" },
  })
  if (v.verdict !== "ESCALATE") fail(`expected ESCALATE (NEED_INPUT), got ${v.verdict}`)
}

{
  const v = computeVerdictV1({
    taskId: "t4",
    submit: { task_id: "t4", status: "FAILED", exit_code: 1, tests: { passed: false } },
    job: { status: "failed", error: "patch_scope_violation", reason: "patch_scope_violation" },
  })
  if (v.verdict !== "ESCALATE") fail(`expected ESCALATE (scope), got ${v.verdict}`)
}

console.log("[selfcheck:verdict_v1] OK")

