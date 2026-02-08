from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import urllib.request
import urllib.error

BASE = "http://127.0.0.1:18788"
ROOT = Path(r"C:\scc\scc-top")
BOARD_JSON = ROOT / "docs" / "TASKS" / "backlog" / "parent_task_goal_board.json"
PARENTS_JSON = ROOT / "docs" / "TASKS" / "backlog" / "parent_tasks.json"
REPORT_DIR = ROOT / "docs" / "REPORT" / "control_plane"
REPORT_DIR.mkdir(parents=True, exist_ok=True)


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


def _load_json_lenient(path: Path) -> Any:
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        return json.loads(text)
    except Exception:
        # Attempt to trim trailing junk after the last JSON object/array
        last_obj = text.rfind("}")
        last_arr = text.rfind("]")
        cut = max(last_obj, last_arr)
        if cut > 0:
            try:
                return json.loads(text[: cut + 1])
            except Exception:
                pass
        raise


def _dump_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    if not BOARD_JSON.exists() or not PARENTS_JSON.exists():
        print("missing board or parents")
        return 2

    board = _load_json_lenient(BOARD_JSON)

    # Step 1: mark active goals with no evidence as needs_followup
    changed = 0
    for item in board.get("items", []):
        if item.get("status") == "active" and not (item.get("evidence") or []):
            item["status"] = "needs_followup"
            changed += 1

    board["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    _dump_json(BOARD_JSON, board)

    # Step 2: run goal review -> generate followup parents
    p = subprocess.run([sys.executable, "tools/scc/ops/parent_task_goal_review.py"], cwd=str(ROOT))

    # Step 3: detect newly added followup parents (by diff)
    parents = _load_json_lenient(PARENTS_JSON)
    followups = [x for x in parents if "FOLLOWUP__" in str(x.get("parent_task_id", ""))]

    # Step 4: create board parent tasks for followups
    created = []
    for parent in followups:
        title = parent.get("title") or f"Follow-up {parent.get('parent_task_id')}"
        goal = parent.get("goal") or "Follow-up goal"
        payload = {
            "kind": "parent",
            "title": title,
            "goal": goal,
            "status": "ready",
            "role": "designer",
            "allowedExecutors": ["codex"],
            "allowedModels": ["gpt-5.2"],
            "area": "control_plane",
        }
        code, body = _http("POST", f"{BASE}/board/tasks", payload)
        if 200 <= code < 300:
            try:
                created.append(json.loads(body))
            except Exception:
                created.append({"raw": body})

    # Step 5: one pump tick (split + apply + dispatch)
    code, body = _http("GET", f"{BASE}/board")
    try:
        board_snapshot = json.loads(body or "{}")
    except Exception:
        board_snapshot = {"raw": body}

    tasks = board_snapshot.get("tasks", []) if isinstance(board_snapshot.get("tasks"), list) else []
    parents_ready = [t for t in tasks if t.get("kind") == "parent" and t.get("status") in ("ready", "needs_split")]
    parents_inprog = [t for t in tasks if t.get("kind") == "parent" and t.get("status") == "in_progress"]
    for t in parents_inprog:
        _http("POST", f"{BASE}/board/tasks/{t.get('id')}/split/apply", {})
    for t in parents_ready:
        _http("POST", f"{BASE}/board/tasks/{t.get('id')}/split", {})

    code2, body2 = _http("GET", f"{BASE}/board")
    try:
        board_snapshot2 = json.loads(body2 or "{}")
    except Exception:
        board_snapshot2 = {"raw": body2}

    tasks2 = board_snapshot2.get("tasks", []) if isinstance(board_snapshot2.get("tasks"), list) else []
    atomic_ready = [t for t in tasks2 if t.get("kind") == "atomic" and t.get("status") in ("ready", "backlog")]
    for t in atomic_ready:
        _http("POST", f"{BASE}/board/tasks/{t.get('id')}/dispatch", {})

    # Step 6: write audit report
    now = datetime.now(timezone.utc)
    report_path = REPORT_DIR / f"REPORT__GOAL_CHAIN_RUN__{now.strftime('%Y%m%d-%H%M%SZ')}.md"
    lines = [
        f"# Goal Chain Run Report ({now.strftime('%Y-%m-%d')})",
        "",
        f"- Generated at (UTC): {now.isoformat()}",
        f"- Goals marked needs_followup: {changed}",
        f"- Followup parents created on board: {len(created)}",
        f"- parent_task_goal_board: {BOARD_JSON}",
        "",
        "## Created Board Parents",
    ]
    for c in created:
        lines.append(f"- {c.get('id')} | {c.get('title')}")
    lines += [
        "",
        "## Board Counts (post-dispatch)",
        json.dumps(board_snapshot2.get("counts", {}), ensure_ascii=False),
    ]
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("report", report_path)
    return 0 if p.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
