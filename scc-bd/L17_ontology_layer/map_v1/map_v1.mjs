import fs from "node:fs"
import path from "node:path"
import crypto from "node:crypto"

const MAP_GENERATOR = { name: "scc.map_builder.v1", version: "1.0.0" }

const DEFAULT_ROOTS = ["oc-scc-local", "tools/scc", "scc-top", "contracts", "roles", "skills", "docs"]
const DEFAULT_EXCLUDES = [
  "**/.git/**",
  "**/node_modules/**",
  "artifacts/**",
  "**/.scc_secrets/**",
  "**/dist/**",
  "**/build/**",
  "**/coverage/**",
  "**/_tmp/**",
  "**/.opencode/**",
  "**/vendor/**",
  "**/.venv/**",
  "**/__pycache__/**",
]

const MODULE_MARKERS = new Set([
  "package.json",
  "pyproject.toml",
  "requirements.txt",
  "setup.py",
  "go.mod",
  "Cargo.toml",
  "pom.xml",
])

const CODE_EXTS = new Set([".mjs", ".js", ".cjs", ".ts", ".tsx", ".py", ".go", ".rs", ".java", ".cs", ".ps1", ".sh"])

function toPosixRel(repoRootAbs, absPath) {
  const rel = path.relative(repoRootAbs, absPath)
  return rel.replaceAll("\\", "/").replace(/^\.\/+/, "")
}

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true })
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

function stableStringify(value) {
  const seen = new WeakSet()
  const normalize = (v) => {
    if (v && typeof v === "object") {
      if (seen.has(v)) throw new Error("stableStringify: cyclic object")
      seen.add(v)
      if (Array.isArray(v)) return v.map(normalize)
      const keys = Object.keys(v).sort((a, b) => a.localeCompare(b))
      const out = {}
      for (const k of keys) out[k] = normalize(v[k])
      return out
    }
    return v
  }
  return JSON.stringify(normalize(value))
}

function sha256Hex(text) {
  return crypto.createHash("sha256").update(Buffer.from(String(text), "utf8")).digest("hex")
}

function safeReadText(file, maxBytes) {
  try {
    const st = fs.statSync(file)
    if (Number.isFinite(maxBytes) && maxBytes > 0 && st.size > maxBytes) return { ok: false, error: "too_large" }
    const raw = fs.readFileSync(file, "utf8")
    return { ok: true, text: raw.replace(/^\uFEFF/, "") }
  } catch (e) {
    return { ok: false, error: "read_failed", message: String(e?.message ?? e) }
  }
}

function isExcluded(relPosix, excludeRegexes) {
  if (!relPosix) return true
  const p = relPosix.replaceAll("\\", "/")
  return excludeRegexes.some((re) => re.test(p))
}

