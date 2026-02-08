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


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", errors="replace")
    os.replace(tmp, path)


def _parse_porcelain(lines: List[str]) -> Tuple[List[str], List[str]]:
    tracked_changes: List[str] = []
    untracked: List[str] = []
    for ln in lines:
        if not ln:
            continue
        if ln.startswith("?? "):
            untracked.append(_decode_git_path(ln[3:].strip()))
        else:
            # e.g. " M file" / "D  file"
            tracked_changes.append(_decode_git_path(ln[3:].strip() if len(ln) > 3 else ln.strip()))
    return tracked_changes, untracked


def _decode_git_path(s: str) -> str:
    """
    Decode git status porcelain path quoting:
    - Unquoted paths are returned as-is.
    - Quoted paths use C-style quoting with backslash escapes + octal sequences.
    """
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
            # Backslash escape
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
            # Octal escape: \123
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
            # Unknown escape, keep literally
            out_bytes.extend(("\\" + esc).encode("utf-8", errors="replace"))
            i += 1
        try:
            return out_bytes.decode("utf-8", errors="replace")
        except Exception:
            return inner
    return s


def _top_level_bucket(path: str) -> str:
    p = path.replace("\\", "/").strip().strip("/")
    if not p:
        return ""
    return p.split("/", 1)[0]


def _ext_bucket(path: str) -> str:
    p = path.replace("\\", "/").strip()
    name = p.rsplit("/", 1)[-1]
    if "." not in name:
        return "(no_ext)"
    return "." + name.rsplit(".", 1)[-1].lower()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=str(_repo_root()))
    ap.add_argument("--limit", type=int, default=30)
    args = ap.parse_args()

    repo_root = Path(args.repo_root).resolve()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = (repo_root / "artifacts" / "scc_state" / "reports").resolve()
    out_json = (out_dir / f"git_noise_audit_{ts}.json").resolve()
    out_md = (out_dir / f"git_noise_audit_{ts}.md").resolve()

    try:
        r = subprocess.run(
            ["git", "status", "--porcelain=v1", "-uall"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        raw = (r.stdout or "").splitlines()
    except Exception as e:
        payload = {
            "schema_version": "scc_git_noise_audit.v0",
            "repo_root": str(repo_root),
            "ts_utc": _utc_now(),
            "error": str(e),
        }
        _atomic_write_json(out_json, payload)
        _atomic_write_text(out_md, f"# Git Noise Audit ({ts})\n\nERROR: {e}\n")
        print(f"[git_noise_audit] error={e}")
        return 1

    tracked_changes, untracked = _parse_porcelain(raw)
    top = Counter(_top_level_bucket(p) for p in untracked)
    ext = Counter(_ext_bucket(p) for p in untracked)
    lim = max(5, min(int(args.limit), 200))

    payload: Dict[str, Any] = {
        "schema_version": "scc_git_noise_audit.v0",
        "repo_root": str(repo_root),
        "ts_utc": _utc_now(),
        "tracked_changes_count": len(tracked_changes),
        "untracked_count": len(untracked),
        "untracked_top_level": top.most_common(lim),
        "untracked_extensions": ext.most_common(lim),
    }
    _atomic_write_json(out_json, payload)

    lines = []
    lines.append(f"# Git Noise Audit ({ts})")
    lines.append("")
    lines.append(f"- tracked_changes_count: `{payload['tracked_changes_count']}`")
    lines.append(f"- untracked_count: `{payload['untracked_count']}`")
    lines.append(f"- json_report: `{str(out_json.relative_to(repo_root))}`")
    lines.append("")
    lines.append("## Untracked Top-Level")
    for k, v in payload["untracked_top_level"]:
        lines.append(f"- `{k}`: `{v}`")
    lines.append("")
    lines.append("## Untracked Extensions")
    for k, v in payload["untracked_extensions"]:
        lines.append(f"- `{k}`: `{v}`")
    lines.append("")
    _atomic_write_text(out_md, "\n".join(lines) + "\n")

    print(f"[git_noise_audit] tracked_changes={len(tracked_changes)} untracked={len(untracked)}")
    print(f"[git_noise_audit] report_md={str(out_md.relative_to(repo_root))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
