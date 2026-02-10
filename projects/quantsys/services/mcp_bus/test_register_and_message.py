#!/usr/bin/env python3
"""
测试注册和消息发送接收
"""

import io
import json
import os
import sys
from datetime import datetime

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


def main():
    print("=" * 60)
    print("测试注册和消息发送接收")
    print("=" * 60)

    # 1. 注册"结构设计师"
    print("\n[1/4] 注册Agent: 结构设计师")
    register_result = call_mcp_tool(
        "agent_register",
        {
            "agent_id": "结构设计师",
            "agent_type": "AI",
            "role": "designer",
            "capabilities": ["design", "structure_design", "planning"],
            "max_concurrent_tasks": 5,
        },
    )

    print(f"注册结果: {json.dumps(register_result, indent=2, ensure_ascii=False)}")

    # 2. 发送消息给"ATA系统"
    print("\n[2/4] 发送消息给ATA系统")
    taskcode = f"TEST-MSG-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    send_result = call_mcp_tool(
        "ata_send",
        {
            "from_agent": "结构设计师",
            "to_agent": "ATA系统",
            "taskcode": taskcode,
            "kind": "message",
            "payload": {
                "message": "你好，ATA系统！我是结构设计师，已成功注册到ATA协作系统。",
                "purpose": "测试消息发送和接收功能",
                "timestamp": datetime.now().isoformat() + "Z",
            },
            "priority": "normal",
        },
    )

    print(f"发送结果: {json.dumps(send_result, indent=2, ensure_ascii=False)}")

    # 3. 以"结构设计师"身份接收消息
    print("\n[3/4] 接收消息（作为结构设计师）")
    receive_result1 = call_mcp_tool("ata_receive", {"to_agent": "结构设计师", "unread_only": True})

    print(f"接收结果: {json.dumps(receive_result1, indent=2, ensure_ascii=False)}")

    # 4. 以"ATA系统"身份接收消息
    print("\n[4/4] 接收消息（作为ATA系统）")
    receive_result2 = call_mcp_tool(
        "ata_receive", {"to_agent": "ATA系统", "from_agent": "结构设计师", "unread_only": True}
    )

    print(f"接收结果: {json.dumps(receive_result2, indent=2, ensure_ascii=False)}")

    if receive_result2.get("success") and receive_result2.get("count", 0) > 0:
        print("\n[OK] 成功接收到消息！")
        messages = receive_result2.get("messages", [])
        for i, msg in enumerate(messages[:3], 1):
            print(f"\n消息 {i}:")
            print(f"  消息ID: {msg.get('msg_id', 'N/A')}")
            print(f"  来自: {msg.get('from_agent', 'N/A')}")
            print(f"  内容: {msg.get('payload', {}).get('message', 'N/A')}")
    else:
        print("\n[WARN] 未接收到消息")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
