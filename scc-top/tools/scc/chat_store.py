from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_mkdir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class ChatMessage:
    ts_utc: str
    role: str  # system|user|assistant|tool
    content: str
    meta: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SCCChatStore:
    """
    Minimal persistent chat store (append-only JSONL) for long-running conversations.

    Layout:
      artifacts/scc_chats/<chat_id>/
        meta.json
        messages.jsonl
        summary.txt
    """

    def __init__(self, *, repo_root: Path):
        self.repo_root = Path(repo_root).resolve()
        self.root = (self.repo_root / "artifacts" / "scc_chats").resolve()
        _safe_mkdir(self.root)

    def _chat_dir(self, chat_id: str) -> Path:
        return (self.root / str(chat_id)).resolve()

    def _meta_path(self, chat_id: str) -> Path:
        return self._chat_dir(chat_id) / "meta.json"

    def _messages_path(self, chat_id: str) -> Path:
        return self._chat_dir(chat_id) / "messages.jsonl"

    def _summary_path(self, chat_id: str) -> Path:
        return self._chat_dir(chat_id) / "summary.txt"

    def _context_pack_path(self, chat_id: str) -> Path:
        return self._chat_dir(chat_id) / "context_pack.json"

    def create(self, *, chat_id: Optional[str] = None, title: str = "") -> Dict[str, Any]:
        cid = (chat_id or "").strip() or f"CHAT-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:6]}"
        d = self._chat_dir(cid)
        _safe_mkdir(d)
        meta_p = self._meta_path(cid)
        if not meta_p.exists():
            meta = {"chat_id": cid, "title": str(title or ""), "created_utc": _utc_now_iso()}
            meta_p.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        msg_p = self._messages_path(cid)
        if not msg_p.exists():
            msg_p.write_text("", encoding="utf-8")
        return {"chat_id": cid, "dir": str(d), "meta": json.loads(meta_p.read_text(encoding="utf-8"))}

    def append(self, *, chat_id: str, role: str, content: str, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        cid = str(chat_id).strip()
        if not cid:
            raise ValueError("chat_id_required")
        self.create(chat_id=cid)
        msg = ChatMessage(ts_utc=_utc_now_iso(), role=str(role or "user"), content=str(content or ""), meta=meta or {})
        p = self._messages_path(cid)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(msg.to_dict(), ensure_ascii=False) + "\n")
        return {"chat_id": cid, "ok": True, "message": msg.to_dict(), "path": str(p)}

    def set_summary(self, *, chat_id: str, summary: str) -> Dict[str, Any]:
        cid = str(chat_id).strip()
        if not cid:
            raise ValueError("chat_id_required")
        self.create(chat_id=cid)
        p = self._summary_path(cid)
        p.write_text(str(summary or ""), encoding="utf-8")
        return {"chat_id": cid, "ok": True, "path": str(p)}

    def get_summary(self, *, chat_id: str) -> str:
        p = self._summary_path(str(chat_id).strip())
        if not p.exists():
            return ""
        return p.read_text(encoding="utf-8", errors="replace")

    def list_chats(self, *, limit: int = 100) -> List[Dict[str, Any]]:
        lim = max(1, min(500, int(limit or 100)))
        out: List[Dict[str, Any]] = []
        for d in sorted(self.root.glob("*"), reverse=True):
            if not d.is_dir():
                continue
            meta_p = d / "meta.json"
            if not meta_p.exists():
                continue
            try:
                meta = json.loads(meta_p.read_text(encoding="utf-8"))
            except Exception:
                meta = {"chat_id": d.name}
            out.append({"chat_id": d.name, "meta": meta, "dir": str(d)})
            if len(out) >= lim:
                break
        return out

    def snapshot(self, *, chat_id: str, tail: int = 50) -> Dict[str, Any]:
        cid = str(chat_id).strip()
        if not cid:
            raise ValueError("chat_id_required")
        self.create(chat_id=cid)
        msg_p = self._messages_path(cid)
        lines = msg_p.read_text(encoding="utf-8", errors="replace").splitlines()
        t = max(1, min(2000, int(tail or 50)))
        msgs: List[Dict[str, Any]] = []
        for ln in lines[-t:]:
            try:
                msgs.append(json.loads(ln))
            except Exception:
                continue
        return {
            "chat_id": cid,
            "ok": True,
            "messages": msgs,
            "summary": self.get_summary(chat_id=cid),
            "count_approx": len(lines),
            "path": str(msg_p),
        }

    def write_context_pack(self, *, chat_id: str, context_pack: Dict[str, Any]) -> Dict[str, Any]:
        cid = str(chat_id).strip()
        if not cid:
            raise ValueError("chat_id_required")
        self.create(chat_id=cid)
        p = self._context_pack_path(cid)
        p.write_text(json.dumps(context_pack, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"chat_id": cid, "ok": True, "path": str(p)}
