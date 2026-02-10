import pathlib

from tools.scc.lib.utils import load_json as _load_json


def run(repo: pathlib.Path) -> list[str]:
    errors: list[str] = []
    p = repo / "connectors" / "registry.json"
    if not p.exists():
        return ["missing connectors/registry.json"]
    try:
        obj = _load_json(p)
    except Exception as e:
        return [f"connectors/registry.json: json_parse_failed: {e}"]

    if not isinstance(obj, dict) or obj.get("schema_version") != "scc.connector_registry.v1":
        return ["connectors/registry.json: schema_version != scc.connector_registry.v1"]

    cs = obj.get("connectors")
    if not isinstance(cs, list) or not cs:
        return ["connectors/registry.json: connectors must be non-empty array"]

    seen: set[str] = set()
    for i, c in enumerate(cs[:200]):
        if not isinstance(c, dict):
            errors.append(f"connectors/registry.json: connectors[{i}] not object")
            continue
        cid = str(c.get("connector_id") or "").strip()
        if not cid:
            errors.append(f"connectors/registry.json: connectors[{i}].connector_id missing")
            continue
        if cid in seen:
            errors.append(f"connectors/registry.json: duplicate connector_id {cid}")
        seen.add(cid)
        typ = str(c.get("type") or "").strip()
        if typ not in {"cli", "http_service", "mcp_server"}:
            errors.append(f"connectors/registry.json: {cid} invalid type {typ!r}")
        eps = c.get("endpoints")
        if not (isinstance(eps, list) and any(isinstance(x, str) and x.strip() for x in eps)):
            errors.append(f"connectors/registry.json: {cid} endpoints missing/empty")
        scopes = c.get("scopes")
        if not (isinstance(scopes, list) and any(isinstance(x, str) and x.strip() for x in scopes)):
            errors.append(f"connectors/registry.json: {cid} scopes missing/empty")
        roles = c.get("allowed_roles")
        if not (isinstance(roles, list) and any(isinstance(x, str) and x.strip() for x in roles)):
            errors.append(f"connectors/registry.json: {cid} allowed_roles missing/empty")
        audit = c.get("audit")
        if not isinstance(audit, dict) or not isinstance(audit.get("logs"), list):
            errors.append(f"connectors/registry.json: {cid} audit.logs missing/invalid")

    return errors

