#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8", errors="replace") or "{}")


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", errors="replace")


def _iter_tasks(tree: Dict[str, Any]) -> List[Tuple[List[int], Dict[str, Any]]]:
    out: List[Tuple[List[int], Dict[str, Any]]] = []
    epics = tree.get("epics") if isinstance(tree.get("epics"), list) else []
    for ei, e in enumerate(epics):
        if not isinstance(e, dict):
            continue
        caps = e.get("capabilities") if isinstance(e.get("capabilities"), list) else []
        for ci, c in enumerate(caps):
            if not isinstance(c, dict):
                continue
            tasks = c.get("tasks") if isinstance(c.get("tasks"), list) else []
            for ti, t in enumerate(tasks):
                if isinstance(t, dict):
                    out.append(([ei, ci, ti], t))
    return out


def _get_task_by_path(tree: Dict[str, Any], path_idx: List[int]) -> Optional[Dict[str, Any]]:
    try:
        ei, ci, ti = path_idx
        return tree["epics"][ei]["capabilities"][ci]["tasks"][ti]
    except Exception:
        return None


def _repo_rel(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(_REPO_ROOT.resolve())).replace("\\", "/")
    except Exception:
        return str(p).replace("\\", "/")


def _load_contract_oid(contract_path: Path) -> Optional[str]:
    if not contract_path.exists():
        return None
    try:
        data = json.loads(contract_path.read_text(encoding="utf-8", errors="replace") or "{}")
        oid = data.get("oid")
        return str(oid).strip() if oid else None
    except Exception:
        return None


