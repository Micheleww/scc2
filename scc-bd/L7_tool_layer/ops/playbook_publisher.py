#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from tools.scc.lib.utils import load_json


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: pathlib.Path, obj: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def publish_draft(draft_path: pathlib.Path, rollout_percent: int = 10) -> pathlib.Path:
    obj = _load_json(draft_path)
    if not isinstance(obj, dict) or obj.get("schema_version") != "scc.playbook.v1":
        raise ValueError("not a scc.playbook.v1")
    en = obj.get("enablement")
    if not isinstance(en, dict) or en.get("schema_version") != "scc.enablement.v1":
        raise ValueError("enablement invalid")

    # Promote draft -> gray with percent rollout.
    en["status"] = "gray"
    en["rollout"] = {"mode": "percent", "percent": int(max(0, min(100, rollout_percent)))}
    obj["enablement"] = en

    lifecycle = obj.get("lifecycle") if isinstance(obj.get("lifecycle"), dict) else {}
    lifecycle["stage"] = "active"
    lifecycle["updated_at"] = _now_iso()
    obj["lifecycle"] = lifecycle

    out = (REPO_ROOT / "playbooks" / draft_path.name).resolve()
    _write_json(out, obj)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Promote playbook drafts to active playbooks (MVP publisher).")
    ap.add_argument("--draft", required=True, help="Draft playbook path under playbooks/drafts/")
    ap.add_argument("--rollout", type=int, default=10, help="Percent rollout for gray mode")
    ap.add_argument("--skip-eval", action="store_true", help="Skip eval gate (unsafe)")
    ap.add_argument("--force", action="store_true", help="Force publish even if eval fails (unsafe)")
    args = ap.parse_args()

    draft = (REPO_ROOT / str(args.draft)).resolve()
    if not draft.exists():
        print(f"FAIL: missing draft {draft}")
        return 2
    if "playbooks" not in str(draft).replace("\\", "/") or "/drafts/" not in str(draft).replace("\\", "/"):
        print("FAIL: draft must be under playbooks/drafts/")
        return 2

    # Gate publish on eval (fail-closed by default).
    if not args.skip_eval:
        try:
            import subprocess

            r = subprocess.run(
                [
                    "python",
                    "tools/scc/ops/eval_replay.py",
                    "--drafts",
                    "playbooks/drafts",
                    "--draft",
                    str(draft.relative_to(REPO_ROOT)).replace("\\", "/"),
                    "--samples-per-playbook",
                    "0",
                    "--require-sample-set",
                ],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=300,
            )
            if r.returncode != 0 and not args.force:
                print("FAIL: eval_replay did not PASS; use --force or --skip-eval to override")
                if r.stdout:
                    print(r.stdout.strip()[-2000:])
                if r.stderr:
                    print(r.stderr.strip()[-2000:])
                return 1
        except Exception as e:
            if not args.force and not args.skip_eval:
                print(f"FAIL: eval_replay execution failed: {e}")
                return 1

    out = publish_draft(draft, rollout_percent=int(args.rollout))
    changelog = REPO_ROOT / "playbooks" / "changelog.jsonl"
    changelog.parent.mkdir(parents=True, exist_ok=True)
    changelog.write_text("", encoding="utf-8") if not changelog.exists() else None
    with changelog.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "t": _now_iso(),
                    "type": "playbook_published",
                    "draft": str(draft.relative_to(REPO_ROOT)).replace("\\", "/"),
                    "out": str(out.relative_to(REPO_ROOT)).replace("\\", "/"),
                    "rollout": int(args.rollout),
                },
                ensure_ascii=False,
            )
            + "\n"
        )

    # Best-effort: update playbooks/registry.json deterministically.
    try:
        import subprocess

        subprocess.run(
            ["python", "tools/scc/ops/playbooks_registry_sync.py"],
            cwd=str(REPO_ROOT),
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass
    print("OK")
    print(str(out.relative_to(REPO_ROOT)).replace("\\", "/"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
