from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=str(_repo_root()))
    ap.add_argument("--mode", choices=["copy", "move"], default="copy")
    args = ap.parse_args()

    repo_root = Path(args.repo_root).resolve()
    legacy = (repo_root / "evidence" / "permission_decisions").resolve()
    target = (repo_root / "artifacts" / "scc_state" / "evidence" / "permission_decisions").resolve()
    target.mkdir(parents=True, exist_ok=True)
    queue_target = (repo_root / "artifacts" / "scc_state" / "approval_queue").resolve()
    queue_target.mkdir(parents=True, exist_ok=True)

    if not legacy.exists():
        print(f"[migrate] legacy dir not found: {legacy}")
        return 0

    moved = 0
    copied = 0
    for p in sorted(legacy.glob("*.json")):
        out = (target / p.name).resolve()
        if out.exists():
            continue
        if args.mode == "move":
            p.replace(out)
            moved += 1
        else:
            shutil.copy2(p, out)
            copied += 1

    # queue.json is special (it might be updated); only copy if missing.
    legacy_q = (legacy / "queue.json").resolve()
    target_q_old = (target / "queue.json").resolve()
    target_q_new = (queue_target / "permission_pdp_queue.json").resolve()
    if legacy_q.exists():
        if not target_q_old.exists() and args.mode != "move":
            # Keep backward-compat copy in the old location (evidence), if missing.
            try:
                shutil.copy2(legacy_q, target_q_old)
            except Exception:
                pass
        if not target_q_new.exists():
            if args.mode == "move":
                legacy_q.replace(target_q_new)
            else:
                shutil.copy2(legacy_q, target_q_new)

    print(f"[migrate] legacy={legacy}")
    print(f"[migrate] target={target}")
    print(f"[migrate] queue_target={queue_target}")
    print(f"[migrate] copied={copied} moved={moved} mode={args.mode}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
