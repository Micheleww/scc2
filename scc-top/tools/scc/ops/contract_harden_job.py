#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Contract Harden Job (v0.1.0)

Deterministically hardens generated contracts without using LLM tokens.
This is intended as a low-cost, fail-closed baseline when CodexCLI patch output is truncated.

Scope:
- Only touches contract files under docs/ssot/04_contracts/generated/*.json
- Writes a job report under docs/REPORT/<area>/ and artifacts under docs/REPORT/<area>/artifacts/<TaskCode>/
"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8", errors="replace") or "{}")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", errors="replace")


def _sha256_text(s: str) -> str:
    import hashlib

    h = hashlib.sha256()
    h.update((s or "").encode("utf-8", errors="replace"))
    return h.hexdigest()


def _utc_stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%SZ", time.gmtime())


def _contract_harden_patch(*, contract: dict, contract_path: str, task_id: str, area: str) -> Tuple[dict, List[str]]:
    """
    Returns (updated_contract, changes[]).
    """
    d = dict(contract)
    changes: List[str] = []

    # Ensure required top-level fields exist.
    for k in ["goal", "constraints", "inputs_ref", "outputs_expected"]:
        if k not in d:
            d[k] = {} if k in ("inputs_ref", "outputs_expected") else ""
            changes.append(f"add:{k}")

    # scope_allow (fail-closed, deterministic)
    #
    # v0.1.0 policy:
    # - scope_allow is a list of repo-relative glob/path patterns that the executor may write.
    # - contract_harden_job defaults to allow editing ONLY the contract file itself (so later scope_harden can widen it).
    scope_allow = d.get("scope_allow")
    needs_set = False
    if scope_allow is None:
        needs_set = True
    elif isinstance(scope_allow, str):
        s = scope_allow.strip()
        if (not s) or ("tbd" in s.lower()) or s.lower().startswith("allowlisted scope"):
            needs_set = True
        else:
            # If a string is present, keep it (planner may have set a single-path string). Normalize to list.
            d["scope_allow"] = [s]
            changes.append("normalize:scope_allow_str_to_list")
    elif isinstance(scope_allow, list):
        if not [x for x in scope_allow if str(x).strip()]:
            needs_set = True
    else:
        needs_set = True

    if needs_set:
        d["scope_allow"] = [contract_path]
        changes.append("set:scope_allow_default_contract_only")

    # Ensure scope_allow covers contract I/O references (still fail-closed).
    #
    # This is the deterministic equivalent of the "scope_harden" step and prevents a common dead-end:
    # - contracts include inputs_ref / outputs_expected / task_tree_ref
    # - but scope_allow remains trivial (contract-only), so any executor/verifier run would be blocked.
    def _collect_io_refs(doc: dict) -> List[str]:
        refs: List[str] = []
        inp0 = doc.get("inputs_ref")
        if isinstance(inp0, dict):
            p0 = inp0.get("paths")
            if isinstance(p0, list):
                refs.extend([str(x).strip() for x in p0 if str(x).strip()])
        out0 = doc.get("outputs_expected")
        if isinstance(out0, dict):
            ev0 = out0.get("evidence_paths")
            if isinstance(ev0, list):
                refs.extend([str(x).strip() for x in ev0 if str(x).strip()])
        tt0 = doc.get("task_tree_ref")
        if isinstance(tt0, str) and tt0.strip():
            refs.append(tt0.strip())
        # stable de-dupe in order
        seen: set[str] = set()
        out: List[str] = []
        for r in refs:
            r2 = r.replace("\\", "/").lstrip("./")
            if not r2 or r2 in seen:
                continue
            seen.add(r2)
            out.append(r2)
        return out

    scope_allow2 = d.get("scope_allow")
    if isinstance(scope_allow2, str):
        scope_allow_list = [scope_allow2.strip()] if scope_allow2.strip() else []
    elif isinstance(scope_allow2, list):
        scope_allow_list = [str(x).strip() for x in scope_allow2 if str(x).strip()]
    else:
        scope_allow_list = []
    io_refs = _collect_io_refs(d)
    missing_io = [r for r in io_refs if r not in scope_allow_list]
    if missing_io:
        d["scope_allow"] = scope_allow_list + missing_io
        changes.append("extend:scope_allow_io_refs")

    # stop_condition / commands_hint
    if not str(d.get("stop_condition") or "").strip() or "acceptance" in str(d.get("stop_condition") or "").lower():
        d["stop_condition"] = (
            "Stop immediately if any acceptance check fails, if any action would read/write outside scope_allow, "
            "or if any command would require network access."
        )
        changes.append("set:stop_condition")

    if not str(d.get("commands_hint") or "").strip():
        d["commands_hint"] = (
            "Edit only the allowlisted contract file. Keep scope_allow explicit and fail-closed. "
            "Prefer deterministic acceptance checks (json parse + required fields) then run verdict_basic last."
        )
        changes.append("set:commands_hint")

    # inputs_ref.paths must exist as list
    inp = d.get("inputs_ref")
    if not isinstance(inp, dict):
        inp = {}
        d["inputs_ref"] = inp
        changes.append("fix:inputs_ref_type")
    paths = inp.get("paths")
    if not isinstance(paths, list):
        inp["paths"] = []
        changes.append("fix:inputs_ref_paths")

    # outputs_expected.evidence_paths deterministic default if missing
    out = d.get("outputs_expected")
    if not isinstance(out, dict):
        out = {}
        d["outputs_expected"] = out
        changes.append("fix:outputs_expected_type")
    if not isinstance(out.get("evidence_paths"), list) or not out.get("evidence_paths"):
        out["evidence_paths"] = [f"docs/REPORT/{area}/artifacts/{task_id}/*"]
        changes.append("set:outputs_expected.evidence_paths")
    if out.get("verdict_required") is None:
        out["verdict_required"] = True
        changes.append("set:outputs_expected.verdict_required")

    # acceptance.checks ensure includes deterministic checks (no mvm-verdict in per-task contracts)
    acc = d.get("acceptance")
    if not isinstance(acc, dict):
        acc = {}
        d["acceptance"] = acc
        changes.append("fix:acceptance_type")
    checks = acc.get("checks")
    if not isinstance(checks, list):
        checks = []
        acc["checks"] = checks
        changes.append("fix:acceptance.checks_type")

    # Remove duplicate checks by name.
    def has(name: str) -> bool:
        return any(isinstance(c, dict) and c.get("name") == name for c in checks)

    if not has("contract_json_valid"):
        checks.insert(
            0,
            {"name": "contract_json_valid", "command": f"python -m json.tool {contract_path}"},
        )
        changes.append("add:acceptance.contract_json_valid")

    if not has("contract_required_fields_present"):
        cmd = (
            "python -c \"import json; p=r'"
            + contract_path
            + "'; d=json.load(open(p,encoding='utf-8')); "
            "req=['goal','scope_allow','constraints','acceptance','stop_condition','commands_hint','inputs_ref','outputs_expected']; "
            "missing=[k for k in req if k not in d]; assert not missing, missing; "
            "sa=d.get('scope_allow'); "
            "assert (isinstance(sa, list) and [x for x in sa if str(x).strip()]) or (isinstance(sa, str) and sa.strip()); "
            "assert 'TBD' not in str(sa); "
            "assert isinstance(d.get('acceptance',{}).get('checks'), list) and d['acceptance']['checks']; "
            "assert isinstance(d.get('stop_condition'), str) and d['stop_condition'].strip(); "
            "assert isinstance(d.get('commands_hint'), str) and d['commands_hint'].strip(); "
            "print('OK')\""
        )
        checks.insert(1, {"name": "contract_required_fields_present", "command": cmd})
        changes.append("add:acceptance.contract_required_fields_present")
    else:
        # Normalize legacy assertion (scope_allow was a string in earlier drafts).
        for c in checks:
            if not (isinstance(c, dict) and c.get("name") == "contract_required_fields_present"):
                continue
            cmd0 = str(c.get("command") or "")
            if "isinstance(d.get('scope_allow'), str)" not in cmd0:
                continue
            cmd = (
                "python -c \"import json; p=r'"
                + contract_path
                + "'; d=json.load(open(p,encoding='utf-8')); "
                "req=['goal','scope_allow','constraints','acceptance','stop_condition','commands_hint','inputs_ref','outputs_expected']; "
                "missing=[k for k in req if k not in d]; assert not missing, missing; "
                "sa=d.get('scope_allow'); "
                "assert (isinstance(sa, list) and [x for x in sa if str(x).strip()]) or (isinstance(sa, str) and sa.strip()); "
                "assert 'TBD' not in str(sa); "
                "assert isinstance(d.get('acceptance',{}).get('checks'), list) and d['acceptance']['checks']; "
                "assert isinstance(d.get('stop_condition'), str) and d['stop_condition'].strip(); "
                "assert isinstance(d.get('commands_hint'), str) and d['commands_hint'].strip(); "
                "print('OK')\""
            )
            c["command"] = cmd
            changes.append("normalize:acceptance.contract_required_fields_present")
            break

    if not has("contract_scope_allows_io_refs"):
        cmd = (
            "python -c \"import json; p=r'"
            + contract_path
            + "'; d=json.load(open(p,encoding='utf-8')); "
            "sa=set(d.get('scope_allow',[]) if isinstance(d.get('scope_allow'), list) else [d.get('scope_allow')]); "
            "refs=set(); "
            "refs |= set((d.get('inputs_ref') or {}).get('paths') or []) if isinstance(d.get('inputs_ref'), dict) else set(); "
            "refs |= set((d.get('outputs_expected') or {}).get('evidence_paths') or []) if isinstance(d.get('outputs_expected'), dict) else set(); "
            "tt=d.get('task_tree_ref'); "
            "refs.add(tt) if isinstance(tt,str) and tt.strip() else None; "
            "missing=sorted([r for r in refs if str(r).strip() and str(r).strip() not in sa]); "
            "assert not missing, missing; print('OK')\""
        )
        checks.append({"name": "contract_scope_allows_io_refs", "command": cmd})
        changes.append("add:acceptance.contract_scope_allows_io_refs")

    # Remove mvm-verdict check from per-task contracts (batch-level gate owns it).
    if any(isinstance(c, dict) and c.get("name") == "verdict_basic" for c in checks):
        checks = [c for c in checks if not (isinstance(c, dict) and c.get("name") == "verdict_basic")]
        changes.append("remove:acceptance.verdict_basic")

    # Remove placeholder blockers inserted by contractize (fail-closed until hardened).
    if any(isinstance(c, dict) and c.get("name") == "acceptance_tbd_blocker" for c in checks):
        checks = [c for c in checks if not (isinstance(c, dict) and c.get("name") == "acceptance_tbd_blocker")]
        changes.append("remove:acceptance.acceptance_tbd_blocker")

    # Ensure checks list is non-empty and stable order
    d["acceptance"]["checks"] = checks

    return d, changes


@dataclass
class Result:
    task_id: str
    contract_path: str
    changed: bool
    changes: List[str]
    sha_before: str
    sha_after: str


def main() -> int:
    ap = argparse.ArgumentParser(description="Deterministic contract harden job (no LLM)")
    ap.add_argument("--area", default="control_plane")
    ap.add_argument("--taskcode", required=True)
    ap.add_argument("--contracts", nargs="*", default=[], help="Explicit contract paths (repo-relative). If empty, reads from task_tree.json.")
    ap.add_argument("--task-tree", default="docs/DERIVED/task_tree.json")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only-tbd", action="store_true", default=True, help="Only harden contracts with scope_allow containing TBD/empty (default).")
    ap.add_argument("--include-non-tbd", action="store_true", default=False, help="Also process contracts even if scope_allow is already hardened.")
    ap.add_argument("--emit-report", action="store_true", default=True)
    args = ap.parse_args()

    repo_root = _repo_root()
    area = str(args.area)
    taskcode = str(args.taskcode)
    limit = int(args.limit or 0)

    targets: List[str] = [str(x).replace("\\", "/") for x in (args.contracts or []) if str(x).strip()]
    if not targets:
        tt = Path(args.task_tree)
        if not tt.is_absolute():
            tt = (repo_root / tt).resolve()
        tree = _read_json(tt)
        # Support both flattened and EPIC/CAPABILITY nested task_tree formats.
        flat_tasks = tree.get("tasks") if isinstance(tree.get("tasks"), list) else []
        if flat_tasks:
            for t in flat_tasks:
                if not isinstance(t, dict):
                    continue
                ref = str(t.get("contract_ref") or "").strip()
                if ref:
                    targets.append(ref.replace("\\", "/"))
        else:
            epics = tree.get("epics") if isinstance(tree.get("epics"), list) else []
            for e in epics:
                if not isinstance(e, dict):
                    continue
                caps = e.get("capabilities") if isinstance(e.get("capabilities"), list) else []
                for c in caps:
                    if not isinstance(c, dict):
                        continue
                    tasks = c.get("tasks") if isinstance(c.get("tasks"), list) else []
                    for t in tasks:
                        if not isinstance(t, dict):
                            continue
                        ref = str(t.get("contract_ref") or "").strip()
                        if ref:
                            targets.append(ref.replace("\\", "/"))
        # stable de-dupe
        seen = set()
        targets = [p for p in targets if not (p in seen or seen.add(p))]

    if limit > 0:
        targets = targets[:limit]

    results: List[Result] = []
    for rel in targets:
        p = (repo_root / rel).resolve()
        if not p.exists() or not p.is_file():
            continue
        if not str(rel).replace("\\", "/").startswith("docs/ssot/04_contracts/generated/"):
            continue
        raw_before = p.read_text(encoding="utf-8", errors="replace")
        sha_before = _sha256_text(raw_before)
        d = _read_json(p)
        task_id = str(d.get("task_id") or "").strip()
        if not task_id:
            continue
        if bool(args.only_tbd) and not bool(args.include_non_tbd):
            # Treat "contract-only" scope as needing harden, because it blocks execution/verification.
            scope = d.get("scope_allow")
            scope_items: List[str] = []
            if isinstance(scope, str) and scope.strip():
                scope_items = [scope.strip()]
            elif isinstance(scope, list):
                scope_items = [str(x).strip() for x in scope if str(x).strip()]

            scope_text = " ".join(scope_items) if scope_items else ""
            is_explicit_tbd = (not scope_items) or ("TBD" in scope_text.upper())
            is_trivial_contract_only = scope_items == [rel.replace("\\", "/")]

            # Also treat missing I/O refs as needing harden.
            io_refs = []
            try:
                io_refs = [x for x in (d.get("inputs_ref") or {}).get("paths", []) if str(x).strip()] if isinstance(d.get("inputs_ref"), dict) else []
                if isinstance(d.get("outputs_expected"), dict):
                    io_refs += [x for x in (d.get("outputs_expected") or {}).get("evidence_paths", []) if str(x).strip()]
                tt = d.get("task_tree_ref")
                if isinstance(tt, str) and tt.strip():
                    io_refs.append(tt.strip())
            except Exception:
                io_refs = []
            missing_io = [r for r in io_refs if str(r).strip() and str(r).strip() not in set(scope_items)]

            if not (is_explicit_tbd or is_trivial_contract_only or missing_io):
                continue

        updated, changes = _contract_harden_patch(contract=d, contract_path=rel.replace("\\", "/"), task_id=task_id, area=area)
        raw_after = json.dumps(updated, ensure_ascii=False, indent=2) + "\n"
        sha_after = _sha256_text(raw_after)
        changed = sha_after != sha_before
        if changed:
            p.write_text(raw_after, encoding="utf-8", errors="replace")
        results.append(Result(task_id=task_id, contract_path=rel.replace("\\", "/"), changed=changed, changes=changes, sha_before=sha_before, sha_after=sha_after))

    stamp = _utc_stamp()
    artifacts_dir = (repo_root / "docs" / "REPORT" / area / "artifacts" / taskcode).resolve()
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "v0.1.0",
        "ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "taskcode": taskcode,
        "area": area,
        "count": len(results),
        "changed": sum(1 for r in results if r.changed),
        "results": [r.__dict__ for r in results],
    }
    _write_json(artifacts_dir / f"contract_harden_job__{stamp}.json", payload)

    if bool(args.emit_report):
        # Use the shared triplet helper (guard-compatible).
        # Note: evidence_hashes.json is created by evidence_triplet.py and includes report + artifacts files.
        import subprocess

        notes_lines: List[str] = []
        notes_lines.append(f"- count: {payload['count']} changed: {payload['changed']}")
        notes_lines.append("## Results")
        for r in results:
            notes_lines.append(f"- task_id=`{r.task_id}` changed={r.changed} contract=`{r.contract_path}`")
        notes = "\n".join(notes_lines).strip()

        ev = [
            f"docs/REPORT/{area}/artifacts/{taskcode}/contract_harden_job__{stamp}.json",
        ]
        cmd = [
            os.environ.get("PYTHON", "python"),
            "tools/scc/ops/evidence_triplet.py",
            "--taskcode",
            taskcode,
            "--area",
            area,
            "--title",
            f"REPORT__{taskcode}",
            "--notes",
            notes,
        ]
        for p in ev:
            cmd += ["--evidence", p]
        subprocess.run(cmd, cwd=str(repo_root), check=False)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
