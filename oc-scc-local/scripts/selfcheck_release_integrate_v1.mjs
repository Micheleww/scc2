import fs from "node:fs"
import path from "node:path"
import process from "node:process"
import { execFileSync } from "node:child_process"

function sh(cmd, args, { cwd, timeoutMs }) {
  return execFileSync(cmd, args, { cwd, stdio: "inherit", windowsHide: true, timeout: timeoutMs })
}

const repoRoot = path.resolve(process.env.SCC_REPO_ROOT ?? path.join(process.cwd(), ".."))
const taskId = "factory_e2e_selfcheck_v1"

console.log(`[selfcheck:release_integrate_v1] repoRoot=${repoRoot}`)
console.log(`[selfcheck:release_integrate_v1] sourceTaskId=${taskId}`)

// Ensure source artifacts exist and strict gates can pass.
sh(process.platform === "win32" ? "cmd.exe" : "sh", process.platform === "win32" ? ["/c", "npm --prefix oc-scc-local run -s selfcheck:factory-e2e-v1"] : ["-lc", "npm --prefix oc-scc-local run -s selfcheck:factory-e2e-v1"], {
  cwd: repoRoot,
  timeoutMs: 420000,
})

const outDir = "releases_selfcheck"
const relCmd = ["python", "tools/scc/ops/release_integrate.py", "--source-task-id", taskId, "--out-dir", outDir, "--labels", "scc,release"]
sh(relCmd[0], relCmd.slice(1), { cwd: repoRoot, timeoutMs: 240000 })

// Discover latest release record under outDir and validate it.
const base = path.join(repoRoot, outDir)
const dirs = fs
  .readdirSync(base, { withFileTypes: true })
  .filter((d) => d.isDirectory() && d.name.startsWith("rel-"))
  .map((d) => d.name)
  .sort()
const last = dirs[dirs.length - 1]
if (!last) {
  console.error(`[selfcheck:release_integrate_v1] FAIL: no releases under ${outDir}/`)
  process.exit(2)
}
const releaseJson = path.posix.join(outDir, last, "release.json")
sh("python", ["tools/scc/selftest/validate_release_record.py", "--path", releaseJson], { cwd: repoRoot, timeoutMs: 120000 })

console.log("[selfcheck:release_integrate_v1] OK")

