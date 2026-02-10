from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .ata_protocol import ATAEvent, ATATaskContext


@dataclass
class ATAMailboxPaths:
    mailbox_dir: Path
    messages_dir: Path
    events_file: Path
    context_file: Path
    meta_file: Path
    artifacts_dir: Path
    verdict_dir: Path


class ATAMailbox:
    def __init__(self, repo_root: Path, security=None):
        self.repo_root = repo_root
        self.security = security
        self.base_dir = self.repo_root / "docs" / "REPORT" / "ata" / "mailbox"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def get_paths(self, task_code: str) -> ATAMailboxPaths:
        mailbox_dir = self.base_dir / task_code
        messages_dir = mailbox_dir / "messages"
        artifacts_dir = self.repo_root / "docs" / "REPORT" / "ata" / "artifacts" / task_code
        verdict_dir = artifacts_dir / "verdict"
        return ATAMailboxPaths(
            mailbox_dir=mailbox_dir,
            messages_dir=messages_dir,
            events_file=mailbox_dir / "events.jsonl",
            context_file=mailbox_dir / "context.json",
            meta_file=mailbox_dir / "meta.json",
            artifacts_dir=artifacts_dir,
            verdict_dir=verdict_dir,
        )

    def init_task(self, context: ATATaskContext, meta: dict[str, Any]) -> ATAMailboxPaths:
        paths = self.get_paths(context.task_code)
        self._ensure_dir(paths.mailbox_dir)
        self._ensure_dir(paths.messages_dir)
        self._ensure_dir(paths.artifacts_dir)
        self._ensure_dir(paths.verdict_dir)

        self._write_json(paths.context_file, context.dict())
        meta_payload = {
            **meta,
            "task_code": context.task_code,
            "created_at": datetime.utcnow().isoformat() + "Z",
        }
        self._write_json(paths.meta_file, meta_payload)
        return paths

    def append_event(self, event: ATAEvent) -> None:
        paths = self.get_paths(event.task_code)
        self._ensure_dir(paths.mailbox_dir)
        line = json.dumps(event.dict(), ensure_ascii=False)
        self._append_text(paths.events_file, line + "\n")

    def write_message(self, task_code: str, message_id: str, payload: dict[str, Any]) -> Path:
        paths = self.get_paths(task_code)
        self._ensure_dir(paths.messages_dir)
        filename = f"{message_id}.json"
        target = paths.messages_dir / filename
        self._write_json(target, payload)
        return target

    def write_verdict(self, task_code: str, verdict: dict[str, Any]) -> Path:
        paths = self.get_paths(task_code)
        self._ensure_dir(paths.verdict_dir)
        target = paths.verdict_dir / "verdict.json"
        self._write_json(target, verdict)
        return target

    def _ensure_dir(self, path: Path) -> None:
        if self.security:
            allowed, err = self.security.check_access(str(path), "write")
            if not allowed:
                raise PermissionError(err)
        path.mkdir(parents=True, exist_ok=True)

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        if self.security:
            allowed, err = self.security.check_access(str(path), "write")
            if not allowed:
                raise PermissionError(err)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def _append_text(self, path: Path, content: str) -> None:
        if self.security:
            allowed, err = self.security.check_access(str(path), "write")
            if not allowed:
                raise PermissionError(err)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(content)
