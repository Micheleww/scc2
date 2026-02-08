from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class MemoryIntakeResult:
    written: bool
    doc_path: str


class WebGPTMemoryService:
    """
    Repo-local "ChatGPT personalization memory" capture.

    This is separate from the conversation archive schema (SQLite), and is written as:
    - artifacts/webgpt/memory.jsonl (append-only evidence)
    - docs/INPUTS/WEBGPT/memory.md (latest snapshot for shared context)
    """

    def __init__(self, *, repo_root: Path):
        self._repo_root = repo_root.resolve()
        self._data_dir = (self._repo_root / "artifacts" / "webgpt").resolve()
        self._docs_dir = (self._repo_root / "docs" / "INPUTS" / "WEBGPT").resolve()
        self._jsonl_path = (self._data_dir / "memory.jsonl").resolve()
        self._doc_path = (self._docs_dir / "memory.md").resolve()

    @property
    def doc_path(self) -> Path:
        return self._doc_path

    def intake(self, *, payload: dict[str, Any]) -> MemoryIntakeResult:
        page_url = str(payload.get("page_url") or "").strip()
        captured_at = str(payload.get("captured_at") or _utc_now_iso()).strip()
        text = str(payload.get("text") or "").strip()
        items = payload.get("items") if isinstance(payload.get("items"), list) else []
        items = [str(x).strip() for x in items if isinstance(x, (str, int, float)) and str(x).strip()]

        envelope = {
            "received_at": _utc_now_iso(),
            "payload": {
                "page_url": page_url,
                "captured_at": captured_at,
                "text": text,
                "items": items,
            },
        }

        self._data_dir.mkdir(parents=True, exist_ok=True)
        with open(self._jsonl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(envelope, ensure_ascii=False) + "\n")

        self._docs_dir.mkdir(parents=True, exist_ok=True)
        lines: list[str] = []
        lines.append("# WebGPT Personalization Memory (Latest)")
        lines.append("")
        if page_url:
            lines.append(f"- page_url: `{page_url}`")
        lines.append(f"- captured_at: `{captured_at}`")
        lines.append(f"- updated_at: `{_utc_now_iso()}`")
        lines.append("")
        if items:
            lines.append("## Items")
            lines.append("")
            for it in items:
                lines.append(f"- {it}")
            lines.append("")
        if text and (not items):
            lines.append("## Raw")
            lines.append("")
            lines.append(text)
            lines.append("")

        self._doc_path.write_text("\n".join(lines), encoding="utf-8")

        # Mirror into artifacts/ so the Workbench can view/download via /files/*.
        try:
            mirror_root = (self._data_dir / "docs").resolve()  # artifacts/webgpt/docs
            mirror_root.mkdir(parents=True, exist_ok=True)
            (mirror_root / "memory.md").write_text("\n".join(lines), encoding="utf-8")
        except Exception:
            pass

        return MemoryIntakeResult(written=True, doc_path=str(self._doc_path.relative_to(self._repo_root)).replace("\\", "/"))
