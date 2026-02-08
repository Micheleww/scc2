from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", errors="replace")
    os.replace(tmp, path)


def _top_level(path: str) -> str:
    p = path.replace("\\", "/").strip().strip("/")
    return p.split("/", 1)[0] if p else ""


def _ext(path: str) -> str:
    p = path.replace("\\", "/").strip()
    name = p.rsplit("/", 1)[-1]
    if "." not in name:
        return "(no_ext)"
    return "." + name.rsplit(".", 1)[-1].lower()


def _git_untracked(repo_root: Path) -> List[str]:
    r = subprocess.run(
        ["git", "status", "--porcelain=v1", "-uall"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    out: List[str] = []
    for ln in (r.stdout or "").splitlines():
        if ln.startswith("?? "):
            out.append(_decode_git_path(ln[3:].strip()))
    return out


def _decode_git_path(s: str) -> str:
    s = str(s or "").strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        inner = s[1:-1]
        out_bytes = bytearray()
        i = 0
        while i < len(inner):
            ch = inner[i]
            if ch != "\\":
                out_bytes.extend(ch.encode("utf-8", errors="replace"))
                i += 1
                continue
            i += 1
            if i >= len(inner):
                out_bytes.extend(b"\\")
                break
            esc = inner[i]
            if esc in {'\\', '"'}:
                out_bytes.extend(esc.encode("utf-8"))
                i += 1
                continue
            if esc == "n":
                out_bytes.extend(b"\n")
                i += 1
                continue
            if esc == "t":
                out_bytes.extend(b"\t")
                i += 1
                continue
            if esc == "r":
                out_bytes.extend(b"\r")
                i += 1
                continue
            if esc.isdigit():
                j = i
                digits = []
                while j < len(inner) and len(digits) < 3 and inner[j].isdigit():
                    digits.append(inner[j])
                    j += 1
                try:
                    out_bytes.append(int("".join(digits), 8) & 0xFF)
                except Exception:
                    out_bytes.extend(("\\ " + "".join(digits)).encode("utf-8", errors="replace"))
                i = j
                continue
            out_bytes.extend(("\\" + esc).encode("utf-8", errors="replace"))
            i += 1
        try:
            return out_bytes.decode("utf-8", errors="replace")
        except Exception:
            return inner
    return s


def _dir_size_bytes(path: Path, limit_files: int = 50_000) -> tuple[int, int]:
    """
    Best-effort size of a directory by sampling up to limit_files.
    Returns: (bytes, files_counted)
    """
    total = 0
    counted = 0
    try:
        for p in path.rglob("*"):
            if counted >= limit_files:
                break
            try:
                if p.is_file():
                    total += int(p.stat().st_size)
                    counted += 1
            except Exception:
                continue
    except Exception:
        pass
    return total, counted


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=str(_repo_root()))
    ap.add_argument("--top-k", type=int, default=50)
    ap.add_argument("--size-sample", action="store_true", help="Also estimate size of top-level dirs (sampled).")
    args = ap.parse_args()

    repo_root = Path(args.repo_root).resolve()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = (repo_root / "artifacts" / "scc_state" / "reports").resolve()
    out_json = (out_dir / f"untracked_inventory_{ts}.json").resolve()

    untracked = _git_untracked(repo_root)
    top = Counter(_top_level(p) for p in untracked)
    ext = Counter(_ext(p) for p in untracked)
    k = max(10, min(int(args.top_k), 500))

    top_level_details: List[Dict[str, Any]] = []
    for name, count in top.most_common(k):
        entry: Dict[str, Any] = {"name": name, "count": int(count)}
        if args.size_sample and name:
            p = (repo_root / name).resolve()
            if p.exists() and p.is_dir():
                size_b, files = _dir_size_bytes(p)
                entry["size_bytes_sampled"] = int(size_b)
                entry["files_counted_sampled"] = int(files)
        top_level_details.append(entry)

    payload: Dict[str, Any] = {
        "schema_version": "scc_untracked_inventory.v0",
        "repo_root": str(repo_root),
        "ts_utc": _utc_now(),
        "untracked_count": int(len(untracked)),
        "top_level": top_level_details,
        "extensions": [{"ext": k, "count": int(v)} for k, v in ext.most_common(k)],
    }
    _atomic_write_json(out_json, payload)
    print(f"[untracked_inventory] untracked={len(untracked)} top_k={k}")
    print(f"[untracked_inventory] report_json={str(out_json.relative_to(repo_root))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
