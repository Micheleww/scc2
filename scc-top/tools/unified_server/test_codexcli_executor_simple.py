#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简化版测试：Codex CLI 执行器（/executor/codex 与 /executor/codex/run）

说明：
- 不会自动启动统一服务器；请先确保 `python -m tools.unified_server.main` 已运行。
- 你可以先自行运行 `codex login` 完成登录，然后再运行本脚本验证是否可用 gpt-5.2-codex。
"""

import json
import os
import sys
import time

import requests

def _get_base_url() -> str:
    # Allow overriding for parallel local runs (e.g. when 18788 is occupied).
    base = os.environ.get("UNIFIED_SERVER_BASE_URL", "").strip()
    if base:
        return base.rstrip("/")
    host = os.environ.get("UNIFIED_SERVER_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = os.environ.get("UNIFIED_SERVER_PORT", "18788").strip() or "18788"
    return f"http://{host}:{port}"


BASE_URL = _get_base_url()


def check_server() -> bool:
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


def post_json(path: str, payload: dict) -> dict:
    headers = {
        "Content-Type": "application/json",
        "X-Trace-ID": f"test-codexcli-executor-{int(time.time())}",
    }
    r = requests.post(f"{BASE_URL}{path}", headers=headers, json=payload, timeout=1200)
    r.raise_for_status()
    return r.json()


def main() -> int:
    if sys.platform == "win32":
        os.environ["PYTHONIOENCODING"] = "utf-8"

    print("=" * 60)
    print("Codex CLI Executor 测试（简化版）")
    print("=" * 60)

    if not check_server():
        print(f"[失败] 统一服务器未运行：{BASE_URL}/health")
        print("请先启动：python -m tools.unified_server.main")
        return 1

    # 1) 单条 prompt：默认不改代码（用于验证登录/模型可用）
    print("\n[测试] /executor/codex（单条）")
    single = post_json(
        "/executor/codex",
        {
            "prompt": "仅回复：OK（不要修改任何文件，不要运行任何命令）。",
            "model": "gpt-5.2-codex",
        },
    )
    print(json.dumps(single, ensure_ascii=False, indent=2))

    # 2) 批量 parents：两条“无副作用”子任务
    print("\n[测试] /executor/codex/run（批量）")
    batch = post_json(
        "/executor/codex/run",
        {
            "model": "gpt-5.2-codex",
            "timeout_s": 600,
            "parents": {
                "parents": [
                    {"id": 1, "description": "仅回复：P1_OK（不要修改任何文件，不要运行任何命令）。"},
                    {"id": 2, "description": "仅回复：P2_OK（不要修改任何文件，不要运行任何命令）。"},
                ]
            },
        },
    )
    print(json.dumps(batch, ensure_ascii=False, indent=2))

    print("\n[完成] 如果看到 executor=codex 且 exit_code=0，则 Codex CLI 可作为执行器运行子任务。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
