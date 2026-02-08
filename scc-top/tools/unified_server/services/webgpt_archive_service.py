from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from tools.chatgpt_chat_archive_mvp.chat_archive_mvp import db as chat_db


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _stable_hash(*, conversation_id: str, role: str, content_text: str, content_json: dict[str, Any] | None) -> str:
    payload = {
        "conversation_id": conversation_id,
        "role": role,
        "content_text": content_text,
        "content_json": content_json,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class IntakeResult:
    inserted: int
    duplicates: int
    last_seq: int


class WebGPTArchiveService:
    """
    Repo-local "WebGPT capture" archive:
    - SQLite + FTS5 (same schema as chat_archive_mvp)
    - Intake payload compatible with the browser extension / embedded browser extraction
    - Markdown export into docs (for downstream AI summarization)
    """

    def __init__(self, *, repo_root: Path):
        self._repo_root = repo_root.resolve()
        self._lock = threading.Lock()

        self._data_dir = (self._repo_root / "artifacts" / "webgpt").resolve()
        self._db_path = (self._data_dir / "archive.sqlite3").resolve()
        self._db = chat_db.connect(self._db_path)
        self._export_state_path = (self._data_dir / "export_state.json").resolve()

    def _load_export_state(self) -> dict[str, Any]:
        try:
            if self._export_state_path.exists():
                return json.loads(self._export_state_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return {}

    def _save_export_state(self, state: dict[str, Any]) -> None:
        try:
            self._export_state_path.parent.mkdir(parents=True, exist_ok=True)
            self._export_state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            # best-effort only
            return

    @property
    def db_path(self) -> Path:
        return self._db_path

    @property
    def data_dir(self) -> Path:
        return self._data_dir

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "ok": True,
                "db_path": str(self._db_path),
                "counts": chat_db.counts(self._db.conn),
                "ingest": chat_db.get_ingest_stats(self._db.conn),
            }

    def intake(
        self,
        *,
        conversation_id: str,
        title: str | None,
        source: str,
        messages: list[dict[str, Any]],
    ) -> IntakeResult:
        cid = (conversation_id or "").strip()
        if not cid or len(cid) > 256:
            raise ValueError("invalid conversation_id")

        inserted = 0
        duplicates = 0
        with self._lock:
            if chat_db.get_paused(self._db.conn):
                chat_db.bump_stats(self._db.conn, failed=1, last_error="paused")
                self._db.conn.commit()
                raise RuntimeError("paused")

            seq = chat_db.next_seq(self._db.conn, conversation_id=cid)
            try:
                with self._db.conn:
                    chat_db.upsert_conversation(self._db.conn, conversation_id=cid, title=title, source=source or "webgpt")
                    for m in messages:
                        role = str(m.get("role") or "assistant")
                        if role not in {"user", "assistant", "tool", "system"}:
                            role = "assistant"
                        content_text = str(m.get("content_text") or "").strip()
                        if not content_text:
                            continue
                        content_json = m.get("content_json") if isinstance(m.get("content_json"), dict) else None
                        message_id = str(m.get("message_id")).strip() if m.get("message_id") else None
                        created_at = str(m.get("created_at")).strip() if m.get("created_at") else None
                        msg_hash = _stable_hash(
                            conversation_id=cid,
                            role=role,
                            content_text=content_text,
                            content_json=content_json,
                        )
                        if chat_db.message_exists(self._db.conn, conversation_id=cid, message_id=message_id, msg_hash=msg_hash):
                            duplicates += 1
                            continue
                        chat_db.insert_message(
                            self._db.conn,
                            conversation_id=cid,
                            message_id=message_id,
                            role=role,
                            created_at=created_at or _utc_now_iso(),
                            content_text=content_text,
                            content_json=content_json,
                            msg_hash=msg_hash,
                            seq=seq,
                        )
                        inserted += 1
                        seq += 1
                chat_db.bump_stats(self._db.conn, inserted=inserted, duplicates=duplicates, last_error=None)
                self._db.conn.commit()
            except Exception as exc:
                chat_db.bump_stats(self._db.conn, failed=1, last_error=type(exc).__name__)
                self._db.conn.commit()
                raise

        return IntakeResult(inserted=inserted, duplicates=duplicates, last_seq=seq - 1)

    def list_conversations(self, *, limit: int = 50) -> list[dict[str, Any]]:
        lim = max(1, min(200, int(limit)))
        with self._lock:
            rows = self._db.conn.execute(
                "SELECT conversation_id, title, created_at, updated_at, source FROM conversations ORDER BY updated_at DESC LIMIT ?",
                (lim,),
            ).fetchall()
        return [dict(r) for r in rows]

    def _write_index(self, *, docs_root: Path) -> None:
        header = [
            "# WebGPT Capture Index",
            "",
            "本目录用于存放从网页 ChatGPT（WebGPT）采集的会话内容（原始对话），供后续 AI 总结与需求提炼。",
            "",
            "- 个性化记忆（Latest）：[memory.md](memory.md)",
            "",
            "## Conversations",
            "",
        ]
        items = []
        for c in self.list_conversations(limit=200):
            cid2 = str(c["conversation_id"])
            sid2 = "".join(ch for ch in cid2 if ch.isalnum() or ch in {"-", "_"})
            t2 = (c.get("title") or "").strip() or sid2
            items.append(f"- [{t2}](conversations/{sid2}.md) (`{cid2}`)")
        index_path = (docs_root / "index.md").resolve()
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text("\n".join(header + items + [""]), encoding="utf-8")

    def _mirror_to_artifacts(self, *, docs_root: Path, safe_id: str, src_path: Path) -> dict[str, Any]:
        """
        Mirror exported markdown into artifacts/ so it can be accessed via /files/*.

        We keep the canonical shared-context copy under docs/INPUTS/WEBGPT, but UI needs
        a stable single-port viewer without direct filesystem access.
        """
        mirror_root = (self._data_dir / "docs").resolve()  # artifacts/webgpt/docs
        conv_dir = (mirror_root / "conversations").resolve()
        conv_dir.mkdir(parents=True, exist_ok=True)

        dst_path = (conv_dir / f"{safe_id}.md").resolve()
        dst_path.write_text(src_path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")

        # Also keep an index.md mirror for discovery in the UI.
        try:
            self._write_index(docs_root=mirror_root)
        except Exception:
            pass

        try:
            rel_doc = str(dst_path.relative_to(self._repo_root)).replace("\\", "/")
        except Exception:
            rel_doc = str(dst_path).replace("\\", "/")
        try:
            rel_index = str((mirror_root / "index.md").relative_to(self._repo_root)).replace("\\", "/")
        except Exception:
            rel_index = str((mirror_root / "index.md")).replace("\\", "/")

        return {"artifact_doc_path": rel_doc, "artifact_index_path": rel_index}

    def get_conversation(self, *, conversation_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        cid = (conversation_id or "").strip()
        if not cid:
            raise ValueError("conversation_id is empty")
        with self._lock:
            conv = self._db.conn.execute(
                "SELECT conversation_id, title, created_at, updated_at, source FROM conversations WHERE conversation_id=?",
                (cid,),
            ).fetchone()
            if not conv:
                raise KeyError("conversation not found")
            msgs = self._db.conn.execute(
                "SELECT seq, message_id, role, created_at, content_text, content_json FROM messages WHERE conversation_id=? ORDER BY seq",
                (cid,),
            ).fetchall()
        out_msgs: list[dict[str, Any]] = []
        for r in msgs:
            d = dict(r)
            raw = d.get("content_json")
            if isinstance(raw, str) and raw.strip():
                try:
                    d["content_json"] = json.loads(raw)
                except Exception:
                    d["content_json"] = None
            else:
                d["content_json"] = None
            out_msgs.append(d)
        return dict(conv), out_msgs

    def conversation_last_seq(self, *, conversation_id: str) -> int:
        cid = (conversation_id or "").strip()
        if not cid:
            raise ValueError("conversation_id is empty")
        with self._lock:
            row = self._db.conn.execute(
                "SELECT COALESCE(MAX(seq), 0) AS max_seq FROM messages WHERE conversation_id=?",
                (cid,),
            ).fetchone()
        try:
            return int(row["max_seq"] if isinstance(row, dict) else row[0])
        except Exception:
            return 0

    def export_markdown(self, *, conversation_id: str, docs_root: Path | None = None) -> dict[str, Any]:
        conv, msgs = self.get_conversation(conversation_id=conversation_id)
        docs_root = (docs_root or (self._repo_root / "docs" / "INPUTS" / "WEBGPT")).resolve()
        conv_dir = docs_root / "conversations"
        conv_dir.mkdir(parents=True, exist_ok=True)

        cid = str(conv["conversation_id"])
        safe_id = "".join(ch for ch in cid if ch.isalnum() or ch in {"-", "_"})
        if not safe_id:
            raise ValueError("conversation_id not safe")

        title = (conv.get("title") or "").strip()
        updated = conv.get("updated_at") or ""

        out_path = (conv_dir / f"{safe_id}.md").resolve()
        try:
            out_path.relative_to(docs_root)
        except Exception as exc:
            raise ValueError("export path escape blocked") from exc

        lines: list[str] = []
        lines.append(f"# WebGPT Conversation: {title or safe_id}")
        lines.append("")
        lines.append(f"- conversation_id: `{cid}`")
        lines.append(f"- updated_at: `{updated}`")
        lines.append(f"- source: `{conv.get('source')}`")
        lines.append("")
        for m in msgs:
            role = str(m.get("role") or "assistant")
            created = str(m.get("created_at") or "")
            lines.append(f"## {role} ({created})")
            lines.append("")
            content = str(m.get("content_text") or "").rstrip()
            if content:
                lines.append(content)
                lines.append("")
            cj = m.get("content_json")
            if isinstance(cj, dict):
                code_blocks = cj.get("code_blocks") if isinstance(cj.get("code_blocks"), list) else []
                for cb in code_blocks:
                    if not isinstance(cb, str) or not cb.strip():
                        continue
                    lines.append("```")
                    lines.append(cb.rstrip("\n"))
                    lines.append("```")
                    lines.append("")

        out_path.write_text("\n".join(lines), encoding="utf-8")

        self._write_index(docs_root=docs_root)

        # Mirror into artifacts/ for UI access via /files/*.
        mirror = self._mirror_to_artifacts(docs_root=docs_root, safe_id=safe_id, src_path=out_path)

        # Update export state (best-effort): last exported seq for incremental export.
        try:
            last_seq = 0
            if msgs:
                try:
                    last_seq = int(msgs[-1].get("seq") or 0)
                except Exception:
                    last_seq = 0
            state = self._load_export_state()
            exports = state.get("exports") if isinstance(state.get("exports"), dict) else {}
            exports[str(cid)] = {"last_seq": last_seq, "exported_at": _utc_now_iso()}
            state["exports"] = exports
            self._save_export_state(state)
        except Exception:
            pass

        return {
            "ok": True,
            "conversation_id": cid,
            "doc_path": str(out_path.relative_to(self._repo_root)).replace("\\", "/"),
            "index_path": str((docs_root / "index.md").relative_to(self._repo_root)).replace("\\", "/"),
            **mirror,
        }

    def export_markdown_if_changed(self, *, conversation_id: str, docs_root: Path | None = None) -> dict[str, Any]:
        """
        Incremental behavior: only rewrite markdown if there are new messages since the last export.
        """
        cid = (conversation_id or "").strip()
        if not cid:
            raise ValueError("conversation_id is empty")

        with self._lock:
            state = self._load_export_state()
            exports = state.get("exports") if isinstance(state.get("exports"), dict) else {}
            prev = exports.get(cid) if isinstance(exports.get(cid), dict) else {}
            prev_last_seq = int(prev.get("last_seq") or 0) if isinstance(prev, dict) else 0

        current_last_seq = self.conversation_last_seq(conversation_id=cid)
        if current_last_seq <= prev_last_seq:
            return {"ok": True, "conversation_id": cid, "skipped": True, "reason": "no_new_messages"}

        res = self.export_markdown(conversation_id=cid, docs_root=docs_root)
        res["skipped"] = False
        res["new_last_seq"] = current_last_seq
        res["prev_last_seq"] = prev_last_seq
        return res

    def export_all_markdown(self, *, limit: int = 500, docs_root: Path | None = None) -> dict[str, Any]:
        """
        Export all conversations (best-effort) into docs/INPUTS/WEBGPT and refresh index.md.

        This is intentionally idempotent: it rewrites the markdown files each time.
        """
        docs_root = (docs_root or (self._repo_root / "docs" / "INPUTS" / "WEBGPT")).resolve()
        lim = max(1, min(2000, int(limit)))
        exported: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        for c in self.list_conversations(limit=lim):
            cid = str(c.get("conversation_id") or "").strip()
            if not cid:
                continue
            try:
                res = self.export_markdown_if_changed(conversation_id=cid, docs_root=docs_root)
                if res.get("skipped"):
                    skipped.append({"conversation_id": cid, "reason": res.get("reason")})
                else:
                    exported.append({"conversation_id": cid, "doc_path": res.get("doc_path")})
            except Exception as exc:  # noqa: BLE001
                errors.append({"conversation_id": cid, "error": type(exc).__name__})
        # Always refresh index.md even if everything was skipped.
        try:
            self._write_index(docs_root=docs_root)
        except Exception:
            pass
        return {"ok": True, "exported": exported, "skipped": skipped, "errors": errors, "count": len(exported), "skipped_count": len(skipped)}
