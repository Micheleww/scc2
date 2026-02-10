from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class PinRequestItem:
    path: str
    kind: str = "file"  # file|range
    start_line: Optional[int] = None  # 1-based
    end_line: Optional[int] = None  # 1-based inclusive
    label: str = ""


@dataclass(frozen=True)
class Pin:
    id: str
    path: str
    kind: str
    start_line: Optional[int]
    end_line: Optional[int]
    label: str
    sha256: str
    bytes: int
    truncated: bool
    content: str


@dataclass(frozen=True)
class PinsResult:
    ok: bool
    repo_path: str
    pins: List[Pin]
    errors: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["pins"] = [asdict(p) for p in self.pins]
        return d


def _sha256(text: str) -> str:
    h = hashlib.sha256()
    h.update(text.encode("utf-8", errors="replace"))
    return h.hexdigest()


def _safe_rel_under_repo(*, repo_path: Path, rel_path: str) -> Path:
    repo = repo_path.resolve()
    rel = str(rel_path or "").strip().lstrip("/").lstrip("\\")
    if not rel or ".." in rel.split("/") or ".." in rel.split("\\"):
        raise ValueError("invalid_path")
    p = (repo / rel).resolve()
    p.relative_to(repo)
    return p


def build_pins(
    *,
    repo_path: Path,
    items: List[PinRequestItem],
    include_content: bool = True,
    max_chars_per_item: int = 8000,
    max_total_chars: int = 50_000,
) -> PinsResult:
    repo = Path(repo_path).resolve()
    if not repo.exists() or not repo.is_dir():
        return PinsResult(ok=False, repo_path=str(repo), pins=[], errors=[{"error": "repo_path_not_dir"}])

    per_item = max(256, min(200_000, int(max_chars_per_item or 8000)))
    total_cap = max(per_item, min(2_000_000, int(max_total_chars or 50_000)))

    pins: List[Pin] = []
    errors: List[Dict[str, Any]] = []
    total_used = 0

    for idx, it in enumerate(items or [], start=1):
        try:
            p = _safe_rel_under_repo(repo_path=repo, rel_path=it.path)
            if not p.exists() or not p.is_file():
                errors.append({"idx": idx, "path": it.path, "error": "not_found"})
                continue

            kind = (it.kind or "file").strip().lower()
            if kind not in ("file", "range"):
                kind = "file"

            text = ""
            if include_content:
                raw = p.read_text(encoding="utf-8", errors="replace")
                if kind == "range":
                    lines = raw.splitlines()
                    s = int(it.start_line or 1)
                    e = int(it.end_line or s)
                    s = max(1, s)
                    e = max(s, e)
                    # Slice is 0-based; include end line.
                    sub = lines[s - 1 : e]
                    text = "\n".join(sub)
                else:
                    text = raw

                remaining = max(0, total_cap - total_used)
                cap = min(per_item, remaining)
                truncated = len(text) > cap
                text = text[:cap]
            else:
                truncated = False

            pin_id = f"pin_{idx:03d}_{_sha256(str(p))[:10]}"
            sha = _sha256(text if include_content else str(p))
            pins.append(
                Pin(
                    id=pin_id,
                    path=str(p),
                    kind=kind,
                    start_line=int(it.start_line) if it.start_line is not None else None,
                    end_line=int(it.end_line) if it.end_line is not None else None,
                    label=str(it.label or ""),
                    sha256=sha,
                    bytes=len(text.encode("utf-8", errors="replace")) if include_content else 0,
                    truncated=bool(truncated),
                    content=text,
                )
            )
            total_used += len(text)
            if total_used >= total_cap:
                break
        except Exception as e:
            errors.append({"idx": idx, "path": getattr(it, "path", ""), "error": str(e)})

    return PinsResult(ok=True, repo_path=str(repo), pins=pins, errors=errors)

