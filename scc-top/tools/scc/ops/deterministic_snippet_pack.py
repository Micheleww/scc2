#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Tuple


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_repo_path(p: str) -> str:
    return (p or "").replace("\\", "/").lstrip("/").strip()


def _match_any(path: str, patterns: List[str]) -> bool:
    import fnmatch

    path = _normalize_repo_path(path)
    for pat in patterns:
        pat = _normalize_repo_path(pat)
        if not pat:
            continue
        if pat.endswith("/") and path.startswith(pat):
            return True
        if fnmatch.fnmatchcase(path, pat):
            return True
    return False


def _read_text_best_effort(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        try:
            return path.read_text()
        except Exception:
            return ""


def _truncate_text(s: str, *, max_chars: int) -> Tuple[str, bool]:
    s = s or ""
    if max_chars <= 0 or len(s) <= max_chars:
        return s, False
    head = s[: max_chars // 2]
    tail = s[-(max_chars - len(head)) :]
    # Avoid inserting markers that could be mistaken as literal file content.
    return head + "\n\n<<<TRUNCATED>>>\n\n" + tail, True


def _extract_keywords(text: str, *, max_keywords: int = 10) -> List[str]:
    text = (text or "").lower()
    toks = re.findall(r"[a-z0-9_./-]{4,}", text)
    stop = {
        "task",
        "goal",
        "allowed",
        "changes",
        "update",
        "create",
        "docs",
        "tools",
        "file",
        "files",
        "must",
        "should",
        "with",
        "from",
        "into",
        "this",
        "that",
        "true",
        "false",
        "json",
        "yaml",
        "python",
        "powershell",
    }
    out: List[str] = []
    seen = set()
    for t in toks:
        if t in stop or t.startswith("http") or t in seen:
            continue
        seen.add(t)
        out.append(t)
        if len(out) >= max_keywords:
            break
    return out


def _iter_files(repo_root: Path) -> Iterable[str]:
    for p in repo_root.rglob("*"):
        try:
            if not p.is_file():
                continue
        except Exception:
            continue
        try:
            rel = _normalize_repo_path(str(p.relative_to(repo_root)))
        except Exception:
            continue
        if rel and not rel.startswith(".git/"):
            yield rel


def _pick_files(repo_root: Path, allowed_globs: List[str], embed_paths: Optional[List[str]], max_files: int) -> List[str]:
    if embed_paths:
        out = []
        for p in embed_paths:
            rp = _normalize_repo_path(p)
            if rp and _match_any(rp, allowed_globs):
                out.append(rp)
        return out[:max_files]

    prefer_ext = (".md", ".py", ".json", ".ps1")
    picked: List[str] = []
    for rel in _iter_files(repo_root):
        if not _match_any(rel, allowed_globs):
            continue
        if rel.endswith(prefer_ext):
            picked.append(rel)
            if len(picked) >= max_files:
                break
    if len(picked) < max_files:
        for rel in _iter_files(repo_root):
            if not _match_any(rel, allowed_globs):
                continue
            if rel in picked:
                continue
            picked.append(rel)
            if len(picked) >= max_files:
                break
    return picked


def _rg_hits(repo_root: Path, rel_path: str, keywords: List[str], context_lines: int, max_chars: int) -> List[str]:
    if not keywords:
        return []
    if shutil.which("rg") is None:
        return []
    hits: List[str] = []
    for kw in keywords:
        try:
            p = subprocess.run(
                ["rg", "-n", "-C", str(context_lines), kw, rel_path],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=8,
            )
            if p.returncode == 0 and (p.stdout or "").strip():
                s, _ = _truncate_text(p.stdout, max_chars=max_chars)
                hits.append(f"rg: {kw}\n{s}".strip())
        except Exception:
            continue
        if len(hits) >= 6:
            break
    return hits


@dataclass
class PackConfig:
    max_files: int
    head_lines: int
    tail_lines: int
    context_lines: int
    max_total_chars: int
    max_file_chars: int


def build_pack(
    *,
    repo_root: Path,
    allowed_globs: List[str],
    task_text: str,
    embed_paths: Optional[List[str]],
    cfg: PackConfig,
) -> str:
    files = _pick_files(repo_root, allowed_globs, embed_paths, cfg.max_files)
    keywords = _extract_keywords(task_text)

    parts: List[str] = []
    parts.append("Context snippets (deterministic; read-only):")
    parts.append(f"- generated_utc: { _utc_now() }")
    parts.append(f"- files: {len(files)}")
    parts.append(f"- keywords: {keywords}")

    total = 0
    for rel in files:
        p = (repo_root / rel).resolve()
        raw = _read_text_best_effort(p)
        lines = raw.splitlines()
        head = "\n".join(lines[: cfg.head_lines])
        tail = "\n".join(lines[-cfg.tail_lines :]) if len(lines) > cfg.head_lines else ""
        hits = _rg_hits(repo_root, rel, keywords, cfg.context_lines, max_chars=2000)
        # IMPORTANT: Keep markers OUTSIDE code fences so agents don't copy them into patches.
        section_parts: List[str] = [f"\nFILE: {rel}"]
        if head.strip():
            head0, _ = _truncate_text(head, max_chars=max(200, cfg.max_file_chars // 2))
            section_parts.append("HEAD:")
            section_parts.append(f"```text\n{head0}\n```")
        if hits:
            hits0 = "\n\n".join(hits).strip()
            hits0, _ = _truncate_text(hits0, max_chars=max(200, cfg.max_file_chars // 2))
            section_parts.append("RG_HITS:")
            section_parts.append(f"```text\n{hits0}\n```")
        if tail.strip():
            tail0, _ = _truncate_text(tail, max_chars=max(200, cfg.max_file_chars // 2))
            section_parts.append("TAIL:")
            section_parts.append(f"```text\n{tail0}\n```")

        chunk = "\n".join(section_parts).strip()
        if total + len(chunk) > cfg.max_total_chars:
            break
        parts.append(chunk)
        total += len(chunk)

    out = "\n".join(parts).strip() + "\n"
    out, _ = _truncate_text(out, max_chars=cfg.max_total_chars)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Deterministic snippet pack generator (low-token context).")
    ap.add_argument("--repo-root", default=str(_repo_root()))
    ap.add_argument("--allowed-glob", action="append", default=[], help="Repeatable allowlist glob (repo-relative).")
    ap.add_argument("--task-text", default="", help="Task/description text used to extract keywords.")
    ap.add_argument("--embed-path", action="append", default=[], help="Optional preferred file paths (repo-relative).")
    ap.add_argument("--out", default="", help="Output path (default: artifacts/scc_state/snippet_packs/...)")
    ap.add_argument("--max-files", type=int, default=4)
    ap.add_argument("--head-lines", type=int, default=80)
    ap.add_argument("--tail-lines", type=int, default=40)
    ap.add_argument("--context-lines", type=int, default=2)
    ap.add_argument("--max-total-chars", type=int, default=45000)
    ap.add_argument("--max-file-chars", type=int, default=12000)
    ap.add_argument("--json", action="store_true", help="Also write a .json sidecar with metadata.")
    args = ap.parse_args()

    repo_root = Path(args.repo_root).resolve()
    allowed = [_normalize_repo_path(x) for x in (args.allowed_glob or []) if _normalize_repo_path(x)]
    if not allowed:
        print("ERR: at least one --allowed-glob is required", flush=True)
        return 2

    embed_paths = [_normalize_repo_path(x) for x in (args.embed_path or []) if _normalize_repo_path(x)] or None
    cfg = PackConfig(
        max_files=max(1, int(args.max_files)),
        head_lines=max(10, int(args.head_lines)),
        tail_lines=max(0, int(args.tail_lines)),
        context_lines=max(0, int(args.context_lines)),
        max_total_chars=max(1000, int(args.max_total_chars)),
        max_file_chars=max(500, int(args.max_file_chars)),
    )

    pack = build_pack(repo_root=repo_root, allowed_globs=allowed, task_text=str(args.task_text or ""), embed_paths=embed_paths, cfg=cfg)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")
    out_path = Path(args.out).resolve() if args.out.strip() else (repo_root / "artifacts" / "scc_state" / "snippet_packs" / f"snippet_pack__{stamp}.md").resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(pack, encoding="utf-8", errors="replace")
    print(str(out_path), flush=True)

    if args.json:
        meta = {
            "generated_utc": _utc_now(),
            "repo_root": str(repo_root),
            "allowed_globs": allowed,
            "embed_paths": embed_paths or [],
            "config": cfg.__dict__,
        }
        out_path.with_suffix(out_path.suffix + ".json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
