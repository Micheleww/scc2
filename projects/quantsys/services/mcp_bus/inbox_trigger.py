#!/usr/bin/env python3
"""
ATA 收信箱激发器（轮询器）

用途：
- 定时从 ATA 消息库拉取某个 agent 的收件箱（to_agent=agent_id）
- 将新消息落盘为任务文件，供“使用者 AI”在自己的工作流中读取并处理

说明：
- 本脚本不发送消息、不修改受保护代码目录，只做“读取 + 生成任务文件”
- 默认输出到 tasks/inbox/<agent_id>/ 目录
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import requests


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _state_file(agent_id: str) -> Path:
    return _repo_root() / "tools" / "mcp_bus" / "_state" / f"inbox_trigger_state__{agent_id}.json"


def _load_seen(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return set(data.get("seen_msg_ids", []))
    except Exception:
        return set()


def _save_seen(path: Path, seen: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"seen_msg_ids": sorted(seen)}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _mcp_call(
    session: requests.Session, base_url: str, name: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }
    r = session.post(f"{base_url}/mcp", json=req, timeout=20)
    r.raise_for_status()
    j = r.json()
    # tool results are returned as result.content[0].text (json string)
    text = j["result"]["content"][0]["text"]
    return (
        json.loads(text)
        if isinstance(text, str) and text.strip().startswith("{")
        else {"raw": text}
    )


def _write_task_file(out_dir: Path, agent_id: str, msg: dict[str, Any]) -> Path:
    msg_id = msg.get("msg_id") or "unknown"
    task_dir = out_dir / agent_id
    task_dir.mkdir(parents=True, exist_ok=True)
    p = task_dir / f"{msg_id}.md"
    payload = msg.get("payload") if isinstance(msg.get("payload"), dict) else {}
    content = (
        payload.get("message")
        or payload.get("text")
        or json.dumps(payload, ensure_ascii=False, indent=2)
    )
    header = [
        f"# ATA Inbox Task: {msg_id}",
        "",
        f"- agent_id: `{agent_id}`",
        f"- taskcode: `{msg.get('taskcode')}`",
        f"- from_agent: `{msg.get('from_agent')}`",
        f"- kind: `{msg.get('kind')}`",
        f"- created_at: `{msg.get('created_at')}`",
        f"- priority: `{msg.get('priority')}`",
        "",
        "## Message",
        "",
        str(content),
        "",
    ]
    p.write_text("\n".join(header), encoding="utf-8")
    return p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:18788/", help="MCP server base url")
    ap.add_argument("--agent-id", required=True, help="Target agent_id to poll (to_agent filter)")
    ap.add_argument("--interval", type=int, default=10, help="Polling interval seconds")
    ap.add_argument("--limit", type=int, default=50, help="Max messages per poll")
    ap.add_argument(
        "--out-dir", default=str(_repo_root() / "tasks" / "inbox"), help="Output dir for task files"
    )
    ap.add_argument("--once", action="store_true", help="Run once and exit")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    state_path = _state_file(args.agent_id)
    seen = _load_seen(state_path)

    s = requests.Session()
    while True:
        try:
            res = _mcp_call(
                s,
                args.base_url,
                "ata_receive",
                {
                    "to_agent": args.agent_id,
                    "unread_only": False,
                    "limit": max(1, min(args.limit, 200)),
                },
            )
            messages: list[dict[str, Any]] = (
                res.get("messages", []) if isinstance(res, dict) else []
            )
            new_msgs = [m for m in messages if m.get("msg_id") and m.get("msg_id") not in seen]
            if new_msgs:
                for m in new_msgs:
                    p = _write_task_file(out_dir, args.agent_id, m)
                    seen.add(m.get("msg_id"))
                    print(f"[NEW] wrote {p.as_posix()}")
                _save_seen(state_path, seen)
            else:
                print("[OK] no new messages")
        except Exception as e:
            print(f"[ERR] {e}")

        if args.once:
            return 0
        time.sleep(max(1, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
