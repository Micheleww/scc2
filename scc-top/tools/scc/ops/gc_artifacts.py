from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    return here.parents[3]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_resolve(p: Path) -> Path:
    try:
        return p.resolve()
    except Exception:
        return Path(os.path.abspath(str(p)))


def _is_within(child: Path, parent: Path) -> bool:
    child_r = _safe_resolve(child)
    parent_r = _safe_resolve(parent)
    try:
        child_r.relative_to(parent_r)
        return True
    except Exception:
        return False


def _format_bytes(n: int) -> str:
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    v = float(n)
    for u in units:
        if v < 1024.0 or u == units[-1]:
            if u == "B":
                return f"{int(v)} {u}"
            return f"{v:.2f} {u}"
        v /= 1024.0
    return f"{n} B"


def _walk_size(path: Path, max_files: int | None = None) -> tuple[int, int]:
    total = 0
    files = 0
    if path.is_file():
        try:
            return int(path.stat().st_size), 1
        except Exception:
            return 0, 0
    if not path.exists():
        return 0, 0
    for root, _dirs, filenames in os.walk(path):
        for name in filenames:
            if max_files is not None and files >= max_files:
                return total, files
            fp = Path(root) / name
            try:
                total += int(fp.stat().st_size)
                files += 1
            except Exception:
                continue
    return total, files


@dataclass(frozen=True)
class Item:
    path: Path
    mtime_utc: datetime
    kind: str  # "file" | "dir"


def _iter_children_as_items(base: Path) -> list[Item]:
    items: list[Item] = []
    if not base.exists():
        return items
    for p in base.iterdir():
        try:
            st = p.stat()
            mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
        except Exception:
            mtime = datetime.fromtimestamp(0, tz=timezone.utc)
        items.append(Item(path=p, mtime_utc=mtime, kind="dir" if p.is_dir() else "file"))
    items.sort(key=lambda x: x.mtime_utc, reverse=True)
    return items


def _pick_deletions(items: list[Item], cutoff: datetime, keep_last: int) -> list[Item]:
    keep: set[Path] = set()
    for it in items[: max(0, keep_last)]:
        keep.add(it.path)
    deletions: list[Item] = []
    for it in items:
        if it.path in keep:
            continue
        if it.mtime_utc >= cutoff:
            continue
        deletions.append(it)
    return deletions


def _rm_tree(p: Path) -> None:
    if p.is_dir() and not p.is_symlink():
        shutil.rmtree(p, ignore_errors=False)
    else:
        p.unlink(missing_ok=True)


def _ensure_parent_dir(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)


def _write_report(report_json: Path, report_md: Path, payload: dict[str, Any]) -> None:
    _ensure_parent_dir(report_json)
    _ensure_parent_dir(report_md)
    report_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines: list[str] = []
    lines.append(f"# Artifacts GC ({payload['ts']})")
    lines.append("")
    lines.append(f"- apply: `{payload['apply']}`")
    lines.append(f"- days: `{payload['days']}`")
    lines.append(f"- keep_last: `{payload['keep_last']}`")
    lines.append(f"- total_candidates: `{payload['total_candidates']}`")
    lines.append(f"- total_planned_delete: `{payload['total_planned_delete']}`")
    lines.append(f"- total_deleted: `{payload['total_deleted']}`")
    lines.append(f"- approx_freed_bytes: `{payload['approx_freed_bytes']}` ({_format_bytes(int(payload['approx_freed_bytes']))})")
    lines.append("")
    for target in payload["targets"]:
        lines.append(f"## {target['name']}")
        lines.append(f"- base: `{target['base']}`")
        lines.append(f"- exists: `{target['exists']}`")
        lines.append(f"- candidates: `{target['candidates']}`")
        lines.append(f"- planned_delete: `{target['planned_delete']}`")
        lines.append("")
        if target["planned"]:
            lines.append("| mtime_utc | kind | approx_size | path |")
            lines.append("|---|---:|---:|---|")
            for row in target["planned"][:200]:
                lines.append(
                    f"| {row['mtime_utc']} | {row['kind']} | {row['approx_size_h']} | `{row['path_rel']}` |"
                )
            if len(target["planned"]) > 200:
                lines.append("")
                lines.append(f"_truncated: showing 200/{len(target['planned'])}_")
        else:
            lines.append("_no deletions planned_")
        lines.append("")
    report_md.write_text("\n".join(lines), encoding="utf-8")


