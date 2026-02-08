from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tools.scc.runtime_config import load_runtime_config


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", errors="replace")
    os.replace(tmp, path)


def _is_manifest_active(manifest: Dict[str, Any]) -> bool:
    parents = manifest.get("parents")
    if isinstance(parents, list) and parents:
        for p in parents:
            if isinstance(p, dict) and not p.get("end"):
                return True
    return not bool(manifest.get("end"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=str(_repo_root()))
    ap.add_argument("--abandon-after-s", type=int, default=0)
    args = ap.parse_args()

    repo_root = Path(args.repo_root).resolve()
    rt = load_runtime_config(repo_root=repo_root)
    abandon_after_s = int(args.abandon_after_s or rt.executor_abandon_active_run_after_s or 21600)

    state_dir = (repo_root / "artifacts" / "codexcli_remote_runs" / "_state").resolve()
    active_runs_file = (state_dir / "active_runs.json").resolve()
    data = _read_json(active_runs_file)
    if not isinstance(data, dict):
        print(f"[prune] active_runs file missing/invalid: {active_runs_file}")
        return 0
    runs = data.get("runs")
    if not isinstance(runs, dict):
        print(f"[prune] no runs dict in: {active_runs_file}")
        return 0

    now = datetime.now(timezone.utc)
    pruned = 0
    kept: Dict[str, Any] = {}
    for rid, entry in runs.items():
        if not isinstance(entry, dict):
            pruned += 1
            continue
        mp = entry.get("manifest_file")
        if not mp:
            pruned += 1
            continue
        manifest_path = Path(str(mp))
        manifest = _read_json(manifest_path)
        if not isinstance(manifest, dict):
            pruned += 1
            continue
        is_active = _is_manifest_active(manifest)
        if not is_active:
            pruned += 1
            continue
        try:
            updated_utc = entry.get("updated_utc")
            updated_dt = datetime.fromisoformat(str(updated_utc)) if updated_utc else None
        except Exception:
            updated_dt = None
        if updated_dt is not None:
            try:
                age_s = (now - updated_dt.astimezone(timezone.utc)).total_seconds()
                if age_s > float(abandon_after_s):
                    pruned += 1
                    continue
            except Exception:
                pass
        kept[str(rid)] = entry

    data["runs"] = kept
    _atomic_write_json(active_runs_file, data)
    print(f"[prune] active_runs_file={active_runs_file}")
    print(f"[prune] abandon_after_s={abandon_after_s}")
    print(f"[prune] pruned={pruned} kept={len(kept)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
