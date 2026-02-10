#!/usr/bin/env python3
"""
列举所有ATA消息（发送和接收）
"""

import io
import json
import os
import sys

import requests

# 设置标准输出编码为UTF-8（Windows兼容）
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE_URL = os.getenv("MCP_BUS_URL", "http://127.0.0.1:18788/")


def call_mcp_tool(tool_name, arguments):
    """调用MCP工具"""
    url = f"{BASE_URL}/mcp"
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        result = response.json()

        if "result" in result:
            if "content" in result["result"]:
                content = result["result"]["content"][0]
                if "text" in content:
                    try:
                        return json.loads(content["text"])
                    except:
                        return {"raw": content["text"]}
            return result["result"]
        elif "error" in result:
            return {"success": False, "error": result["error"]}

        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


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
        else:
            print(f"  {json.dumps(payload, indent=2, ensure_ascii=False)}")
    else:
        print(f"\n消息内容: {payload}")

    # 显示SHA256
    if "sha256" in msg:
        print(f"\nSHA256:    {msg['sha256']}")

    # 显示文件路径
    if "file_path" in msg:
        print(f"文件路径:  {msg['file_path']}")

    # 显示上下文信息
    if "context" in msg:
        context = msg["context"]
        print("\n上下文信息:")
        print(f"  会话状态: {context.get('conversation_status', 'N/A')}")
        print(f"  参与者:   {', '.join(context.get('participants', []))}")
        print(f"  消息索引: {context.get('message_index', 'N/A')}")


def main():
    print("=" * 80)
    print("ATA消息列表 - 所有发送和接收的消息")
    print("=" * 80)

    # 获取所有消息（不限制接收方，不限制发送方，包括已读和未读）
    print("\n正在获取所有消息...")
    result = call_mcp_tool(
        "ata_receive",
        {
            "unread_only": False  # 获取所有消息，包括已读的
        },
    )

    if not result.get("success"):
        print(f"\n[ERROR] 获取消息失败: {result.get('error', '未知错误')}")
        print("\n完整响应:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 1

    messages = result.get("messages", [])
    count = result.get("count", 0)
    statistics = result.get("statistics", {})

    print(f"\n找到 {count} 条消息")

    if statistics:
        print("\n统计信息:")
        print(f"  总计: {statistics.get('total', 0)}")
        print(f"  未读: {statistics.get('unread_count', 0)}")

        by_priority = statistics.get("by_priority", {})
        if by_priority:
            print("\n  按优先级:")
            for priority, cnt in by_priority.items():
                print(f"    {priority}: {cnt}")

        by_status = statistics.get("by_status", {})
        if by_status:
            print("\n  按状态:")
            for status, cnt in by_status.items():
                print(f"    {status}: {cnt}")

    if not messages:
        print("\n没有找到任何消息")
        return 0

    # 按创建时间排序（最新的在前）
    messages.sort(key=lambda x: x.get("created_at", ""), reverse=True)

    # 按发送方和接收方分组统计
    print(f"\n{'=' * 80}")
    print("消息分组统计")
    print(f"{'=' * 80}")

    from_stats = {}
    to_stats = {}
    conversation_stats = {}

    for msg in messages:
        from_agent = msg.get("from_agent", "Unknown")
        to_agent = msg.get("to_agent", "Unknown")
        taskcode = msg.get("taskcode", "Unknown")

        # 统计发送方
        if from_agent not in from_stats:
            from_stats[from_agent] = 0
        from_stats[from_agent] += 1

        # 统计接收方
        if to_agent not in to_stats:
            to_stats[to_agent] = 0
        to_stats[to_agent] += 1

        # 统计会话
        conv_key = f"{from_agent} <-> {to_agent} ({taskcode})"
        if conv_key not in conversation_stats:
            conversation_stats[conv_key] = 0
        conversation_stats[conv_key] += 1

    print("\n发送方统计:")
    for agent, cnt in sorted(from_stats.items(), key=lambda x: x[1], reverse=True):
        print(f"  {agent}: {cnt} 条")

    print("\n接收方统计:")
    for agent, cnt in sorted(to_stats.items(), key=lambda x: x[1], reverse=True):
        print(f"  {agent}: {cnt} 条")

    print("\n会话统计:")
    for conv, cnt in sorted(conversation_stats.items(), key=lambda x: x[1], reverse=True):
        print(f"  {conv}: {cnt} 条消息")

    # 显示所有消息详情
    print(f"\n{'=' * 80}")
    print(f"消息详情列表（共 {len(messages)} 条，按时间倒序）")
    print(f"{'=' * 80}")

    for i, msg in enumerate(messages, 1):
        format_message(msg, i)

    print(f"\n{'=' * 80}")
    print("消息列表完成")
    print(f"{'=' * 80}")
    print("\n提示:")
    print(f"  - 可以在 {BASE_URL}/viewer 查看Web界面")
    print(f"  - 可以在 {BASE_URL}/collaboration 查看Agent协作状态")

    return 0


if __name__ == "__main__":
    sys.exit(main())
