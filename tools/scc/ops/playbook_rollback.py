#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from tools.scc.lib.utils import load_json


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: pathlib.Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _op_ok(op: str, value: float, threshold: float) -> bool:
    if op == ">":
        return value > threshold
    if op == ">=":
        return value >= threshold
    if op == "<":
        return value < threshold
    if op == "<=":
        return value <= threshold
    return False


def _read_playbooks(playbooks_dir: pathlib.Path) -> List[Tuple[pathlib.Path, Dict[str, Any]]]:
    out: List[Tuple[pathlib.Path, Dict[str, Any]]] = []
    if not playbooks_dir.exists():
        return out
    for p in sorted(playbooks_dir.glob("*.json"))[:400]:
        if p.name in {"overrides.json"}:
            continue
        try:
            obj = _load_json(p)
        except Exception:
            continue
        if isinstance(obj, dict) and obj.get("schema_version") == "scc.playbook.v1":
            out.append((p, obj))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Auto-rollback playbooks based on metrics rollback_conditions (MVP).")
    ap.add_argument("--metrics", default="metrics/latest.json")
    ap.add_argument("--overrides", default="playbooks/overrides.json")
    args = ap.parse_args()

    metrics_path = (REPO_ROOT / str(args.metrics)).resolve()
    if not metrics_path.exists():
        print(f"FAIL: missing metrics file {metrics_path}")
        return 2
    metrics = _load_json(metrics_path)
    latest = metrics.get("latest_bucket") if isinstance(metrics, dict) else None
    latest = latest if isinstance(latest, dict) else {}

    overrides_path = (REPO_ROOT / str(args.overrides)).resolve()
    existing: Dict[str, Any] = {}
    if overrides_path.exists():
        try:
            existing = _load_json(overrides_path)
        except Exception:
            existing = {}

    next_overrides: Dict[str, Any] = {
        "schema_version": "scc.playbook_overrides.v1",
        "updated_at": _now_iso(),
        "overrides": {},
    }
    if isinstance(existing, dict) and isinstance(existing.get("overrides"), dict):
        next_overrides["overrides"] = dict(existing["overrides"])

    rolled_back: List[Dict[str, Any]] = []
    playbooks_dir = (REPO_ROOT / "playbooks").resolve()
    for p, pb in _read_playbooks(playbooks_dir):
        en = pb.get("enablement")
        if not isinstance(en, dict) or en.get("schema_version") != "scc.enablement.v1":
            continue
        rcs = en.get("rollback_conditions")
        if not isinstance(rcs, list) or not rcs:
            continue
        pbid = str(pb.get("playbook_id") or "")
        if not pbid:
            continue

        for rc in rcs[:20]:
            if not isinstance(rc, dict):
                continue
            metric = str(rc.get("metric") or "").strip()
            op = str(rc.get("op") or "").strip()
            thr = rc.get("threshold")
            if not metric or not op or not isinstance(thr, (int, float)):
                continue
            val = latest.get(metric)
            if not isinstance(val, (int, float)):
                continue
            if _op_ok(op, float(val), float(thr)):
                next_overrides["overrides"][pbid] = {
                    "disabled": True,
                    "reason": "rollback_condition_triggered",
                    "t": _now_iso(),
                    "metric": metric,
                    "op": op,
                    "threshold": float(thr),
                    "value": float(val),
                    "source_playbook": str(p.relative_to(REPO_ROOT)).replace("\\", "/"),
                }
                rolled_back.append({"playbook_id": pbid, "metric": metric, "value": float(val), "threshold": float(thr), "op": op})
                break

    _write_json(overrides_path, next_overrides)
    if rolled_back:
        changelog = REPO_ROOT / "playbooks" / "changelog.jsonl"
        changelog.parent.mkdir(parents=True, exist_ok=True)
        with changelog.open("a", encoding="utf-8") as f:
            for r in rolled_back:
                f.write(json.dumps({"t": _now_iso(), "type": "playbook_rolled_back", **r}, ensure_ascii=False) + "\n")
    print("OK")
    print(json.dumps({"rolled_back": rolled_back}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