def _make_target(name: str, base: Path) -> dict[str, Any]:
    return {"name": name, "base": str(base).replace("\\", "/"), "exists": base.exists()}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="GC artifacts (quarantine/root_clutter/reports) with retention policy.")
    ap.add_argument("--days", type=int, default=21, help="Retain items newer than N days (default: 21).")
    ap.add_argument("--keep-last", type=int, default=10, help="Always keep last N items per target (default: 10).")
    ap.add_argument("--apply", action="store_true", help="Actually delete files/directories (default: dry-run).")
    ap.add_argument(
        "--size-scan-max-files",
        type=int,
        default=4000,
        help="Cap file counting for size estimation per item (default: 4000).",
    )
    ap.add_argument(
        "--targets",
        type=str,
        default="quarantine,root_clutter,reports",
        help="Comma-separated targets: quarantine,root_clutter,reports (default: all).",
    )
    args = ap.parse_args(argv)

    root = _repo_root()
    artifacts = root / "artifacts"
    allowed_bases = {
        "quarantine": artifacts / "_observatory_quarantine",
        "root_clutter": artifacts / "_root_clutter",
        "reports": artifacts / "scc_state" / "reports",
    }
    selected = [t.strip() for t in str(args.targets).split(",") if t.strip()]
    for t in selected:
        if t not in allowed_bases:
            raise SystemExit(f"unknown target: {t}")

    now = _utc_now()
    cutoff = now - timedelta(days=int(args.days))
    ts = now.strftime("%Y%m%d_%H%M%S")
    out_dir = artifacts / "scc_state" / "reports"
    report_json = out_dir / f"gc_artifacts_{ts}.json"
    report_md = out_dir / f"gc_artifacts_{ts}.md"

    payload: dict[str, Any] = {
        "ts": ts,
        "apply": bool(args.apply),
        "days": int(args.days),
        "keep_last": int(args.keep_last),
        "cutoff_utc": cutoff.isoformat(),
        "targets": [],
        "total_candidates": 0,
        "total_planned_delete": 0,
        "total_deleted": 0,
        "approx_freed_bytes": 0,
    }

    for name in selected:
        base = allowed_bases[name]
        target = _make_target(name, base)
        if not target["exists"]:
            target.update({"candidates": 0, "planned_delete": 0, "deleted": 0, "planned": []})
            payload["targets"].append(target)
            continue

        if name == "reports":
            # Treat each file as item (avoid deleting folders inside reports unless explicitly asked later).
            items: list[Item] = []
            for p in base.iterdir():
                if p.is_dir():
                    continue
                try:
                    st = p.stat()
                    mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
                except Exception:
                    mtime = datetime.fromtimestamp(0, tz=timezone.utc)
                items.append(Item(path=p, mtime_utc=mtime, kind="file"))
            items.sort(key=lambda x: x.mtime_utc, reverse=True)
        else:
            items = _iter_children_as_items(base)

        deletions = _pick_deletions(items, cutoff=cutoff, keep_last=int(args.keep_last))
        planned_rows: list[dict[str, Any]] = []

        deleted = 0
        approx_bytes = 0
        for it in deletions:
            if not _is_within(it.path, artifacts):
                continue
            size_bytes, _files = _walk_size(it.path, max_files=int(args.size_scan_max_files))
            approx_bytes += size_bytes
            planned_rows.append(
                {
                    "mtime_utc": it.mtime_utc.isoformat(),
                    "kind": it.kind,
                    "approx_size_bytes": size_bytes,
                    "approx_size_h": _format_bytes(size_bytes),
                    "path_rel": str(it.path.relative_to(root)).replace("\\", "/"),
                }
            )
            if args.apply:
                try:
                    _rm_tree(it.path)
                    deleted += 1
                except Exception:
                    continue

        target.update(
            {
                "candidates": len(items),
                "planned_delete": len(deletions),
                "deleted": deleted,
                "planned": planned_rows,
                "approx_freed_bytes": approx_bytes if args.apply else approx_bytes,
            }
        )
        payload["targets"].append(target)
        payload["total_candidates"] += len(items)
        payload["total_planned_delete"] += len(deletions)
        payload["total_deleted"] += deleted
        payload["approx_freed_bytes"] += approx_bytes

    _write_report(report_json=report_json, report_md=report_md, payload=payload)
    print(f"[gc_artifacts] apply={payload['apply']} days={payload['days']} keep_last={payload['keep_last']}")
    print(f"[gc_artifacts] planned_delete={payload['total_planned_delete']} deleted={payload['total_deleted']}")
    print(f"[gc_artifacts] report_md={report_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
