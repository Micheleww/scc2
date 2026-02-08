import fs from "node:fs"
import path from "node:path"

function normPosixRel(p) {
  const s = String(p ?? "").trim().replaceAll("\\", "/").replace(/^\.\/+/, "")
  if (!s) return null
  if (s.includes("..")) return null
  if (s.startsWith("/")) return null
  if (/^[a-zA-Z]:\//.test(s)) return null
  return s
}

function fileExists(root, rel) {
  try {
    const abs = path.join(root, rel)
    return fs.existsSync(abs) && fs.statSync(abs).isFile()
  } catch {
    return false
  }
}

function isAllowedByPrefixes(rel, allowPaths) {
  const list = Array.isArray(allowPaths) ? allowPaths.map(normPosixRel).filter(Boolean) : []
  if (!list.length) return false
  if (list.includes("**")) return true
  const s = String(rel ?? "").replaceAll("\\", "/")
  for (const a of list) {
    const p = String(a).replaceAll("\\", "/").replace(/\/+$/, "")
    if (!p) continue
    if (s === p) return true
    if (s.startsWith(p + "/")) return true
  }
  return false
}

function dirExists(root, rel) {
  try {
    const abs = path.join(root, rel)
    return fs.existsSync(abs) && fs.statSync(abs).isDirectory()
  } catch {
    return false
  }
}

function globToRegex(glob) {
  const g0 = String(glob ?? "").trim().replaceAll("\\", "/")
  if (!g0) return null
  if (g0 === "**") return /^.*$/
  let g = g0
  let prefix = ""
  if (g.startsWith("**/")) {
    prefix = "(?:.*/)?"
    g = g.slice(3)
  }
  let out = ""
  for (let i = 0; i < g.length; i += 1) {
    const c = g[i]
    const next = g[i + 1]
    if (c === "*" && next === "*") {
      out += ".*"
      i += 1
      continue
    }
    if (c === "*") {
      out += "[^/]*"
      continue
    }
    if (c === "?") {
      out += "[^/]"
      continue
    }
    if (/[-/\\^$+?.()|[\]{}]/.test(c)) out += `\\${c}`
    else out += c
  }
  return new RegExp(`^${prefix}${out}$`)
}

function shellSplit(cmd) {
  const s = String(cmd ?? "").trim()
  const out = []
  let cur = ""
  let q = null
  for (let i = 0; i < s.length; i += 1) {
    const c = s[i]
    if (q) {
      if (c === q) {
        q = null
        continue
      }
      if (c === "\\" && i + 1 < s.length) {
        cur += s[i + 1]
        i += 1
        continue
      }
      cur += c
      continue
    }
    if (c === "'" || c === '"') {
      q = c
      continue
    }
    if (/\s/.test(c)) {
      if (cur) out.push(cur)
      cur = ""
      continue
    }
    cur += c
  }
  if (cur) out.push(cur)
  return out
}

function validateNpmCommand({ repoRoot, tokens }) {
  const prefixIdx = tokens.findIndex((t) => t === "--prefix" || t === "-C")
  const prefix = prefixIdx >= 0 ? tokens[prefixIdx + 1] : null
  const prefixRel = prefix ? normPosixRel(prefix) : null
  const pkgRoot = prefixRel ? prefixRel : "."
  if (prefixRel && !dirExists(repoRoot, prefixRel)) return { ok: false, reason: `missing_dir:${prefixRel}` }
  const pkgJson = path.join(repoRoot, pkgRoot, "package.json")
  if (!fs.existsSync(pkgJson)) return { ok: false, reason: `missing_file:${normPosixRel(path.posix.join(pkgRoot, "package.json"))}` }

  const runIdx = tokens.findIndex((t) => t === "run")
  const script = runIdx >= 0 ? tokens[runIdx + 1] : null
  if (!script) return { ok: true }
  try {
    const pkg = JSON.parse(fs.readFileSync(pkgJson, "utf8"))
    const scripts = pkg?.scripts && typeof pkg.scripts === "object" ? pkg.scripts : {}
    if (!scripts[script]) return { ok: false, reason: `missing_npm_script:${pkgRoot}:${script}` }
  } catch {
    return { ok: false, reason: `invalid_json:${normPosixRel(path.posix.join(pkgRoot, "package.json"))}` }
  }
  return { ok: true }
}

function validatePythonOrNode({ repoRoot, tokens }) {
  if (!Array.isArray(tokens) || tokens.length < 2) return { ok: true }
  // Common pattern: python -m <module> ... (no script path)
  const second = String(tokens[1] ?? "").trim()
  if (!second || second.startsWith("-")) return { ok: true }
  const p = normPosixRel(second)
  if (!p) return { ok: true }
  // Only validate if it looks like a path (avoid treating bare module names as file paths).
  const looksLikePath = p.includes("/") || p.endsWith(".py") || p.endsWith(".js") || p.endsWith(".mjs") || p.endsWith(".cjs") || p.endsWith(".json")
  if (!looksLikePath) return { ok: true }
  if (!fileExists(repoRoot, p)) return { ok: false, reason: `missing_file:${p}` }
  return { ok: true }
}

function validatePytest({ repoRoot, tokens }) {
  // If pytest includes explicit paths, ensure they exist. Otherwise, best-effort allow.
  const paths = tokens.filter((t) => !t.startsWith("-")).slice(1)
  for (const raw of paths) {
    const rel = normPosixRel(raw)
    if (!rel) continue
    const abs = path.join(repoRoot, rel)
    if (!fs.existsSync(abs)) return { ok: false, reason: `missing_path:${rel}` }
  }
  const hasConfig =
    fs.existsSync(path.join(repoRoot, "pytest.ini")) ||
    fs.existsSync(path.join(repoRoot, "pyproject.toml")) ||
    fs.existsSync(path.join(repoRoot, "setup.cfg"))
  if (!hasConfig) {
    // Still allow if there is a tests/ folder.
    if (!fs.existsSync(path.join(repoRoot, "tests"))) return { ok: false, reason: "pytest_config_missing" }
  }
  return { ok: true }
}

function validateGoTest({ repoRoot }) {
  if (!fs.existsSync(path.join(repoRoot, "go.mod"))) return { ok: false, reason: "missing_file:go.mod" }
  return { ok: true }
}

function validateAllowedTestCommand({ repoRoot, cmd }) {
  const tokens = shellSplit(cmd)
  const head = String(tokens[0] ?? "").toLowerCase()
  if (!head) return { ok: false, reason: "empty_command" }
  if (head === "npm" || head === "pnpm" || head === "yarn" || head === "bun") return validateNpmCommand({ repoRoot, tokens })
  if (head === "python" || head === "node") return validatePythonOrNode({ repoRoot, tokens })
  if (head === "pytest") return validatePytest({ repoRoot, tokens })
  if (head === "go" && String(tokens[1] ?? "").toLowerCase() === "test") return validateGoTest({ repoRoot })
  // Unknown commands are allowed unless they reference an obvious missing path.
  for (const t of tokens.slice(1)) {
    const rel = normPosixRel(t)
    if (!rel) continue
    if (rel.includes("/") || rel.endsWith(".py") || rel.endsWith(".js") || rel.endsWith(".mjs") || rel.endsWith(".json")) {
      const abs = path.join(repoRoot, rel)
      if (!fs.existsSync(abs)) return { ok: false, reason: `missing_path:${rel}` }
    }
  }
  return { ok: true }
}

export function runPreflightV1({ repoRoot, taskId, childTask, pinsSpec, rolePolicy } = {}) {
  const root = path.resolve(repoRoot || process.cwd())
  const id = String(taskId ?? "").trim()
  if (!id) return { ok: false, error: "missing_task_id" }

  const child = childTask && typeof childTask === "object" ? childTask : null
  if (!child) return { ok: false, error: "missing_child_task" }
  const pins = pinsSpec && typeof pinsSpec === "object" ? pinsSpec : null
  if (!pins) return { ok: false, error: "missing_pins" }

  const requiredFiles = Array.isArray(child.files) ? child.files.map(normPosixRel).filter(Boolean) : []
  const allowedPaths = Array.isArray(pins.allowed_paths) ? pins.allowed_paths.map(normPosixRel).filter(Boolean) : []

  const missingFiles = []
  for (const f of requiredFiles) {
    if (!fileExists(root, f)) missingFiles.push(f)
    else if (!isAllowedByPrefixes(f, allowedPaths)) missingFiles.push(f)
  }

  const allowedTests = Array.isArray(child.allowedTests) ? child.allowedTests.map((x) => String(x ?? "").trim()).filter(Boolean) : []
  const missingTests = []
  for (const cmd of allowedTests) {
    const v = validateAllowedTestCommand({ repoRoot: root, cmd })
    if (!v.ok) missingTests.push(`${cmd} :: ${v.reason}`)
  }

  const missingSymbols = []
  const requiredSymbols = Array.isArray(child.required_symbols) ? child.required_symbols : []
  if (requiredSymbols.length) {
    const have = new Set(Array.isArray(pins.symbols) ? pins.symbols.map((x) => String(x ?? "")).filter(Boolean) : [])
    for (const s of requiredSymbols) {
      const sym = String(s ?? "").trim()
      if (!sym) continue
      if (!have.has(sym)) missingSymbols.push(sym)
    }
  }

  const missingWriteScope = []
  const policy = rolePolicy && typeof rolePolicy === "object" ? rolePolicy : null
  const allowList = Array.isArray(policy?.permissions?.write?.allow_paths) ? policy.permissions.write.allow_paths : []
  const denyList = Array.isArray(policy?.permissions?.write?.deny_paths) ? policy.permissions.write.deny_paths : []
  const allowAll = allowList.map(String).includes("**")
  const allowRes = allowList.map(globToRegex).filter(Boolean)
  const denyRes = denyList.map(globToRegex).filter(Boolean)
  for (const f of requiredFiles) {
    const rel = String(f)
    if (denyRes.length && denyRes.some((re) => re.test(rel))) missingWriteScope.push(rel)
    else if (!allowAll && allowRes.length && !allowRes.some((re) => re.test(rel))) missingWriteScope.push(rel)
  }

  const pass =
    missingFiles.length === 0 && missingSymbols.length === 0 && missingTests.length === 0 && missingWriteScope.length === 0

  const preflight = {
    schema_version: "scc.preflight.v1",
    task_id: id,
    pass,
    missing: {
      files: missingFiles.slice(0, 50),
      symbols: missingSymbols.slice(0, 50),
      tests: missingTests.slice(0, 30),
      write_scope: missingWriteScope.slice(0, 50),
    },
    notes: pass ? "preflight PASS" : "preflight FAIL (fail-closed); fix missing items before dispatch",
  }

  return { ok: true, preflight }
}

export function writePreflightV1Output({ repoRoot, taskId, outPath, preflight } = {}) {
  const root = path.resolve(repoRoot || process.cwd())
  const id = String(taskId ?? "").trim()
  if (!id) return { ok: false, error: "missing_task_id" }
  const out = outPath
    ? path.resolve(root, outPath)
    : path.join(root, "artifacts", id, "preflight.json")
  fs.mkdirSync(path.dirname(out), { recursive: true })
  fs.writeFileSync(out, JSON.stringify(preflight ?? {}, null, 2) + "\n", "utf8")
  return { ok: true, path: out }
}
