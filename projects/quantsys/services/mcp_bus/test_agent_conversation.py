#!/usr/bin/env python3
"""
Agent对话测试工具
用于测试两个注册的Agent之间的ATA消息通信
"""

import io
import json
import os
import sys
from typing import Any

import requests

# 设置标准输出编码为UTF-8（Windows兼容）
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE_URL = os.getenv("MCP_BUS_URL", "http://127.0.0.1:18788/")


def send_ata_message(
    taskcode: str,
    from_agent: str,
    to_agent: str,
    message: str,
    kind: str = "request",
    priority: str = "normal",
    requires_response: bool = True,
    prev_sha256: str | None = None,
) -> dict[str, Any]:
    """发送ATA消息"""
    url = f"{BASE_URL}/mcp"

    arguments = {
        "taskcode": taskcode,
        "from_agent": from_agent,
        "to_agent": to_agent,
        "kind": kind,
        "payload": {"message": message, "text": message},
        "priority": priority,
        "requires_response": requires_response,
    }

    if prev_sha256:
        arguments["prev_sha256"] = prev_sha256

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "ata_send", "arguments": arguments},
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()

        result = response.json()

        if "result" in result:
            if "content" in result["result"]:
                content = result["result"]["content"][0]
                if "text" in content:
                    return json.loads(content["text"])
            return result["result"]
        elif "error" in result:
            return {"success": False, "error": result["error"]}

        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


def receive_ata_message(
    to_agent: str,
    from_agent: str | None = None,
    taskcode: str | None = None,
    unread_only: bool = True,
    limit: int = 10,
) -> dict[str, Any]:
    """接收ATA消息"""
    url = f"{BASE_URL}/mcp"

    arguments = {"to_agent": to_agent, "unread_only": unread_only, "limit": limit}

    if from_agent:
        arguments["from_agent"] = from_agent
    if taskcode:
        arguments["taskcode"] = taskcode

    payload = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": "ata_receive", "arguments": arguments},
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()

        result = response.json()

        if "result" in result:
            if "content" in result["result"]:
                content = result["result"]["content"][0]
                if "text" in content:
                    return json.loads(content["text"])
            return result["result"]
        elif "error" in result:
            return {"success": False, "error": result["error"]}

        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


def test_conversation(agent1: str, agent2: str, taskcode: str = "TEST-CONV-001"):
    """测试两个Agent之间的对话"""
    print("=" * 60)
    print(f"Agent对话测试: {agent1} <-> {agent2}")
    print("=" * 60)
    print(f"任务代码: {taskcode}")
    print()

    # Agent1发送消息给Agent2
    # 按 ATA 通信规则：正文必须以 @对方#NN 开头（此处按当前系统约定：结构设计师#08、ATA系统#01）
    print(f"[{agent1}] -> [{agent2}]: @结构设计师#08 你好，我是{agent1}，我们可以开始对话吗？")
    result1 = send_ata_message(
        taskcode=taskcode,
        from_agent=agent1,
        to_agent=agent2,
        message=f"@结构设计师#08 你好，我是{agent1}，我们可以开始对话吗？",
        kind="request",
    )

    if result1.get("success"):
        print(f"[OK] 消息发送成功: msg_id={result1.get('msg_id')}")
    else:
        print(f"[ERROR] 消息发送失败: {result1.get('error')}")
        return False

    print()

    # Agent2接收消息
    print(f"[{agent2}] 检查新消息...")
    result2 = receive_ata_message(
        to_agent=agent2, from_agent=agent1, taskcode=taskcode, unread_only=True
    )

    if result2.get("success"):
        messages = result2.get("messages", [])
        if messages:
            msg = messages[0]
            print(f"[OK] 收到消息: msg_id={msg.get('msg_id')}")
            payload = msg.get("payload", {})
            print(f"   内容: {payload.get('message', payload.get('text', ''))}")

            # Agent2回复
            print()
            print(
                f"[{agent2}] -> [{agent1}]: @ATA系统#01 你好{agent1}，我是{agent2}，很高兴与你对话！"
            )
            # 获取前一条消息的SHA256
            prev_sha256 = msg.get("sha256") if "sha256" in msg else None

            result3 = send_ata_message(
                taskcode=taskcode,
                from_agent=agent2,
                to_agent=agent1,
                message=f"@ATA系统#01 你好{agent1}，我是{agent2}，很高兴与你对话！",
                kind="response",
            )

            if result3.get("success"):
                print(f"[OK] 回复发送成功: msg_id={result3.get('msg_id')}")

                # Agent1接收回复
                print()
                print(f"[{agent1}] 检查新消息...")
                result4 = receive_ata_message(
                    to_agent=agent1, from_agent=agent2, taskcode=taskcode, unread_only=True
                )

                if result4.get("success"):
                    messages2 = result4.get("messages", [])
                    if messages2:
                        msg2 = messages2[0]
                        print(f"[OK] 收到回复: msg_id={msg2.get('msg_id')}")
                        payload2 = msg2.get("payload", {})
                        print(f"   内容: {payload2.get('message', payload2.get('text', ''))}")
                        print()
                        print("[OK] 对话测试成功！")
                        return True
                    else:
                        print("[WARN] 没有收到回复消息")
                        return False
                else:
                    print(f"[ERROR] 接收回复失败: {result4.get('error')}")
                    return False
            else:
                print(f"[ERROR] 回复发送失败: {result3.get('error')}")
                return False
        else:
            print("[WARN] 没有收到消息")
            return False
    else:
        print(f"[ERROR] 接收消息失败: {result2.get('error')}")
        return False


def main():
    """主函数"""
    if len(sys.argv) < 3:
        print("用法: python test_agent_conversation.py <agent1_id> <agent2_id> [taskcode]")
        print("\n示例:")
        print('  python test_agent_conversation.py "ATA系统" "结构设计师"')
        print('  python test_agent_conversation.py "ATA系统" "结构设计师" "TEST-001"')
        sys.exit(1)

    agent1 = sys.argv[1]
    agent2 = sys.argv[2]
    taskcode = sys.argv[3] if len(sys.argv) > 3 else "TEST-CONV-001"

    success = test_conversation(agent1, agent2, taskcode)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