function listBacktickPathRefs(text) {
  const out = new Set()
  const t = String(text ?? "")
  const re = /`([^`]+)`/g
  let m
  while ((m = re.exec(t))) {
    const s = String(m[1] ?? "").trim().replaceAll("\\", "/").replace(/^\.\/+/, "")
    if (!s) continue
    if (s.includes("..") || s.startsWith("/") || s.includes("://")) continue
    if (s.length > 260) continue
    if (/^[a-zA-Z]:\//.test(s)) continue
    if (!/[./]/.test(s)) continue
    out.add(s)
  }
  return Array.from(out)
}

function buildDocRefIndex(repoRootAbs) {
  const docs = ["docs/INDEX.md", "docs/NAVIGATION.md", "docs/AI_CONTEXT.md", "docs/START_HERE.md"]
  const map = new Map()
  for (const docRel of docs) {
    const docAbs = path.join(repoRootAbs, docRel)
    if (!fs.existsSync(docAbs)) continue
    const raw = safeReadText(docAbs, 2_000_000)
    if (!raw.ok) continue
    const refs = listBacktickPathRefs(raw.text)
    for (const codePath of refs) {
      const arr = map.get(codePath) ?? []
      arr.push(docRel)
      map.set(codePath, arr)
    }
  }
  return map
}

function extractSymbolsFromText(fileRel, text) {
  const ext = path.extname(fileRel).toLowerCase()
  const lines = String(text ?? "").split(/\r?\n/g)
  const out = []
  const push = (symbol, kind, line) => {
    if (!symbol) return
    const ln = Math.max(1, Number(line))
    out.push({
      symbol,
      kind,
      path: fileRel,
      line: ln,
      line_window: [Math.max(1, ln - 3), ln + 3],
      confidence: 0.75,
      doc_refs: [],
    })
  }

  const jsFunc = /^\s*(?:export\s+)?function\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*\(/
  const jsClass = /^\s*(?:export\s+)?class\s+([A-Za-z_$][A-Za-z0-9_$]*)\b/
  const jsConst = /^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=/
  const pyDef = /^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(/
  const pyClass = /^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)\b/
  const goFunc = /^\s*func\s+(?:\([^)]+\)\s*)?([A-Za-z_][A-Za-z0-9_]*)\s*\(/
  const goType = /^\s*type\s+([A-Za-z_][A-Za-z0-9_]*)\s+/
  const rsFn = /^\s*(?:pub\s+)?fn\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(/
  const rsStruct = /^\s*(?:pub\s+)?struct\s+([A-Za-z_][A-Za-z0-9_]*)\b/

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i]
    if (ext === ".py") {
      let m = pyDef.exec(line)
      if (m) push(m[1], "function", i + 1)
      m = pyClass.exec(line)
      if (m) push(m[1], "class", i + 1)
      continue
    }
    if (ext === ".go") {
      let m = goFunc.exec(line)
      if (m) push(m[1], "function", i + 1)
      m = goType.exec(line)
      if (m) push(m[1], "type", i + 1)
      continue
    }
    if (ext === ".rs") {
      let m = rsFn.exec(line)
      if (m) push(m[1], "function", i + 1)
      m = rsStruct.exec(line)
      if (m) push(m[1], "struct", i + 1)
      continue
    }
    if ([".mjs", ".js", ".cjs", ".ts", ".tsx"].includes(ext)) {
      let m = jsFunc.exec(line)
      if (m) push(m[1], "function", i + 1)
      m = jsClass.exec(line)
      if (m) push(m[1], "class", i + 1)
      m = jsConst.exec(line)
      if (m) push(m[1], "const", i + 1)
    }
  }

  return out.slice(0, 200)
}

function extractEnvKeysFromText(fileRel, text) {
  const ext = path.extname(fileRel).toLowerCase()
  const lines = String(text ?? "").split(/\r?\n/g)
  const out = []
  const push = (key, line, reason) => {
    const k = String(key ?? "").trim()
    if (!k) return
    if (!/^[A-Z0-9_]{2,80}$/.test(k)) return
    out.push({ key: k, path: fileRel, line: Math.max(1, Number(line)), confidence: 0.7, reason: reason ?? "env_key" })
  }

  const jsDot = /process\.env\.([A-Z0-9_]{2,80})/g
  const jsBr = /process\.env\[\s*["']([A-Z0-9_]{2,80})["']\s*\]/g
  const pyGet = /os\.(?:getenv|environ\.get)\(\s*["']([A-Z0-9_]{2,80})["']/g
  const pyIdx = /os\.environ\[\s*["']([A-Z0-9_]{2,80})["']\s*\]/g
  const psEnv = /\$env:([A-Z0-9_]{2,80})/g

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i]
    if ([".mjs", ".js", ".cjs", ".ts", ".tsx"].includes(ext)) {
      let m
      while ((m = jsDot.exec(line))) push(m[1], i + 1, "process.env.DOT")
      while ((m = jsBr.exec(line))) push(m[1], i + 1, "process.env.BRACKET")
      continue
    }
    if (ext === ".py") {
      let m
      while ((m = pyGet.exec(line))) push(m[1], i + 1, "os.getenv")
      while ((m = pyIdx.exec(line))) push(m[1], i + 1, "os.environ[]")
      continue
    }
    if (ext === ".ps1") {
      let m
      while ((m = psEnv.exec(line))) push(m[1], i + 1, "$env:")
    }
  }
  return out.slice(0, 200)
}

function loadJson(fileAbs) {
  const raw = fs.readFileSync(fileAbs, "utf8").replace(/^\uFEFF/, "")
  return JSON.parse(raw)
}

function detectEntryPointsFromPackageJson(repoRootAbs, pkgAbs, docIndex) {
  const out = []
  let pkg = null
  try {
    pkg = loadJson(pkgAbs)
  } catch {
    return out
  }
  const rel = toPosixRel(repoRootAbs, pkgAbs)
  const scripts = pkg && typeof pkg === "object" ? pkg.scripts : null
  const bin = pkg && typeof pkg === "object" ? pkg.bin : null
  const add = (id, kind, command, reason) => {
    const docRefs = docIndex.get(rel) ?? []
    out.push({
      id,
      kind,
      path: rel,
      command: String(command ?? "").trim(),
      confidence: 0.85,
      reason: reason ?? "",
      doc_refs: Array.from(new Set(docRefs)),
    })
  }
  if (scripts && typeof scripts === "object") {
    for (const [k, v] of Object.entries(scripts)) {
      const key = String(k ?? "").trim()
      const cmd = String(v ?? "").trim()
      if (!key || !cmd) continue
      if (key.startsWith("selfcheck:")) continue
      const isCore =
        key === "start" ||
        key === "dev" ||
        key === "smoke" ||
        key === "build" ||
        key === "test" ||
        key.startsWith("map:") ||
        key.startsWith("pins:") ||
        key.startsWith("preflight:") ||
        key.startsWith("factory:") ||
        key.startsWith("ci:") ||
        key.startsWith("ssot:")
      if (!isCore) continue
      add(`pkg:${rel}:${key}`, "npm_script", `npm --prefix ${path.posix.dirname(rel)} run ${key}`, `package.json scripts.${key}`)
    }
  }
  if (bin && typeof bin === "string") {
    add(`pkg:${rel}:bin`, "node_bin", `node ${bin}`, "package.json bin")
  } else if (bin && typeof bin === "object") {
    for (const [k, v] of Object.entries(bin)) {
      const name = String(k ?? "").trim()
      const target = String(v ?? "").trim()
      if (!name || !target) continue
      add(`pkg:${rel}:bin:${name}`, "node_bin", `node ${target}`, "package.json bin")
    }
  }
  return out.filter((x) => x.command.length > 0)
}

function detectTestEntryPoints(repoRootAbs, markers) {
  const out = []
  const add = (id, kind, command, paths, confidence, reason) => {
    out.push({
      id,
      kind,
      command,
      paths: Array.isArray(paths) ? paths : [],
      confidence,
      reason,
    })
  }
  if (markers.packageJson.length) {
    // Make npm tests preflight-checkable by always adding an explicit --prefix to the package root.
    for (const pkgAbs of markers.packageJson.slice(0, 50)) {
      const rel = toPosixRel(repoRootAbs, pkgAbs)
      const dir = path.posix.dirname(rel)
      add(`npm:test:${dir}`, "node", `npm --prefix ${dir} test`, [rel], 0.7, "package.json present")
    }
  }
  if (markers.pyProject.length || markers.pytestIni.length) {
    add("pytest", "python", "pytest -q", [...markers.pyProject, ...markers.pytestIni].map((p) => toPosixRel(repoRootAbs, p)), 0.7, "pytest config present")
  }
  if (markers.goMod.length) {
    add("go:test", "go", "go test ./...", markers.goMod.map((p) => toPosixRel(repoRootAbs, p)), 0.7, "go.mod present")
  }
  if (markers.cargoToml.length) {
    add("cargo:test", "rust", "cargo test", markers.cargoToml.map((p) => toPosixRel(repoRootAbs, p)), 0.7, "Cargo.toml present")
  }
  return out
}

export function computeMapHash(mapObj) {
  const stable = {
    schema_version: mapObj.schema_version,
    generator: mapObj.generator,
    coverage: mapObj.coverage,
    modules: mapObj.modules,
    entry_points: mapObj.entry_points,
    key_symbols: mapObj.key_symbols,
    test_entry_points: mapObj.test_entry_points,
    configs: mapObj.configs,
    doc_refs: mapObj.doc_refs,
  }
  return `sha256:${sha256Hex(stableStringify(stable))}`
}

export function defaultMapRoots() {
  return DEFAULT_ROOTS.slice()
}

export function defaultMapExcludes() {
  return DEFAULT_EXCLUDES.slice()
}

export function loadMapV1({ repoRoot, mapPath } = {}) {
  const root = path.resolve(repoRoot || process.cwd())
  const p = mapPath ? path.resolve(root, mapPath) : path.join(root, "map", "map.json")
  const data = loadJson(p)
  return { repoRoot: root, path: p, data }
}

export function queryMapV1({ map, q, limit = 20 } = {}) {
  const query = String(q ?? "").trim()
  const tokens = query.length ? query.toLowerCase().split(/\s+/g).filter(Boolean) : []
  const results = []
  const push = (item) => {
    results.push(item)
  }
  const scoreText = (hay, base = 0.5) => {
    const h = String(hay ?? "").toLowerCase()
    if (!h) return 0
    let score = 0
    for (const t of tokens) {
      if (!t) continue
      if (h === t) score += 6
      else if (h.startsWith(t)) score += 4
      else if (h.includes(t)) score += 2
    }
    return score > 0 ? base + score : 0
  }
  if (!tokens.length) return { ok: false, error: "missing_query" }

  for (const m of Array.isArray(map?.modules) ? map.modules : []) {
    const s = Math.max(scoreText(m.id, 0.2), scoreText(m.root, 0.2))
    if (s > 0) push({ kind: "module", id: m.id, path: m.root, score: s, reason: "match module id/root", doc_refs: m.doc_refs ?? [] })
  }
  for (const e of Array.isArray(map?.entry_points) ? map.entry_points : []) {
    const s = Math.max(scoreText(e.id, 0.2), scoreText(e.command, 0.2), scoreText(e.path, 0.2))
    if (s > 0) push({ kind: "entry_point", id: e.id, path: e.path ?? null, score: s, reason: "match entry point", command: e.command ?? null, doc_refs: e.doc_refs ?? [] })
  }
  for (const ks of Array.isArray(map?.key_symbols) ? map.key_symbols : []) {
    const s = Math.max(scoreText(ks.symbol, 0.2), scoreText(ks.path, 0.2))
    if (s > 0) push({ kind: "key_symbol", id: `${ks.symbol}@${ks.path}:${ks.line}`, path: ks.path, score: s, reason: "match symbol/path", symbol: ks.symbol, line: ks.line, line_window: ks.line_window, doc_refs: ks.doc_refs ?? [] })
  }
  for (const t of Array.isArray(map?.test_entry_points) ? map.test_entry_points : []) {
    const s = Math.max(scoreText(t.id, 0.2), scoreText(t.command, 0.2))
    if (s > 0) push({ kind: "test_entry", id: t.id, path: (t.paths ?? [])[0] ?? null, score: s, reason: "match test id/command", command: t.command })
  }
  for (const c of Array.isArray(map?.configs) ? map.configs : []) {
    const s = Math.max(scoreText(c.key, 0.2), scoreText(c.path, 0.1))
    if (s > 0) push({ kind: "config", id: `${c.key}@${c.path}:${c.line}`, path: c.path, score: s, reason: "match config key", key: c.key, line: c.line })
  }

  results.sort((a, b) => Number(b.score ?? 0) - Number(a.score ?? 0))
  return { ok: true, query, results: results.slice(0, Math.max(1, Math.min(200, Number(limit)))) }
}

export function buildMapV1({
  repoRoot,
  roots = null,
  excludes = null,
  maxFiles = 20000,
  maxFileBytes = 900_000,
  incremental = true,
  previousMapPath = null,
} = {}) {
  const repoRootAbs = path.resolve(repoRoot || process.cwd())
  const rootList = (Array.isArray(roots) && roots.length ? roots : DEFAULT_ROOTS)
    .map((r) => String(r).trim())
    .filter(Boolean)
  const excludeList = (Array.isArray(excludes) && excludes.length ? excludes : DEFAULT_EXCLUDES)
    .map((x) => String(x).trim())
    .filter(Boolean)
  const excludeRegexes = excludeList.map(globToRegex).filter(Boolean)

  const docIndex = buildDocRefIndex(repoRootAbs)

  let prev = null
  if (incremental) {
    const p = previousMapPath ? path.resolve(repoRootAbs, previousMapPath) : path.join(repoRootAbs, "map", "map.json")
    if (fs.existsSync(p)) {
      try {
        prev = loadJson(p)
      } catch {
        prev = null
      }
    }
  }

  const prevFileIndex = prev && typeof prev === "object" ? prev.file_index : null
  const prevKeyByFile = new Map()
  const prevCfgByFile = new Map()
  if (prev && typeof prev === "object") {
    for (const ks of Array.isArray(prev.key_symbols) ? prev.key_symbols : []) {
      const file = String(ks?.path ?? "")
      if (!file) continue
      const arr = prevKeyByFile.get(file) ?? []
      arr.push(ks)
      prevKeyByFile.set(file, arr)
    }
    for (const c of Array.isArray(prev.configs) ? prev.configs : []) {
      const file = String(c?.path ?? "")
      if (!file) continue
      const arr = prevCfgByFile.get(file) ?? []
      arr.push(c)
      prevCfgByFile.set(file, arr)
    }
  }

  const markers = { packageJson: [], pyProject: [], pytestIni: [], goMod: [], cargoToml: [] }
  const moduleRoots = new Map()
  const entryPoints = []
  const fileIndex = {}
  const keySymbols = []
  const configs = []
  const docRefs = []
  const seenDocRef = new Set()

  const addDocRef = (codePath, docPath, reason) => {
    const c = String(codePath ?? "").trim().replaceAll("\\", "/")
    const d = String(docPath ?? "").trim().replaceAll("\\", "/")
    if (!c || !d) return
    const key = `${c}=>${d}`
    if (seenDocRef.has(key)) return
    seenDocRef.add(key)
    docRefs.push({ code_path: c, doc_path: d, reason: String(reason ?? "") })
  }

  const queue = []
  for (const relRoot of rootList) {
    const absRoot = path.resolve(repoRootAbs, relRoot)
    if (!fs.existsSync(absRoot)) continue
    queue.push({ abs: absRoot, relBase: toPosixRel(repoRootAbs, absRoot) })
  }

  const files = []
  const visitedDirs = new Set()
  while (queue.length) {
    const cur = queue.pop()
    if (!cur) continue
    const relDir = cur.relBase.replace(/\/+$/, "")
    if (visitedDirs.has(relDir)) continue
    visitedDirs.add(relDir)
    if (isExcluded(relDir + "/", excludeRegexes)) continue
    let ents = []
    try {
      ents = fs.readdirSync(cur.abs, { withFileTypes: true })
    } catch {
      continue
    }
    for (const ent of ents) {
      const abs = path.join(cur.abs, ent.name)
      const rel = toPosixRel(repoRootAbs, abs)
      if (isExcluded(ent.isDirectory() ? rel + "/" : rel, excludeRegexes)) continue
      if (ent.isDirectory()) {
        queue.push({ abs, relBase: rel })
        continue
      }
      if (!ent.isFile()) continue
      if (files.length >= maxFiles) break
      files.push({ abs, rel })
      const base = path.posix.basename(rel)
      if (MODULE_MARKERS.has(base)) {
        const dirRel = path.posix.dirname(rel)
        const kind =
          base === "package.json"
            ? "node"
            : base === "go.mod"
              ? "go"
              : base === "Cargo.toml"
                ? "rust"
                : base === "pyproject.toml" || base === "requirements.txt" || base === "setup.py"
                  ? "python"
                  : "generic"
        moduleRoots.set(dirRel, { root: dirRel, kind, signals: [`marker:${base}`], confidence: 0.8 })
        if (base === "package.json") markers.packageJson.push(abs)
        if (base === "pyproject.toml") markers.pyProject.push(abs)
        if (base === "pytest.ini") markers.pytestIni.push(abs)
        if (base === "go.mod") markers.goMod.push(abs)
        if (base === "Cargo.toml") markers.cargoToml.push(abs)
      }
      if (base === "pytest.ini") markers.pytestIni.push(abs)
      if (base === "package.json") {
        entryPoints.push(...detectEntryPointsFromPackageJson(repoRootAbs, abs, docIndex))
      }
    }
  }

  for (const relRoot of rootList) {
    const root = relRoot.replaceAll("\\", "/").replace(/\/+$/, "")
    if (!root) continue
    if (!moduleRoots.has(root)) {
      moduleRoots.set(root, { root, kind: "root", signals: ["configured_root"], confidence: 0.55 })
    }
  }

  const readmeCandidates = new Set()
  for (const mod of moduleRoots.values()) {
    readmeCandidates.add(path.join(repoRootAbs, mod.root, "README.md"))
    readmeCandidates.add(path.join(repoRootAbs, mod.root, "readme.md"))
  }
  for (const absReadme of readmeCandidates) {
    if (!fs.existsSync(absReadme)) continue
    const rel = toPosixRel(repoRootAbs, absReadme)
    const modRoot = toPosixRel(repoRootAbs, path.dirname(absReadme))
    addDocRef(modRoot + "/", rel, "module_readme")
  }

  for (const f of files) {
    const ext = path.extname(f.rel).toLowerCase()
    const st = (() => {
      try {
        return fs.statSync(f.abs)
      } catch {
        return null
      }
    })()
    if (!st) continue
    fileIndex[f.rel] = { mtimeMs: Number(st.mtimeMs), size: Number(st.size) }
    if (!CODE_EXTS.has(ext)) continue

    const prevMeta = prevFileIndex && typeof prevFileIndex === "object" ? prevFileIndex[f.rel] : null
    const unchanged =
      prevMeta &&
      Number(prevMeta?.mtimeMs ?? -1) === Number(st.mtimeMs) &&
      Number(prevMeta?.size ?? -1) === Number(st.size)
    if (incremental && unchanged) {
      const reusedKs = prevKeyByFile.get(f.rel) ?? []
      const reusedCfg = prevCfgByFile.get(f.rel) ?? []
      keySymbols.push(...reusedKs)
      configs.push(...reusedCfg)
      continue
    }

    const read = safeReadText(f.abs, maxFileBytes)
    if (!read.ok) continue
    const syms = extractSymbolsFromText(f.rel, read.text)
    const envs = extractEnvKeysFromText(f.rel, read.text)
    keySymbols.push(...syms)
    configs.push(...envs)
  }

  const moduleByRoot = new Map()
  for (const [root, meta] of moduleRoots.entries()) {
    const docRefsForRoot = Array.from(new Set([...(docIndex.get(root) ?? []), ...(docIndex.get(root + "/") ?? [])]))
    moduleByRoot.set(root, {
      id: `mod:${root}`,
      root,
      kind: meta.kind,
      confidence: meta.confidence,
      signals: meta.signals,
      doc_refs: docRefsForRoot,
    })
    for (const d of docRefsForRoot) addDocRef(root + "/", d, "docs_backtick_ref")
  }

  const entryPointsWithDocs = entryPoints.map((e) => {
    const fileRel = typeof e.path === "string" ? e.path : null
    const docRefsForFile = fileRel ? (docIndex.get(fileRel) ?? []) : []
    const docRefsForModule = fileRel ? (moduleByRoot.get(path.posix.dirname(fileRel))?.doc_refs ?? []) : []
    const merged = Array.from(new Set([...(e.doc_refs ?? []), ...docRefsForFile, ...docRefsForModule]))
    if (fileRel) for (const d of merged) addDocRef(fileRel, d, "docs_backtick_ref")
    return { ...e, doc_refs: merged }
  })

  const keySymbolsWithDocs = keySymbols.map((ks) => {
    const fileRel = String(ks?.path ?? "")
    const docRefsForFile = fileRel ? (docIndex.get(fileRel) ?? []) : []
    const docRefsForModule = fileRel ? (moduleByRoot.get(path.posix.dirname(fileRel))?.doc_refs ?? []) : []
    const merged = Array.from(new Set([...(ks.doc_refs ?? []), ...docRefsForFile, ...docRefsForModule]))
    if (fileRel) for (const d of merged) addDocRef(fileRel, d, "docs_backtick_ref")
    return { ...ks, doc_refs: merged }
  })

  const testEntryPoints = detectTestEntryPoints(repoRootAbs, markers)

  const modules = Array.from(moduleByRoot.values()).sort((a, b) => a.root.localeCompare(b.root))
  const entry_points = entryPointsWithDocs
    .filter((e) => e && typeof e === "object" && String(e.command ?? "").trim().length)
    .sort((a, b) => String(a.id ?? "").localeCompare(String(b.id ?? "")))
    .slice(0, 300)
  const key_symbols = keySymbolsWithDocs
    .filter((x) => x && typeof x === "object" && x.symbol && x.path && Number.isFinite(x.line))
    .sort((a, b) => {
      const ap = String(a.path).localeCompare(String(b.path))
      if (ap !== 0) return ap
      const al = Number(a.line) - Number(b.line)
      if (al !== 0) return al
      return String(a.symbol).localeCompare(String(b.symbol))
    })
    .slice(0, 6000)
  const configsSorted = configs
    .filter((x) => x && typeof x === "object" && x.key && x.path && Number.isFinite(x.line))
    .sort((a, b) => {
      const ak = String(a.key).localeCompare(String(b.key))
      if (ak !== 0) return ak
      const ap = String(a.path).localeCompare(String(b.path))
      if (ap !== 0) return ap
      return Number(a.line) - Number(b.line)
    })
    .slice(0, 8000)

  const map = {
    schema_version: "scc.map.v1",
    generated_at: new Date().toISOString(),
    generator: MAP_GENERATOR,
    coverage: { roots: rootList, excluded_globs: excludeList, notes: "Deterministic tool-based index (regex symbol scan + config scan)." },
    modules,
    entry_points,
    key_symbols,
    test_entry_points: testEntryPoints.sort((a, b) => String(a.id).localeCompare(String(b.id))),
    configs: configsSorted,
    doc_refs: docRefs.sort((a, b) => {
      const ac = String(a.code_path).localeCompare(String(b.code_path))
      if (ac !== 0) return ac
      const ad = String(a.doc_path).localeCompare(String(b.doc_path))
      if (ad !== 0) return ad
      return String(a.reason).localeCompare(String(b.reason))
    }),
    file_index: fileIndex,
  }

  const hash = computeMapHash(map)
  const contractsSchemas = Object.keys(fileIndex)
    .filter((p) => String(p).startsWith("contracts/") && String(p).endsWith(".schema.json"))
    .sort((a, b) => {
      const aa = String(a)
      const bb = String(b)
      return aa < bb ? -1 : aa > bb ? 1 : 0
    })
    .slice(0, 20000)
  const uniqSorted = (arr) => Array.from(new Set(arr.map((x) => String(x)))).sort((a, b) => (a < b ? -1 : a > b ? 1 : 0))
  const factsHash = `sha256:${sha256Hex(
    stableStringify({
      modules: uniqSorted((Array.isArray(map.modules) ? map.modules : []).map((m) => m.root)),
      entry_points: uniqSorted((Array.isArray(map.entry_points) ? map.entry_points : []).map((e) => e.id)),
      contracts: contractsSchemas,
    }),
  )}`

  const facts = {
    modules: uniqSorted((Array.isArray(map.modules) ? map.modules : []).map((m) => m.root)),
    entry_points: uniqSorted((Array.isArray(map.entry_points) ? map.entry_points : []).map((e) => e.id)),
    contracts: contractsSchemas,
  }

  const prevFacts = (() => {
    if (!prev || typeof prev !== "object") return null
    try {
      const prevFileIndex = prev.file_index && typeof prev.file_index === "object" ? prev.file_index : {}
      const prevContracts = Object.keys(prevFileIndex)
        .filter((p) => String(p).startsWith("contracts/") && String(p).endsWith(".schema.json"))
        .sort((a, b) => (String(a) < String(b) ? -1 : String(a) > String(b) ? 1 : 0))
        .slice(0, 20000)
      return {
        modules: uniqSorted((Array.isArray(prev.modules) ? prev.modules : []).map((m) => String(m?.root ?? "")).filter(Boolean)),
        entry_points: uniqSorted((Array.isArray(prev.entry_points) ? prev.entry_points : []).map((e) => String(e?.id ?? "")).filter(Boolean)),
        contracts: prevContracts,
      }
    } catch {
      return null
    }
  })()

  const diff = (() => {
    if (!prevFacts) return null
    const prevHash = computeMapHash(prev)
    const prevFactsHash = `sha256:${sha256Hex(stableStringify(prevFacts))}`
    const added = {
      modules: facts.modules.filter((x) => !prevFacts.modules.includes(x)),
      entry_points: facts.entry_points.filter((x) => !prevFacts.entry_points.includes(x)),
      contracts: facts.contracts.filter((x) => !prevFacts.contracts.includes(x)),
    }
    const removed = {
      modules: prevFacts.modules.filter((x) => !facts.modules.includes(x)),
      entry_points: prevFacts.entry_points.filter((x) => !facts.entry_points.includes(x)),
      contracts: prevFacts.contracts.filter((x) => !facts.contracts.includes(x)),
    }
    return {
      schema_version: "scc.map_diff.v1",
      generated_at: new Date().toISOString(),
      previous: { hash: prevHash, facts_hash: prevFactsHash },
      current: { hash, facts_hash: factsHash },
      added,
      removed,
      notes: "Map diff is fact-level (modules/entry_points/contracts) and is generated only when a previous map is available.",
    }
  })()
  const linkReport = (() => {
    const missingModules = modules.filter((m) => !(Array.isArray(m.doc_refs) && m.doc_refs.length)).map((m) => m.root)
    const missingEntries = entry_points.filter((e) => !(Array.isArray(e.doc_refs) && e.doc_refs.length)).map((e) => e.id)
    const missingSymbols = key_symbols
      .filter((s) => !(Array.isArray(s.doc_refs) && s.doc_refs.length))
      .slice(0, 2000)
      .map((s) => `${s.symbol}@${s.path}:${s.line}`)
    return {
      schema_version: "scc.link_report.v1",
      generated_at: new Date().toISOString(),
      map_hash: hash,
      counts: {
        modules_missing: missingModules.length,
        entry_points_missing: missingEntries.length,
        key_symbols_missing: missingSymbols.length,
      },
      missing_doc_refs: {
        modules: missingModules.slice(0, 200),
        entry_points: missingEntries.slice(0, 200),
        key_symbols: missingSymbols.slice(0, 200),
      },
      notes: "Missing doc_refs list is capped for safety; counts reflect full scan where applicable.",
    }
  })()

  const version = {
    schema_version: "scc.map_version.v1",
    generated_at: new Date().toISOString(),
    valid_until: new Date(Date.now() + 7 * 24 * 3600 * 1000).toISOString(),
    generator: MAP_GENERATOR,
    map_path: "map/map.json",
    link_report_path: "map/link_report.json",
    hash,
    facts_hash: factsHash,
    coverage: { roots: rootList, excluded_globs: excludeList },
    stats: {
      files_indexed: Object.keys(fileIndex).length,
      modules: modules.length,
      entry_points: entry_points.length,
      key_symbols: key_symbols.length,
      test_entry_points: map.test_entry_points.length,
      configs: configsSorted.length,
      doc_refs: map.doc_refs.length,
    },
  }

  return { ok: true, map, version, linkReport, diff }
}

export function writeMapV1Outputs({ repoRoot, outDir, buildResult }) {
  const repoRootAbs = path.resolve(repoRoot || process.cwd())
  const out = path.resolve(repoRootAbs, outDir || "map")
  ensureDir(out)
  const mapPath = path.join(out, "map.json")
  const versionPath = path.join(out, "version.json")
  const linkPath = path.join(out, "link_report.json")
  const linkMdPath = path.join(out, "link_report.md")
  const diffPath = path.join(out, "diff.json")
  const diffMdPath = path.join(out, "diff.md")

  const mapText = JSON.stringify(buildResult.map, null, 2) + "\n"
  const outRel = path.relative(repoRootAbs, out).replaceAll("\\", "/").replace(/^\.\/+/, "")
  const version = {
    ...buildResult.version,
    map_path: outRel ? `${outRel}/map.json` : "map.json",
    link_report_path: outRel ? `${outRel}/link_report.json` : "link_report.json",
  }
  const versionText = JSON.stringify(version, null, 2) + "\n"
  const linkText = JSON.stringify(buildResult.linkReport, null, 2) + "\n"
  const linkMd = [
    `# Map Link Report (v1)`,
    ``,
    `- generated_at: ${buildResult.linkReport.generated_at}`,
    `- map_hash: ${buildResult.linkReport.map_hash}`,
    ``,
    `## Missing doc_refs counts`,
    `- modules_missing: ${buildResult.linkReport.counts.modules_missing}`,
    `- entry_points_missing: ${buildResult.linkReport.counts.entry_points_missing}`,
    `- key_symbols_missing: ${buildResult.linkReport.counts.key_symbols_missing}`,
    ``,
    `## Samples (capped)`,
    `### modules`,
    ...buildResult.linkReport.missing_doc_refs.modules.slice(0, 40).map((x) => `- \`${x}\``),
    ``,
    `### entry_points`,
    ...buildResult.linkReport.missing_doc_refs.entry_points.slice(0, 40).map((x) => `- \`${x}\``),
    ``,
    `### key_symbols`,
    ...buildResult.linkReport.missing_doc_refs.key_symbols.slice(0, 40).map((x) => `- \`${x}\``),
    ``,
  ].join("\n")

  fs.writeFileSync(mapPath, mapText, "utf8")
  fs.writeFileSync(versionPath, versionText, "utf8")
  fs.writeFileSync(linkPath, linkText, "utf8")
  fs.writeFileSync(linkMdPath, linkMd, "utf8")
  if (buildResult.diff) {
    fs.writeFileSync(diffPath, JSON.stringify(buildResult.diff, null, 2) + "\n", "utf8")
    const d = buildResult.diff
    const md = [
      `# Map Diff (v1)`,
      ``,
      `- generated_at: ${d.generated_at}`,
      `- previous.hash: ${d.previous?.hash ?? ""}`,
      `- current.hash: ${d.current?.hash ?? ""}`,
      ``,
      `## Added`,
      `- modules: ${Array.isArray(d.added?.modules) ? d.added.modules.length : 0}`,
      `- entry_points: ${Array.isArray(d.added?.entry_points) ? d.added.entry_points.length : 0}`,
      `- contracts: ${Array.isArray(d.added?.contracts) ? d.added.contracts.length : 0}`,
      ``,
      `## Removed`,
      `- modules: ${Array.isArray(d.removed?.modules) ? d.removed.modules.length : 0}`,
      `- entry_points: ${Array.isArray(d.removed?.entry_points) ? d.removed.entry_points.length : 0}`,
      `- contracts: ${Array.isArray(d.removed?.contracts) ? d.removed.contracts.length : 0}`,
      ``,
    ].join("\n")
    fs.writeFileSync(diffMdPath, md, "utf8")
  }

  return {
    ok: true,
    outDir: out,
    mapPath,
    versionPath,
    linkReportPath: linkPath,
    linkReportMdPath: linkMdPath,
    diffPath: buildResult.diff ? diffPath : null,
    diffMdPath: buildResult.diff ? diffMdPath : null,
  }
}
