#!/usr/bin/env python3
"""
从文件系统列举所有ATA消息
"""

import io
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

# 设置标准输出编码为UTF-8（Windows兼容）
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def load_all_messages(repo_root: Path):
    """从文件系统加载所有ATA消息"""
    messages_dir = repo_root / "docs" / "REPORT" / "ata" / "messages"
    messages = []

    if not messages_dir.exists():
        return messages

    # 遍历所有任务目录
    for task_dir in messages_dir.iterdir():
        if not task_dir.is_dir():
            continue

        # 遍历任务目录中的所有JSON文件
        for msg_file in task_dir.glob("*.json"):
            try:
                with open(msg_file, encoding="utf-8") as f:
                    msg = json.load(f)
                    msg["file_path"] = str(msg_file.relative_to(repo_root))
                    messages.append(msg)
            except Exception as e:
                print(f"[WARN] 无法读取文件 {msg_file}: {e}", file=sys.stderr)

    return messages


def format_message(msg, index):
    """格式化消息显示"""
    print(f"\n{'=' * 80}")
    print(f"消息 #{index}")
    print(f"{'=' * 80}")
    print(f"消息ID:     {msg.get('msg_id', 'N/A')}")
    print(f"任务代码:   {msg.get('taskcode', 'N/A')}")
    print(f"发送方:     {msg.get('from_agent', 'N/A')}")
    print(f"接收方:     {msg.get('to_agent', 'N/A')}")
    print(f"类型:       {msg.get('kind', 'N/A')}")
    print(f"优先级:     {msg.get('priority', 'N/A')}")
    print(f"状态:       {msg.get('status', 'N/A')}")
    print(f"创建时间:   {msg.get('created_at', 'N/A')}")

    # 显示消息内容
    payload = msg.get("payload", {})
    if isinstance(payload, dict):
        print("\n消息内容:")
        if "message" in payload:
            print(f"  {payload['message']}")
        elif "text" in payload:
            print(f"  {payload['text']}")
        elif "purpose" in payload:
            print(f"  目的: {payload.get('purpose', 'N/A')}")
            if "message" in payload:
                print(f"  内容: {payload['message']}")
        else:
            # 显示所有payload字段
            for key, value in payload.items():
                if isinstance(value, str) and len(value) < 200:
                    print(f"  {key}: {value}")
                elif isinstance(value, (dict, list)):
                    print(f"  {key}: {json.dumps(value, indent=2, ensure_ascii=False)[:200]}...")
    else:
        print(f"\n消息内容: {payload}")

    # 显示SHA256
    if "sha256" in msg:
        print(f"\nSHA256:    {msg['sha256'][:64]}...")

    # 显示文件路径
    if "file_path" in msg:
        print(f"文件路径:  {msg['file_path']}")


def main():
    repo_root = Path(os.getenv("REPO_ROOT", "d:\\quantsys")).resolve()

    print("=" * 80)
    print("ATA消息列表 - 从文件系统读取所有消息")
    print("=" * 80)
    print(f"\n消息目录: {repo_root / 'docs' / 'REPORT' / 'ata' / 'messages'}")

    # 加载所有消息
    print("\n正在加载所有消息文件...")
    messages = load_all_messages(repo_root)

    if not messages:
        print("\n没有找到任何消息文件")
        return 0

    print(f"找到 {len(messages)} 条消息")

    # 按创建时间排序（最新的在前）
    messages.sort(key=lambda x: x.get("created_at", ""), reverse=True)

    # 统计信息
    from_stats = defaultdict(int)
    to_stats = defaultdict(int)
    kind_stats = defaultdict(int)
    taskcode_stats = defaultdict(int)
    conversation_stats = defaultdict(int)

    for msg in messages:
        from_agent = msg.get("from_agent", "Unknown")
        to_agent = msg.get("to_agent", "Unknown")
        kind = msg.get("kind", "Unknown")
        taskcode = msg.get("taskcode", "Unknown")

        from_stats[from_agent] += 1
        to_stats[to_agent] += 1
        kind_stats[kind] += 1
        taskcode_stats[taskcode] += 1

        # 会话统计（双向）
        conv_key1 = f"{from_agent} -> {to_agent}"
        conv_key2 = f"{to_agent} -> {from_agent}"
        conversation_stats[conv_key1] += 1

    # 显示统计信息
    print(f"\n{'=' * 80}")
    print("消息统计信息")
    print(f"{'=' * 80}")

    print("\n发送方统计:")
    for agent, cnt in sorted(from_stats.items(), key=lambda x: x[1], reverse=True):
        print(f"  {agent}: {cnt} 条")

    print("\n接收方统计:")
    for agent, cnt in sorted(to_stats.items(), key=lambda x: x[1], reverse=True):
        print(f"  {agent}: {cnt} 条")

    print("\n消息类型统计:")
    for kind, cnt in sorted(kind_stats.items(), key=lambda x: x[1], reverse=True):
        print(f"  {kind}: {cnt} 条")

    print("\n任务代码统计:")
    for taskcode, cnt in sorted(taskcode_stats.items(), key=lambda x: x[1], reverse=True):
        print(f"  {taskcode}: {cnt} 条消息")

    print("\n会话统计（按方向）:")
    for conv, cnt in sorted(conversation_stats.items(), key=lambda x: x[1], reverse=True):
        print(f"  {conv}: {cnt} 条")

    # 显示所有消息详情
    print(f"\n{'=' * 80}")
    print(f"消息详情列表（共 {len(messages)} 条，按时间倒序）")
    print(f"{'=' * 80}")

    for i, msg in enumerate(messages, 1):
        format_message(msg, i)

    print(f"\n{'=' * 80}")
    print("消息列表完成")
    print(f"{'=' * 80}")
    print(f"\n总计: {len(messages)} 条消息")
    print(f"涉及 {len(from_stats)} 个发送方")
    print(f"涉及 {len(to_stats)} 个接收方")
    print(f"涉及 {len(taskcode_stats)} 个任务")

    return 0


if __name__ == "__main__":
    sys.exit(main())
