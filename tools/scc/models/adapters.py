from __future__ import annotations

import json
import os
import pathlib
import subprocess
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


def openrouter_chat_completion(
    api_key: str,
    model: str,
    messages: List[ChatMessage],
    *,
    timeout_s: int = 60,
    extra_headers: Optional[Dict[str, str]] = None,
) -> str:
    url = "https://openrouter.ai/api/v1/chat/completions"
    payload = {"model": model, "messages": [{"role": m.role, "content": m.content} for m in messages]}
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        **(extra_headers or {}),
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        obj = json.loads(resp.read().decode("utf-8"))
    choices = obj.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError(f"openrouter: no choices in response: {str(obj)[:300]}")
    msg = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(msg, dict):
        raise RuntimeError(f"openrouter: invalid message: {str(choices[0])[:300]}")
    return str(msg.get("content") or "")


def codex_cli_chat_completion(
    codex_bin: str,
    model: str,
    prompt: str,
    *,
    cwd: pathlib.Path,
    timeout_s: int = 180,
) -> str:
    out_last = cwd / "artifacts" / "_tmp" / "codex_last_message.txt"
    out_last.parent.mkdir(parents=True, exist_ok=True)
    # Use read-only sandbox to prevent accidental execution.
    # `-a never` is passed at the top-level to avoid interactive prompts.
    p = subprocess.run(
        [codex_bin, "-a", "never", "exec", "--sandbox", "read-only", "--skip-git-repo-check", "-C", str(cwd), "--model", model, "--output-last-message", str(out_last)],
        input=prompt,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout_s,
        env=os.environ.copy(),
    )
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout or "codex exec failed").strip()[:2000])
    if not out_last.exists():
        raise RuntimeError("codex exec did not write --output-last-message")
    return out_last.read_text(encoding="utf-8", errors="replace")


def opencode_cli_chat_completion(
    opencode_bin: str,
    model: str,
    prompt: str,
    *,
    cwd: pathlib.Path,
    timeout_s: int = 180,
) -> str:
    # `--format json` emits JSON events; simplest is to grab the last "assistant" text segment.
    p = subprocess.run(
        [opencode_bin, "run", prompt, "--model", model, "--format", "json"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_s,
        env=os.environ.copy(),
    )
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout or "opencode run failed").strip()[:2000])

    last_text = ""
    for line in (p.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except Exception:
            continue
        if not isinstance(ev, dict):
            continue
        # Heuristic: accept common event shapes.
        if ev.get("type") in {"message", "assistant_message"} and isinstance(ev.get("content"), str):
            last_text = ev["content"]
        if ev.get("role") == "assistant" and isinstance(ev.get("content"), str):
            last_text = ev["content"]
        msg = ev.get("message")
        if isinstance(msg, dict) and msg.get("role") == "assistant" and isinstance(msg.get("content"), str):
            last_text = msg["content"]
    if not last_text:
        # Fallback to raw stdout (trim to avoid huge logs).
        last_text = (p.stdout or "").strip()
    return last_text

