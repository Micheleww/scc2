import hashlib
import json
import pathlib
from typing import Any

from tools.scc.lib.utils import load_json, norm_rel


def _sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def _stable_normalize(x: Any) -> Any:
    if isinstance(x, dict):
        # sort keys
        return {k: _stable_normalize(x[k]) for k in sorted(x.keys())}
    if isinstance(x, list):
        return [_stable_normalize(v) for v in x]
    return x


def _stable_dumps(x: Any) -> str:
    # Match JS stableStringify: keys sorted, no whitespace.
    return json.dumps(_stable_normalize(x), ensure_ascii=False, separators=(",", ":"))


def _validate_pack(repo: pathlib.Path, pack: dict) -> list[str]:
    errors: list[str] = []

    if pack.get("schema_version") != "scc.context_pack.v1":
        errors.append("context_pack.schema_version != scc.context_pack.v1")
        return errors

    slots = pack.get("slots")
    if not isinstance(slots, list):
        errors.append("context_pack.slots must be array")
        return errors

    by_slot: dict[int, dict] = {}
    for it in slots:
        if not isinstance(it, dict):
            continue
        s = it.get("slot")
        if isinstance(s, int):
            by_slot[s] = it

    for must in (0, 1, 3):
        if must not in by_slot:
            errors.append(f"missing required slot {must}")

    if by_slot.get(0, {}).get("kind") != "LEGAL_PREFIX":
        errors.append("slot0.kind != LEGAL_PREFIX")
    if by_slot.get(1, {}).get("kind") != "BINDING_REFS":
        errors.append("slot1.kind != BINDING_REFS")
    if by_slot.get(3, {}).get("kind") != "TASK_BUNDLE":
        errors.append("slot3.kind != TASK_BUNDLE")

    # Hash check (fail-closed): hash is sha256(stableStringify(pack without hash)).
    want = str(pack.get("hash") or "").strip()
    pack_wo = dict(pack)
    pack_wo.pop("hash", None)
    got = "sha256:" + hashlib.sha256(_stable_dumps(pack_wo).encode("utf-8")).hexdigest()
    if want != got:
        errors.append(f"pack hash mismatch: want={want} got={got}")

    # Refs integrity
    refs_index = by_slot.get(1, {}).get("refs_index")
    refs = refs_index.get("refs") if isinstance(refs_index, dict) else None
    if not isinstance(refs, list):
        errors.append("slot1.refs_index.refs must be array")
        return errors

    for r in refs[:200]:
        if not isinstance(r, dict):
            errors.append("refs_index.refs[] invalid entry")
            continue
        rel = str(r.get("path") or "").strip()
        ver = str(r.get("version") or "").strip()
        want_h = str(r.get("hash") or "").strip()
        if not rel:
            errors.append("ref missing path")
            continue
        if not ver:
            errors.append(f"ref missing version: {rel}")
        abs_path = (repo / norm_rel(rel)).resolve()
        if not abs_path.exists():
            errors.append(f"ref file missing: {rel}")
            continue
        got_h = _sha256_file(abs_path)
        if want_h != got_h:
            errors.append(f"ref hash mismatch: {rel} want={want_h} got={got_h}")

    return errors


def run(repo: pathlib.Path, submit: dict, *, strict: bool = True) -> dict:
    """
    Gate: require a slot-based Context Pack v1 reference for a task and verify:
    - required slots exist (SLOT0/1/3)
    - pack hash matches stable serialization
    - refs_index file hashes match (fail-closed)
    """
    task_id = str((submit or {}).get("task_id") or "unknown")
    ref_path = (repo / "artifacts" / task_id / "context_pack_v1.json").resolve()
    if not ref_path.exists():
        if strict:
            return {"errors": ["missing artifacts/<task_id>/context_pack_v1.json"], "warnings": []}
        return {"errors": [], "warnings": ["missing artifacts/<task_id>/context_pack_v1.json (non-strict)"]}

    try:
        ref = load_json(ref_path)
    except Exception as e:
        return {"errors": [f"context_pack_v1.json parse failed: {e}"], "warnings": []}

    cp_id = str(ref.get("context_pack_id") or "").strip()
    if not cp_id:
        return {"errors": ["context_pack_v1.json: missing context_pack_id"], "warnings": []}

    pack_path = (repo / "artifacts" / "scc_runs" / cp_id / "rendered_context_pack.json").resolve()
    if not pack_path.exists():
        return {"errors": [f"missing rendered_context_pack.json for context_pack_id={cp_id}"], "warnings": []}

    try:
        pack = load_json(pack_path)
    except Exception as e:
        return {"errors": [f"rendered_context_pack.json parse failed: {e}"], "warnings": []}

    errors = _validate_pack(repo, pack if isinstance(pack, dict) else {})
    return {"errors": errors, "warnings": []}