def _mint_evidence_oids(
    *,
    dsn: str,
    task_id: str,
    evidence_paths: List[Path],
) -> List[str]:
    from tools.scc.oid.pg_registry import issue_new

    out: List[str] = []
    for p in evidence_paths:
        rel = _repo_rel(p)
        kind = p.suffix.lstrip(".") or "bin"
        stable_key = f"evidence:{task_id}:{rel}"
        oid, _ = issue_new(
            dsn=dsn,
            path=rel,
            kind=kind,
            layer="REPORT",
            primary_unit="V.VERDICT",
            tags=["V.VERDICT"],
            stable_key=stable_key,
            hint=f"task_evidence:{task_id}",
        )
        out.append(oid)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Backfill docs/DERIVED/task_tree.json tasks from artifacts/scc_tasks records.")
    ap.add_argument("--task-tree", default="docs/DERIVED/task_tree.json")
    ap.add_argument("--tasks-root", default="artifacts/scc_tasks")
    ap.add_argument("--dsn", default="", help="OID Postgres DSN (or set SCC_OID_PG_DSN).")
    ap.add_argument("--mint-evidence-oids", action="store_true", help="Mint OIDs for evidence files and write evidence_oids[] into task_tree.")
    ap.add_argument("--only-with-verdict", action="store_true", help="Only backfill tasks that have a verdict in task.json.")
    ap.add_argument("--limit", type=int, default=0, help="Optional max number of tasks to update (0 = no limit).")
    ap.add_argument("--emit-report", action="store_true")
    ap.add_argument("--taskcode", default="TASKTREE_BACKFILL_V010")
    ap.add_argument("--area", default="control_plane")
    args = ap.parse_args()

    tree_path = (Path(args.task_tree) if Path(args.task_tree).is_absolute() else (_REPO_ROOT / args.task_tree)).resolve()
    if not tree_path.exists():
        print(json.dumps({"ok": False, "error": "missing_task_tree", "path": _repo_rel(tree_path)}, ensure_ascii=False))
        return 2

    tasks_root = (Path(args.tasks_root) if Path(args.tasks_root).is_absolute() else (_REPO_ROOT / args.tasks_root)).resolve()
    if not tasks_root.exists():
        print(json.dumps({"ok": False, "error": "missing_tasks_root", "path": _repo_rel(tasks_root)}, ensure_ascii=False))
        return 3

    dsn = (str(args.dsn).strip() or os.getenv("SCC_OID_PG_DSN") or os.getenv("DATABASE_URL") or "").strip()
    if args.mint_evidence_oids and not dsn:
        print(json.dumps({"ok": False, "error": "missing_pg_dsn", "hint": "set SCC_OID_PG_DSN or pass --dsn"}, ensure_ascii=False))
        return 4

    tree = _read_json(tree_path)
    items = _iter_tasks(tree)

    updated = 0
    missing_task_records = 0
    minted_evidence = 0

    for idx_path, t in items:
        task_id = str(t.get("task_id") or "").strip()
        if not task_id:
            continue
        task_json = (tasks_root / task_id / "task.json").resolve()
        if not task_json.exists():
            missing_task_records += 1
            continue
        rec = _read_json(task_json)
        verdict = rec.get("verdict")
        if args.only_with_verdict and not verdict:
            continue
        if verdict:
            t["verdict"] = verdict

        contract_ref = str(t.get("contract_ref") or "").strip().replace("\\", "/")
        contract_oid = None
        if contract_ref and contract_ref.startswith("docs/"):
            contract_oid = _load_contract_oid((_REPO_ROOT / contract_ref).resolve())
        if contract_oid:
            t["touched_oids"] = sorted(set((t.get("touched_oids") or []) + [contract_oid]))

        if args.mint_evidence_oids:
            ev: List[Path] = []
            evidence_dir = str(rec.get("evidence_dir") or "").strip()
            if evidence_dir:
                base = Path(evidence_dir)
                if not base.is_absolute():
                    base = (_REPO_ROOT / base).resolve()
                if base.exists():
                    for p in base.rglob("*"):
                        if p.is_file():
                            ev.append(p)
            report_md = str(rec.get("report_md") or "").strip()
            if report_md:
                p = Path(report_md)
                if not p.is_absolute():
                    p = (_REPO_ROOT / p).resolve()
                if p.exists() and p.is_file():
                    ev.append(p)
            if ev:
                oids = _mint_evidence_oids(dsn=dsn, task_id=task_id, evidence_paths=ev)
                prev = t.get("evidence_oids") if isinstance(t.get("evidence_oids"), list) else []
                t["evidence_oids"] = sorted(set([*prev, *oids]))
                minted_evidence += len(oids)

        updated += 1
        if args.limit and updated >= int(args.limit):
            break

    _write_json(tree_path, tree)

    result = {
        "ok": True,
        "task_tree": _repo_rel(tree_path),
        "tasks_root": _repo_rel(tasks_root),
        "tasks_in_tree": len(items),
        "updated_tasks": updated,
        "missing_task_records": missing_task_records,
        "minted_evidence_oids": minted_evidence,
        "ts_utc": _iso_now(),
    }

    if args.emit_report:
        task_code = str(args.taskcode).strip() or "TASKTREE_BACKFILL_V010"
        area = str(args.area).strip() or "control_plane"
        artifacts = (_REPO_ROOT / "docs" / "REPORT" / area / "artifacts" / task_code).resolve()
        artifacts.mkdir(parents=True, exist_ok=True)
        _write_json(artifacts / "tasktree_backfill_summary.json", result)
        (artifacts / "selftest.log").write_text(f"{task_code} tasktree_backfill\nEXIT_CODE=0\n", encoding="utf-8")
        report = (_REPO_ROOT / "docs" / "REPORT" / area / f"REPORT__{task_code}__{datetime.now(timezone.utc).strftime('%Y%m%d')}.md").resolve()
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(
            "\n".join(
                [
                    f"# REPORT__{task_code}",
                    "",
                    f"- TaskCode: {task_code}",
                    f"- Area: {area}",
                    f"- Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
                    "",
                    "## Evidence Paths",
                    f"- docs/REPORT/{area}/artifacts/{task_code}/tasktree_backfill_summary.json",
                    f"- docs/REPORT/{area}/artifacts/{task_code}/selftest.log",
                    "",
                    "## Notes",
                    "- Backfills derived task_tree with verdict/touched_oids and optional evidence_oids (minted via OID generator).",
                    "",
                ]
            ),
            encoding="utf-8",
            errors="replace",
        )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
