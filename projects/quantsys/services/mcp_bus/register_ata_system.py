#!/usr/bin/env python3
"""
注册ATA系统为Agent
"""

import json
import sys

import requests

BASE_URL = "http://127.0.0.1:18788/"


def register_agent():
    """注册ATA系统Agent"""
    # 使用MCP tools/call接口
    url = f"{BASE_URL}/mcp"

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "agent_register",
            "arguments": {
                "agent_id": "ATA系统",
                "agent_type": "ATA",
                "role": "system",
                "capabilities": [
                    "ata_communication",
                    "agent_coordination",
                    "workflow_management",
                    "task_orchestration",
                    "message_routing",
                    "system_monitoring",
                ],
                "max_concurrent_tasks": 10,
            },
        },
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()

        result = response.json()

        if "result" in result:
            # 提取实际结果
            if "content" in result["result"]:
                content = result["result"]["content"][0]
                if "text" in content:
                    result_data = json.loads(content["text"])
                    return result_data
            return result["result"]
        elif "error" in result:
            return {"success": False, "error": result["error"]}

        return result
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": str(e)}
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"JSON解析失败: {str(e)}"}


def main():
    """主函数"""
    print("=" * 60)
    print("注册ATA系统为Agent")
    print("=" * 60)

    result = register_agent()

    if result.get("success"):
        print("\n[OK] 注册成功！")
        print("\nAgent信息:")
        print(f"  Agent ID: {result.get('agent_id', 'ATA系统')}")
        print(f"  角色: {result.get('role', 'system')}")
        print(f"  状态: {result.get('status', 'available')}")
    else:
        print(f"\n[ERROR] 注册失败: {result.get('error', '未知错误')}")
        print("\n完整响应:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
