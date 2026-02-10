import hashlib
import json
import pathlib
import os
import sqlite3
from datetime import datetime, timezone

from tools.scc.lib.utils import load_json, norm_rel as _norm_rel


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _stable_dumps(obj) -> str:
    # Match JS stableStringify() behavior: sort keys recursively, no whitespace.
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _compute_map_hash(map_obj: dict) -> str:
    stable = {
        "schema_version": map_obj.get("schema_version"),
        "generator": map_obj.get("generator"),
        "coverage": map_obj.get("coverage"),
        "modules": map_obj.get("modules"),
        "entry_points": map_obj.get("entry_points"),
        "key_symbols": map_obj.get("key_symbols"),
        "test_entry_points": map_obj.get("test_entry_points"),
        "configs": map_obj.get("configs"),
        "doc_refs": map_obj.get("doc_refs"),
    }
    return f"sha256:{_sha256_hex(_stable_dumps(stable))}"


def _compute_facts_hash(map_obj: dict) -> str:
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

    facts = {
        "modules": sorted({str(m.get("root")) for m in (map_obj.get("modules") or []) if isinstance(m, dict) and m.get("root")}),
        "entry_points": sorted({str(e.get("id")) for e in (map_obj.get("entry_points") or []) if isinstance(e, dict) and e.get("id")}),
        "contracts": contracts,
    }
    return f"sha256:{_sha256_hex(_stable_dumps(facts))}"

def _read_sqlite_meta(sqlite_path: pathlib.Path, key: str) -> str:
    try:
        conn = sqlite3.connect(str(sqlite_path))
        try:
            row = conn.execute("SELECT v FROM meta WHERE k = ?", (key,)).fetchone()
            if not row:
                return ""
            return str(row[0] or "")
        finally:
            conn.close()
    except Exception:
        return ""


def run(repo: pathlib.Path) -> list[str]:
    errors: list[str] = []
    map_path = repo / "map" / "map.json"
    ver_path = repo / "map" / "version.json"
    link_path = repo / "map" / "link_report.json"
    sqlite_path = repo / "map" / "map.sqlite"

    if not map_path.exists():
        return ["missing map/map.json (run: npm --prefix oc-scc-local run map:build)"]
    if not ver_path.exists():
        return ["missing map/version.json (run: npm --prefix oc-scc-local run map:build)"]
    if not link_path.exists():
        errors.append("missing map/link_report.json (run: npm --prefix oc-scc-local run map:build)")

    try:
        map_obj = _load_json(map_path)
    except Exception as e:
        return [f"map/map.json invalid json: {e}"]
    try:
        ver_obj = _load_json(ver_path)
    except Exception as e:
        return [f"map/version.json invalid json: {e}"]

    if map_obj.get("schema_version") != "scc.map.v1":
        errors.append("map/map.json: schema_version != scc.map.v1")
    if ver_obj.get("schema_version") != "scc.map_version.v1":
        errors.append("map/version.json: schema_version != scc.map_version.v1")

    # Gate policy: generator + coverage must match expectations (SSOT-like invariants).
    try:
        gen = ver_obj.get("generator") if isinstance(ver_obj.get("generator"), dict) else {}
        gname = str(gen.get("name") or "")
        gver = str(gen.get("version") or "")
        if gname != "scc.map_builder.v1":
            errors.append(f"map/version.json: generator.name unexpected: {gname!r}")
        if not gver:
            errors.append("map/version.json: generator.version missing")
    except Exception:
        errors.append("map/version.json: generator parse failed")

    # Map freshness: fail-closed when too old (override via MAP_MAX_AGE_HOURS) or past valid_until.
    try:
        vu = str(ver_obj.get("valid_until") or "")
        if vu:
            dt2 = datetime.fromisoformat(vu.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) > dt2.astimezone(timezone.utc):
                errors.append(f"map/version.json expired: valid_until={vu}")

        max_age_hours = int(os.environ.get("MAP_MAX_AGE_HOURS") or "168")
        if max_age_hours > 0:
            ts = str(ver_obj.get("generated_at") or "")
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            age_s = (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds()
            if age_s > max_age_hours * 3600:
                errors.append(f"map/version.json too old: age_hours={age_s/3600:.1f} max={max_age_hours}")
    except Exception:
        errors.append("map/version.json: generated_at parse failed for freshness gate")

    # Coverage roots should include required control-plane areas.
    try:
        cov = ver_obj.get("coverage") if isinstance(ver_obj.get("coverage"), dict) else {}
        roots = cov.get("roots") if isinstance(cov.get("roots"), list) else []
        roots_set = {str(x) for x in roots if isinstance(x, str) and x.strip()}
        required = {"oc-scc-local", "tools/scc", "contracts", "roles", "skills", "docs"}
        missing = sorted(required - roots_set)
        if missing:
            errors.append(f"map/version.json coverage.roots missing required: {missing}")
    except Exception:
        errors.append("map/version.json: coverage parse failed")

    # Optional: require map.sqlite for faster queries.
    require_sqlite = str(os.environ.get("MAP_SQLITE_REQUIRED") or "false").lower() == "true"
    if require_sqlite and not sqlite_path.exists():
        errors.append("missing map/map.sqlite (run: npm --prefix oc-scc-local run map:sqlite)")

    want_sqlite_backend = (
        str(os.environ.get("MAP_QUERY_BACKEND") or "").lower() == "sqlite"
        or str(os.environ.get("MAP_PINS_QUERY_BACKEND") or "").lower() == "sqlite"
    )

    expected_hash = _compute_map_hash(map_obj)
    declared_hash = str(ver_obj.get("hash") or "")
    if declared_hash != expected_hash:
        errors.append(f"map hash mismatch: version.json hash={declared_hash} expected={expected_hash}")

    declared_facts = str(ver_obj.get("facts_hash") or "")
    if declared_facts:
        expected_facts = _compute_facts_hash(map_obj)
        if declared_facts != expected_facts:
            errors.append(f"map facts_hash mismatch: version.json facts_hash={declared_facts} expected={expected_facts}")

    # If sqlite is used/required, it must match the current map/version.json hash (fail-closed).
    if sqlite_path.exists() and (require_sqlite or want_sqlite_backend):
        meta_hash = _read_sqlite_meta(sqlite_path, "map_hash")
        if not meta_hash:
            errors.append("map/map.sqlite missing meta.map_hash (rebuild sqlite: npm --prefix oc-scc-local run map:sqlite)")
        elif declared_hash and meta_hash != declared_hash:
            errors.append(f"map sqlite stale: meta.map_hash={meta_hash} version.json hash={declared_hash} (rebuild sqlite)")

    if link_path.exists():
        try:
            link_obj = _load_json(link_path)
            if link_obj.get("schema_version") != "scc.link_report.v1":
                errors.append("map/link_report.json: schema_version != scc.link_report.v1")
            link_hash = str(link_obj.get("map_hash") or "")
            if link_hash and link_hash != expected_hash:
                errors.append(f"map/link_report.json map_hash mismatch: {link_hash} expected={expected_hash}")
        except Exception as e:
            errors.append(f"map/link_report.json invalid json: {e}")

    # If map content changes, SSOT should be updated (NAVIGATION/INDEX) eventually.
    touched = set()
    try:
        # Best-effort: use version map_path/link_report_path for drift detection.
        for k in ("map_path", "link_report_path"):
            v = ver_obj.get(k)
            if v:
                touched.add(norm_rel(str(v)))
    except Exception:
        pass

    return errors
