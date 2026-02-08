from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _format_bytes(n: int) -> str:
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    v = float(n)
    for u in units:
        if v < 1024.0 or u == units[-1]:
            return f"{int(v)} {u}" if u == "B" else f"{v:.2f} {u}"
        v /= 1024.0
    return f"{n} B"


def _walk_files(base: Path) -> Iterable[Path]:
    if not base.exists():
        return []
    for root, _dirs, files in os.walk(base):
        for f in files:
            yield Path(root) / f


def _dir_size_bytes(base: Path) -> tuple[int, int]:
    total = 0
    count = 0
    for fp in _walk_files(base):
        try:
            total += int(fp.stat().st_size)
            count += 1
        except OSError:
            continue
    return total, count


def _dir_mtime_utc(base: Path) -> str | None:
    try:
        return datetime.fromtimestamp(base.stat().st_mtime, tz=timezone.utc).isoformat()
    except OSError:
        return None


@dataclass(frozen=True)
class EvidenceDir:
    kind: str
    task_id: str | None
    path: Path


def _iter_evidence_dirs(root: Path) -> list[EvidenceDir]:
    artifacts = root / "artifacts"
    out: list[EvidenceDir] = []

    # Task evidence
    scc_tasks = artifacts / "scc_tasks"
    if scc_tasks.exists():
        for task_dir in scc_tasks.iterdir():
            if not task_dir.is_dir():
                continue
            evid = task_dir / "evidence"
            if evid.exists() and evid.is_dir():
                out.append(EvidenceDir(kind="task", task_id=task_dir.name, path=evid))

    # System evidence
    sys_evid = artifacts / "scc_state" / "evidence"
    if sys_evid.exists() and sys_evid.is_dir():
        out.append(EvidenceDir(kind="system", task_id=None, path=sys_evid))

    out.sort(key=lambda x: (x.kind, x.task_id or "", str(x.path)))
    return out


def _move_to_quarantine(*, root: Path, src: Path, quarantine_root: Path) -> Path:
    # Move the whole evidence dir into quarantine to keep traceability.
    # This is a heavy-handed option, intentionally not default.
    rel = src.relative_to(root)
    dst = quarantine_root / rel
    _ensure_dir(dst.parent)
    if dst.exists():
        # Avoid collisions; add suffix.
        ts = _utc_now().strftime("%Y%m%d_%H%M%S")
        dst = quarantine_root / f"{rel.as_posix().replace('/', '__')}__{ts}"
    shutil.move(str(src), str(dst))
    return dst


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Audit evidence dir sizes and optionally quarantine over-budget evidence.")
    ap.add_argument("--max-task-mib", type=int, default=512, help="Max MiB per task evidence dir (default: 512).")
    ap.add_argument("--max-system-mib", type=int, default=1024, help="Max MiB for system evidence dir (default: 1024).")
    ap.add_argument("--apply", action="store_true", help="Move over-budget dirs to quarantine (default: dry-run).")
    args = ap.parse_args(argv)

    root = _repo_root()
    artifacts = root / "artifacts"
    out_dir = artifacts / "scc_state" / "reports"
    _ensure_dir(out_dir)
    ts = _utc_now().strftime("%Y%m%d_%H%M%S")
    report_json = out_dir / f"evidence_budget_audit_{ts}.json"
    report_md = out_dir / f"evidence_budget_audit_{ts}.md"

    quarantine_root = artifacts / "_observatory_quarantine" / ts / "EVIDENCE_OVER_BUDGET"
    if args.apply:
        _ensure_dir(quarantine_root)

    max_task = int(args.max_task_mib) * 1024 * 1024
    max_system = int(args.max_system_mib) * 1024 * 1024

    rows: list[dict[str, Any]] = []
    moved = 0
    over = 0

    for ed in _iter_evidence_dirs(root):
        size_b, file_count = _dir_size_bytes(ed.path)
        limit_b = max_task if ed.kind == "task" else max_system
        is_over = size_b > limit_b
        if is_over:
            over += 1

        moved_to = None
        if args.apply and is_over:
            try:
                dst = _move_to_quarantine(root=root, src=ed.path, quarantine_root=quarantine_root)
                moved_to = str(dst.relative_to(root)).replace("\\", "/")
                moved += 1
            except Exception:
                moved_to = "MOVE_FAILED"

        rows.append(
            {
                "kind": ed.kind,
                "task_id": ed.task_id,
                "path": str(ed.path.relative_to(root)).replace("\\", "/"),
                "mtime_utc": _dir_mtime_utc(ed.path),
                "files": file_count,
                "size_bytes": size_b,
                "size_h": _format_bytes(size_b),
                "limit_bytes": limit_b,
                "limit_h": _format_bytes(limit_b),
                "over_budget": is_over,
                "moved_to": moved_to,
            }
        )

    payload = {
        "ts": ts,
        "apply": bool(args.apply),
        "max_task_mib": int(args.max_task_mib),
        "max_system_mib": int(args.max_system_mib),
        "dirs_total": len(rows),
        "dirs_over_budget": over,
        "dirs_moved": moved,
        "rows": rows,
    }

    report_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines: list[str] = []
    lines.append(f"# Evidence Budget Audit ({ts})")
    lines.append("")
    lines.append(f"- apply: `{payload['apply']}`")
    lines.append(f"- max_task_mib: `{payload['max_task_mib']}`")
    lines.append(f"- max_system_mib: `{payload['max_system_mib']}`")
    lines.append(f"- dirs_total: `{payload['dirs_total']}`")
    lines.append(f"- dirs_over_budget: `{payload['dirs_over_budget']}`")
    lines.append(f"- dirs_moved: `{payload['dirs_moved']}`")
    lines.append("")
    lines.append("| kind | task_id | files | size | limit | over | moved_to | path |")
    lines.append("|---|---|---:|---:|---:|---:|---|---|")
    for r in rows:
        lines.append(
            f"| {r['kind']} | {r['task_id'] or ''} | {r['files']} | {r['size_h']} | {r['limit_h']} | {str(r['over_budget']).lower()} | {r['moved_to'] or ''} | `{r['path']}` |"
        )
    report_md.write_text("\n".join(lines), encoding="utf-8")

    print(f"[evidence_budget_audit] over_budget={over} moved={moved} apply={payload['apply']}")
    print(f"[evidence_budget_audit] report_md={report_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

