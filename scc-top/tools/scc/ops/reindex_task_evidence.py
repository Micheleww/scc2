from __future__ import annotations

import argparse
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tools.scc.evidence_index import build_task_evidence_index


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=str(_repo_root()))
    ap.add_argument("--task-id", default="")
    ap.add_argument("--limit", type=int, default=200)
    args = ap.parse_args()

    repo_root = Path(args.repo_root).resolve()
    tasks_root = (repo_root / "artifacts" / "scc_tasks").resolve()

    task_id = str(args.task_id or "").strip()
    if task_id:
        out = build_task_evidence_index(repo_root=repo_root, task_id=task_id)
        print(out.get("paths", {}).get("task_json", {}).get("path", ""))
        return 0

    if not tasks_root.exists():
        print(f"[reindex] tasks_root not found: {tasks_root}")
        return 0

    dirs = [p for p in tasks_root.iterdir() if p.is_dir()]
    dirs.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    lim = max(1, min(int(args.limit), 5000))
    ok = 0
    err = 0
    for d in dirs[:lim]:
        tid = d.name
        try:
            build_task_evidence_index(repo_root=repo_root, task_id=tid)
            ok += 1
        except Exception:
            err += 1
    print(f"[reindex] repo_root={repo_root}")
    print(f"[reindex] tasks_scanned={min(lim, len(dirs))} ok={ok} err={err}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
