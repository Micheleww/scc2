import hashlib
import json
import pathlib
from datetime import datetime, timezone


def _norm_rel(p: str) -> str:
    return p.replace("\\", "/").lstrip("./")


def _load_json(path: pathlib.Path):
    return json.loads(path.read_text(encoding="utf-8").lstrip("\ufeff"))


def _stable_dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _facts_from_map(map_obj: dict) -> dict:
    coverage_roots = []
    try:
        cov = map_obj.get("coverage") or {}
        roots = cov.get("roots") or []
        if isinstance(roots, list):
            coverage_roots = [str(x) for x in roots if isinstance(x, str) and x.strip()]
    except Exception:
        coverage_roots = []

    entry_ids = set()
    for e in map_obj.get("entry_points") or []:
        if not isinstance(e, dict):
            continue
        p = str(e.get("path") or "")
        if not _norm_rel(p).startswith("oc-scc-local/"):
            continue
        i = e.get("id")
        if i:
            sid = str(i)
            # Keep SSOT entry_points stable: treat selfcheck/test scripts as non-entrypoints.
            if ":selfcheck:" in sid:
                continue
            entry_ids.add(sid)

    file_index = map_obj.get("file_index") or {}
    contracts = []
    if isinstance(file_index, dict):
        for k in file_index.keys():
            if not isinstance(k, str):
                continue
            kk = _norm_rel(k)
            if kk.startswith("contracts/") and kk.endswith(".schema.json"):
                contracts.append(kk)
    contracts.sort()

    return {
        "modules": sorted({str(x) for x in coverage_roots if str(x).strip()}),
        "entry_points": sorted(entry_ids),
        "contracts": contracts,
    }


def _facts_hash(facts: dict) -> str:
    return f"sha256:{_sha256_hex(_stable_dumps(facts))}"


def run(repo: pathlib.Path, submit: dict) -> list[str]:
    errors: list[str] = []
    task_id = str(submit.get("task_id") or "unknown")

    registry_path = repo / "docs" / "SSOT" / "registry.json"
    if not registry_path.exists():
        return ["missing docs/SSOT/registry.json (SSOT facts registry)"]

    map_path = repo / "map" / "map.json"
    ver_path = repo / "map" / "version.json"
    if not map_path.exists():
        return ["missing map/map.json (run: npm --prefix oc-scc-local run map:build)"]
    if not ver_path.exists():
        errors.append("missing map/version.json (run: npm --prefix oc-scc-local run map:build)")

    try:
        reg = _load_json(registry_path)
    except Exception as e:
        return [f"docs/SSOT/registry.json invalid json: {e}"]

    if reg.get("schema_version") != "scc.ssot_registry.v1":
        errors.append("docs/SSOT/registry.json: schema_version != scc.ssot_registry.v1")

    facts_reg = reg.get("facts") if isinstance(reg, dict) else None
    if not isinstance(facts_reg, dict):
        return errors + ["docs/SSOT/registry.json: missing facts{}"]

    reg_modules = [str(x) for x in (facts_reg.get("modules") or []) if isinstance(x, str) and x.strip()]
    reg_entry = [str(x) for x in (facts_reg.get("entry_points") or []) if isinstance(x, str) and x.strip()]
    reg_contracts = [_norm_rel(str(x)) for x in (facts_reg.get("contracts") or []) if isinstance(x, str) and x.strip()]

    for rel in reg_contracts:
        if not (repo / rel).exists():
            errors.append(f"docs/SSOT/registry.json references missing contract schema: {rel}")

    try:
        map_obj = _load_json(map_path)
    except Exception as e:
        return errors + [f"map/map.json invalid json: {e}"]

    facts_map = _facts_from_map(map_obj)
    facts_hash = _facts_hash(facts_map)

    missing = {
        "modules": sorted(set(facts_map["modules"]) - set(reg_modules)),
        "entry_points": sorted(set(facts_map["entry_points"]) - set(reg_entry)),
        "contracts": sorted(set(facts_map["contracts"]) - set(reg_contracts)),
    }
    stale = {
        "modules": sorted(set(reg_modules) - set(facts_map["modules"])),
        "entry_points": sorted(set(reg_entry) - set(facts_map["entry_points"])),
        "contracts": sorted(set(reg_contracts) - set(facts_map["contracts"])),
    }

    try:
        ver = _load_json(ver_path) if ver_path.exists() else {}
        map_hash = str(ver.get("hash") or "")
        map_path_rel = str(ver.get("map_path") or "map/map.json")
    except Exception:
        map_hash = ""
        map_path_rel = "map/map.json"

    suggestion = {
        "schema_version": "scc.ssot_update.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "task_id": task_id,
        "sources": {"map_path": map_path_rel, "map_hash": map_hash or "sha256:" + "0" * 64, "facts_hash": facts_hash},
        "missing": missing,
        "stale": stale,
        "notes": "Update docs/SSOT/registry.json to match Map-derived facts (coverage.roots + oc-scc-local entry points + contracts/*.schema.json).",
    }

    out_dir = repo / "artifacts" / task_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "ssot_update.json"
    out_path.write_text(json.dumps(suggestion, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if missing["modules"] or missing["entry_points"] or missing["contracts"]:
        errors.append(f"SSOT registry missing facts (see {out_path.as_posix()}): {json.dumps(missing, ensure_ascii=False)}")
    if stale["modules"] or stale["entry_points"] or stale["contracts"]:
        errors.append(f"SSOT registry has stale facts (see {out_path.as_posix()}): {json.dumps(stale, ensure_ascii=False)}")

    return errors
