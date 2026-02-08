from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class TailResult:
    ok: bool
    path: str
    cursor: int
    lines: List[str]
    size: int = 0
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def tail_jsonl_with_cursor(
    *,
    path: Path,
    cursor: Optional[int],
    max_bytes: int = 256_000,
    max_lines: int = 2000,
) -> TailResult:
    """
    Cursor-based tail for append-only JSONL.

    cursor:
      - None: start from (EOF - max_bytes), dropping partial first line
      - int: byte offset to start reading from
    returns:
      - cursor=EOF (byte size)
      - lines split by newline
    """
    p = Path(path).resolve()
    if not p.exists():
        return TailResult(ok=False, path=str(p), cursor=0, lines=[], size=0, error="not_found")

    try:
        size = p.stat().st_size
    except Exception:
        size = 0
    mb = max(1024, min(5_000_000, int(max_bytes or 256_000)))
    ml = max(1, min(20_000, int(max_lines or 2000)))

    if cursor is None:
        start = max(0, int(size) - mb)
    else:
        start = max(0, min(int(size), int(cursor)))

    try:
        with open(p, "rb") as f:
            f.seek(start)
            chunk = f.read(int(size) - start)
    except Exception as e:
        return TailResult(
            ok=False,
            path=str(p),
            cursor=int(size),
            lines=[],
            size=int(size),
            error=f"read_failed:{e}",
        )

    text = chunk.decode("utf-8", errors="replace")

    lines = text.splitlines()
    # If we computed start ourselves (cursor is None), we may begin mid-line.
    # In that case drop the first partial line unless we started at 0.
    if cursor is None and start > 0 and lines:
        lines = lines[1:]

    if len(lines) > ml:
        lines = lines[-ml:]

    return TailResult(ok=True, path=str(p), cursor=int(size), lines=lines, size=int(size))
