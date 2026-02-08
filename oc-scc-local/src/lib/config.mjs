import path from "node:path"
import os from "node:os"
import { fileURLToPath } from "node:url"

function defaultRepoRoot() {
  // Cross-platform default: repo root is parent of oc-scc-local/
  // NOTE: On Windows, URL.pathname yields "/C:/..." which breaks path.resolve into "C:\\C:\\...".
  // fileURLToPath handles platform specifics correctly.
  const here = path.dirname(fileURLToPath(import.meta.url))
  // config.mjs lives under oc-scc-local/src/lib/ so go up 3 levels to repo root.
  return path.resolve(here, "..", "..", "..")
}

function envBool(name, def = false) {
  const v = String(process.env[name] ?? "").trim().toLowerCase()
  if (!v) return def
  if (["1", "true", "yes", "y", "on"].includes(v)) return true
  if (["0", "false", "no", "n", "off"].includes(v)) return false
  return def
}

function getConfig() {
  const repoRoot = process.env.SCC_REPO_ROOT ? path.resolve(process.env.SCC_REPO_ROOT) : defaultRepoRoot()

  const occliDefault =
    process.platform === "win32"
      ? path.join(repoRoot, "OpenCode", "opencode-cli.exe")
      : path.join(repoRoot, "OpenCode", "opencode-cli")

  const execRoot = process.env.EXEC_ROOT ? path.resolve(process.env.EXEC_ROOT) : path.join(repoRoot, "opencode-dev")
  const execLogDir = process.env.EXEC_LOG_DIR ? path.resolve(process.env.EXEC_LOG_DIR) : path.join(repoRoot, "artifacts", "executor_logs")
  const docsRoot = process.env.DOCS_ROOT ? path.resolve(process.env.DOCS_ROOT) : path.join(repoRoot, "docs")
  const boardDir = process.env.BOARD_DIR ? path.resolve(process.env.BOARD_DIR) : path.join(repoRoot, "artifacts", "taskboard")

  return {
    repoRoot,
    docsRoot,
    boardDir,
    execRoot,
    execLogDir,
    occliBin: (process.env.OPENCODE_BIN ?? occliDefault).trim(),
    codexBin: (process.env.CODEX_BIN ?? process.env.CODEXCLI_BIN ?? "codex").trim(),
    // When true, reject non-transactional/best-effort writes in critical paths (gradually enforced).
    strictWrites: envBool("SCC_STRICT_WRITES", false),
    // OS hints
    isWindows: process.platform === "win32",
    homedir: os.homedir(),
  }
}

export { getConfig }
