import fs from "node:fs"
import path from "node:path"
import process from "node:process"
import { fileURLToPath } from "node:url"
import { computeDegradationActionV1, applyDegradationToWipLimitsV1, shouldAllowTaskUnderStopTheBleedingV1 } from "../../L1_code_layer/factory_policy/factory_policy_v1.mjs"

function fail(msg) {
  console.error(`[selfcheck:factory_policy_v1] FAIL: ${msg}`)
  process.exit(1)
}

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const repoRoot = process.env.SCC_REPO_ROOT ?? path.resolve(__dirname, "..", "..")
console.log(`[selfcheck:factory_policy_v1] repoRoot=${repoRoot}`)
const fpPath = path.join(repoRoot, "config", "factory_policy.json")
const fp = JSON.parse(fs.readFileSync(fpPath, "utf8").replace(/^\uFEFF/, ""))
if (fp.schema_version !== "scc.factory_policy.v1") fail("factory_policy.schema_version mismatch")

const qAction = computeDegradationActionV1({ factoryPolicy: fp, signals: { queue_overload: true, repo_unhealthy: false } })
if (!qAction) fail("expected degradation action for queue_overload=true")
if (String(qAction.prefer_lane ?? "") !== "fastlane") fail("expected prefer_lane=fastlane for queue_overload")
if (Number(qAction.reduce_WIP_EXEC_MAX_to) !== 2) fail("expected reduce_WIP_EXEC_MAX_to=2 for queue_overload")

const baseLimits = { total: 12, exec: 4, batch: 1 }
const degraded = applyDegradationToWipLimitsV1({ limits: baseLimits, action: qAction })
if (degraded.exec !== 2) fail(`expected degraded.exec=2, got ${degraded.exec}`)

const unhealthyAction = computeDegradationActionV1({ factoryPolicy: fp, signals: { queue_overload: false, repo_unhealthy: true } })
if (!unhealthyAction) fail("expected degradation action for repo_unhealthy=true")
if (String(unhealthyAction.mode ?? "") !== "stop_the_bleeding") fail("expected stop_the_bleeding mode for repo_unhealthy")

const allowCiFixup = shouldAllowTaskUnderStopTheBleedingV1({ action: unhealthyAction, task: { task_class_id: "ci_fixup_v1", area: "product" } })
if (!allowCiFixup.ok) fail("expected ci_fixup_v1 allowed under stop_the_bleeding")
const blockFeature = shouldAllowTaskUnderStopTheBleedingV1({ action: unhealthyAction, task: { task_class_id: "feature", area: "product" } })
if (blockFeature.ok) fail("expected non-allowlisted task blocked under stop_the_bleeding")
const allowControl = shouldAllowTaskUnderStopTheBleedingV1({ action: unhealthyAction, task: { task_class_id: "feature", area: "control_plane" } })
if (!allowControl.ok) fail("expected control_plane tasks allowed under stop_the_bleeding")

console.log("[selfcheck:factory_policy_v1] OK")

