from __future__ import annotations

import pathlib

from tools.scc.lib.utils import load_json, norm_rel
from tools.scc.validators.contract_validator import validate_release_record_v1


def run(repo: pathlib.Path, submit: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(submit, dict):
        return ["release_gate: submit is not an object"]

    changed = submit.get("changed_files") or []
    new_files = submit.get("new_files") or []
    touched = submit.get("touched_files") or []
    candidates: list[str] = []
    for x in list(changed) + list(new_files) + list(touched):
        if isinstance(x, str) and x.strip():
            candidates.append(norm_rel(x))

    # Gate is conditional: only validate when release records are touched.
    targets = [p for p in sorted(set(candidates)) if p.endswith("/release.json") or p.endswith("release.json")]
    targets = [p for p in targets if p.startswith("releases/") or p.startswith("releases_selfcheck/")]
    if not targets:
        return []

    for rel in targets:
        p = (repo / rel).resolve()
        if not p.exists() or p.is_dir():
            errors.append(f"release_gate: missing release record: {rel}")
            continue
        try:
            obj = load_json(p)
        except Exception as e:
            errors.append(f"release_gate: bad json: {rel}: {e}")
            continue
        v = validate_release_record_v1(obj)
        if v:
            errors.append(f"release_gate: invalid release record: {rel}: {v[0]}")
            continue

        # Basic referential integrity: referenced files exist.
        artifacts = obj.get("artifacts") if isinstance(obj, dict) else None
        if isinstance(artifacts, dict):
            rr = artifacts.get("release_record_json")
            if isinstance(rr, str) and rr.strip():
                rr_p = (repo / norm_rel(rr)).resolve()
                if not rr_p.exists():
                    errors.append(f"release_gate: release_record_json missing: {rr}")
        sources = obj.get("sources") if isinstance(obj, dict) else None
        if isinstance(sources, list):
            for s in sources:
                if not isinstance(s, dict):
                    continue
                for k in ("submit_json", "patch_diff", "pr_bundle"):
                    v = s.get(k)
                    if isinstance(v, str) and v.strip():
                        sp = (repo / norm_rel(v)).resolve()
                        if not sp.exists():
                            errors.append(f"release_gate: missing source ref: {k}={v}")
                            break

    return errors

