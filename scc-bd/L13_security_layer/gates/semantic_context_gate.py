import json
import pathlib


def _read_jsonl(path: pathlib.Path, tail: int = 2000) -> list[dict]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []
    out: list[dict] = []
    for ln in lines[-int(tail) :]:
        s = ln.strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
        except Exception:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def run(repo: pathlib.Path) -> list[str]:
    errors: list[str] = []
    p = repo / "semantic_context" / "index.jsonl"
    if not p.exists():
        return ["missing semantic_context/index.jsonl"]
    rows = _read_jsonl(p, tail=2000)
    if not rows:
        return ["semantic_context/index.jsonl: empty_or_unparseable"]

    # Minimal validation (fail-closed)
    required = {"schema_version", "entry_id", "created_at", "title", "content", "permissions", "sources"}
    for i, r in enumerate(rows[:200]):
        if r.get("schema_version") != "scc.semantic_context_entry.v1":
            errors.append(f"semantic_context/index.jsonl: row[{i}] schema_version mismatch")
            continue
        missing = [k for k in required if k not in r]
        if missing:
            errors.append(f"semantic_context/index.jsonl: row[{i}] missing keys: {','.join(missing)}")
        perms = r.get("permissions")
        if not isinstance(perms, dict) or not isinstance(perms.get("read_roles"), list) or not perms.get("read_roles"):
            errors.append(f"semantic_context/index.jsonl: row[{i}] permissions.read_roles missing/empty")
    return errors

