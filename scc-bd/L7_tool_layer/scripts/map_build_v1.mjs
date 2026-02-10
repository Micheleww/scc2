import path from "node:path"
import process from "node:process"
import fs from "node:fs"
import { execFileSync } from "node:child_process"
import { buildMapV1, writeMapV1Outputs, defaultMapRoots, defaultMapExcludes } from "../../L17_ontology_layer/map_v1/map_v1.mjs"

function parseArgs(argv) {
  const out = {
    roots: null,
    excludes: null,
    outDir: "map",
    repoRoot: null,
    maxFiles: 20000,
    maxFileBytes: 900_000,
    incremental: true,
    previousMapPath: null,
    sqlite: false,
  }
  for (let i = 2; i < argv.length; i += 1) {
    const a = String(argv[i] ?? "")
    const next = argv[i + 1]
    if (a === "--repo-root") {
      out.repoRoot = String(next ?? "")
      i += 1
      continue
    }
    if (a === "--out") {
      out.outDir = String(next ?? "map")
      i += 1
      continue
    }
    if (a === "--roots") {
      out.roots = String(next ?? "")
        .split(/[;,]/g)
        .map((x) => x.trim())
        .filter(Boolean)
      i += 1
      continue
    }
    if (a === "--exclude") {
      out.excludes = String(next ?? "")
        .split(/[;,]/g)
        .map((x) => x.trim())
        .filter(Boolean)
      i += 1
      continue
    }
    if (a === "--max-files") {
      out.maxFiles = Number(next ?? out.maxFiles)
      i += 1
      continue
    }
    if (a === "--max-file-bytes") {
      out.maxFileBytes = Number(next ?? out.maxFileBytes)
      i += 1
      continue
    }
    if (a === "--no-incremental") {
      out.incremental = false
      continue
    }
    if (a === "--previous-map") {
      out.previousMapPath = String(next ?? "")
      i += 1
      continue
    }
    if (a === "--sqlite") {
      out.sqlite = true
      continue
    }
  }
  return out
}

const args = parseArgs(process.argv)
const repoRoot = path.resolve(args.repoRoot || process.env.SCC_REPO_ROOT || path.join(process.cwd(), ".."))
const roots = args.roots && args.roots.length ? args.roots : defaultMapRoots()
const excludes = args.excludes && args.excludes.length ? args.excludes : defaultMapExcludes()

const startedAt = Date.now()
const res = buildMapV1({
  repoRoot,
  roots,
  excludes,
  maxFiles: args.maxFiles,
  maxFileBytes: args.maxFileBytes,
  incremental: args.incremental,
  previousMapPath: args.previousMapPath,
})
const wrote = writeMapV1Outputs({ repoRoot, outDir: args.outDir, buildResult: res })
const ms = Date.now() - startedAt

let sqlite = null
const wantSqlite =
  args.sqlite ||
  String(process.env.MAP_BUILD_SQLITE ?? "").toLowerCase() === "true" ||
  String(process.env.MAP_QUERY_BACKEND ?? "").toLowerCase() === "sqlite" ||
  String(process.env.MAP_PINS_QUERY_BACKEND ?? "").toLowerCase() === "sqlite" ||
  String(process.env.MAP_SQLITE_REQUIRED ?? "").toLowerCase() === "true" ||
  fs.existsSync(path.join(repoRoot, "map", "map.sqlite"))
if (wantSqlite) {
  try {
    const stdout = execFileSync(
      "python",
      [
        "tools/scc/map/map_sqlite_v1.py",
        "--repo-root",
        repoRoot,
        "--map",
        wrote.mapPath.replaceAll("\\", "/"),
        "--version",
        wrote.versionPath.replaceAll("\\", "/"),
        "--out",
        "map/map.sqlite",
        "--force",
      ],
      { cwd: repoRoot, windowsHide: true, timeout: 120000, maxBuffer: 10 * 1024 * 1024, encoding: "utf8" },
    )
    sqlite = JSON.parse(String(stdout ?? "").replace(/^\uFEFF/, ""))
  } catch (e) {
    sqlite = { ok: false, error: "sqlite_build_failed", message: String(e?.message ?? e) }
  }
}

console.log(
  JSON.stringify(
    {
      ok: true,
      repoRoot,
      outDir: wrote.outDir.replaceAll("\\", "/"),
      files: {
        map: wrote.mapPath.replaceAll("\\", "/"),
        version: wrote.versionPath.replaceAll("\\", "/"),
        link_report: wrote.linkReportPath.replaceAll("\\", "/"),
        link_report_md: wrote.linkReportMdPath.replaceAll("\\", "/"),
      },
      sqlite,
      hash: res.version.hash,
      stats: res.version.stats,
      durationMs: ms,
    },
    null,
    2,
  ),
)

process.exitCode = 0
