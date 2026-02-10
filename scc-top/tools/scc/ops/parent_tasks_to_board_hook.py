#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Parent Tasks -> Board Hook

Reads parent_tasks.json and ensures matching board parent tasks exist.
Optionally runs split/apply and dispatch for ready atomic tasks.

Design:
- deterministic, no network (except local board API)
- idempotent: uses pointers.parent_task_id to detect existing board tasks
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import urllib.request
import urllib.error


def _http(method: str, url: str, payload: Any | None = None, timeout_s: float = 10.0) -> Tuple[int, str]:
    data = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return int(getattr(resp, "status", 200)), body
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            body = str(e)
        return int(getattr(e, "code", 500)), body
    except Exception as e:
        return 0, str(e)


def _load_lenient_json_array(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end < start:
        return []
    return json.loads(text[start : end + 1])


def _extract_board_tasks(base: str) -> List[Dict[str, Any]]:
    code, body = _http("GET", f"{base}/board/tasks")
    if code < 200 or code >= 300:
        return []
    try:
        data = json.loads(body or "[]")
    except Exception:
        return []
    return data if isinstance(data, list) else []


def _has_parent_task(board_tasks: List[Dict[str, Any]], parent_task_id: str) -> bool:
    for t in board_tasks:
        pointers = t.get("pointers") or {}
        if isinstance(pointers, dict) and pointers.get("parent_task_id") == parent_task_id:
            return True
    return False


def main() -> int:
    default_repo_root = Path(__file__).resolve().parents[4]
    ap = argparse.ArgumentParser(description="Hook: sync parent_tasks -> board")
    ap.add_argument("--parents", default=os.environ.get("PARENTS_PATH") or str(default_repo_root / "scc-top" / "docs" / "TASKS" / "backlog" / "parent_tasks.json"))
    ap.add_argument("--base", default="http://127.0.0.1:18788")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--split", action="store_true")
    ap.add_argument("--dispatch", action="store_true")
    ap.add_argument("--max-new", type=int, default=50)
    ap.add_argument("--allowed-executors", action="append", default=[])
    ap.add_argument("--allowed-models", action="append", default=[])
    ap.add_argument("--area", default="control_plane")
    ap.add_argument("--runner", default="external")
    ap.add_argument("--role", default="designer")
    args = ap.parse_args()

    parents_path = Path(args.parents)
    if not parents_path.exists():
        raise SystemExit(f"Missing parents: {parents_path}")

    parents = _load_lenient_json_array(parents_path)
    board_tasks = _extract_board_tasks(args.base)

    created = 0
    for parent in parents:
        if created >= int(args.max_new):
            break
        parent_id = str(parent.get("parent_task_id") or "").strip()
        title = str(parent.get("title") or "").strip()
        goal = str(parent.get("goal") or "").strip()
        if not parent_id or not title or not goal:
            continue
        if _has_parent_task(board_tasks, parent_id):
            continue

        payload = {
            "kind": "parent",
            "title": title,
            "goal": goal,
            "status": "needs_split",
            "role": args.role,
            "allowedExecutors": args.allowed_executors or ["codex"],
            "allowedModels": args.allowed_models or ["gpt-5.2"],
            "area": args.area,
            "runner": "internal" if args.runner == "internal" else "external",
            "pointers": {"parent_task_id": parent_id, "parent_task_source": "parent_tasks.json"},
        }
        if not args.apply:
            created += 1
            continue
        code, body = _http("POST", f"{args.base}/board/tasks", payload)
        if 200 <= code < 300:
            created += 1

    if not args.apply:
        print(f"[hook] dry-run: would_create={created}")
        return 0

    # Refresh board tasks after creation
    board_tasks = _extract_board_tasks(args.base)

    if args.split:
        parents_ready = [t for t in board_tasks if t.get("kind") == "parent" and t.get("status") in ("ready", "needs_split")]
        parents_inprog = [t for t in board_tasks if t.get("kind") == "parent" and t.get("status") == "in_progress"]
        for t in parents_inprog:
            _http("POST", f"{args.base}/board/tasks/{t.get('id')}/split/apply", {})
        for t in parents_ready:
            _http("POST", f"{args.base}/board/tasks/{t.get('id')}/split", {})

    if args.dispatch:
        board_tasks = _extract_board_tasks(args.base)
        atomic_ready = [t for t in board_tasks if t.get("kind") == "atomic" and t.get("status") in ("ready", "backlog")]
        for t in atomic_ready:
            _http("POST", f"{args.base}/board/tasks/{t.get('id')}/dispatch", {})

    print(f"[hook] created={created} split={bool(args.split)} dispatch={bool(args.dispatch)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
