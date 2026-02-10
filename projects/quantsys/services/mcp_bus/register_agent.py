#!/usr/bin/env python3
"""
统一的Agent注册工具
供AI使用，可以快速注册Agent到ATA协作系统
"""

import json
import os
import sys
from typing import Any

import requests

BASE_URL = os.getenv("MCP_BUS_URL", "http://127.0.0.1:18788/")


def register_agent(
    agent_id: str,
    agent_type: str = "AI",
    role: str = "general",
    capabilities: list | None = None,
    max_concurrent_tasks: int = 5,
    dialog_name: str | None = None,
    numeric_code: int | None = None,
) -> dict[str, Any]:
    """
    注册Agent到ATA协作系统

    Args:
        agent_id: Agent ID（唯一标识）
        agent_type: Agent类型（如：AI, Cursor, GPT, TRAE, ATA等）
        role: Agent角色（如：general, system, researcher, architect, implementer等）
        capabilities: Agent能力列表（如：["coding", "design", "research"]）
        max_concurrent_tasks: 最大并发任务数（默认5）
        dialog_name: 对话框名称（可选，用于描述）
        numeric_code: 数字编码（1-100，可选，不指定则自动分配）

    Returns:
        注册结果字典
    """
    if capabilities is None:
        # 根据角色设置默认能力
        default_capabilities = {
            "general": ["general_assistance", "question_answering"],
            "system": ["system_management", "coordination"],
            "researcher": ["research", "analysis", "documentation"],
            "architect": ["design", "architecture", "planning"],
            "implementer": ["coding", "implementation", "testing"],
            "designer": ["design", "structure_design", "planning"],
        }
        capabilities = default_capabilities.get(role, ["general_assistance"])

    url = f"{BASE_URL}/mcp"

    # 1. 注册到Agent Coordinator
    arguments = {
        "agent_id": agent_id,
        "agent_type": agent_type,
        "role": role,
        "capabilities": capabilities,
        "max_concurrent_tasks": max_concurrent_tasks,
    }

    # 只在numeric_code不为None时才添加
    if numeric_code is not None:
        arguments["numeric_code"] = numeric_code

    payload_agent = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "agent_register", "arguments": arguments},
    }

    try:
        response = requests.post(url, json=payload_agent, timeout=10)
        response.raise_for_status()

        result = response.json()

        agent_result = {}
        if "result" in result:
            if "content" in result["result"]:
                content = result["result"]["content"][0]
                if "text" in content:
                    agent_result = json.loads(content["text"])
            else:
                agent_result = result["result"]
        elif "error" in result:
            return {"success": False, "error": f"Agent注册失败: {result['error']}"}

        # 2. 注册到Dialog Registry（可选）
        dialog_result = None
        if dialog_name:
            payload_dialog = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "dialog_register",
                    "arguments": {
                        "agent_type": agent_type,
                        "dialog_name": dialog_name,
                        "dialog_id": agent_id,  # 使用相同的ID
                    },
                },
            }

            try:
                response_dialog = requests.post(url, json=payload_dialog, timeout=10)
                response_dialog.raise_for_status()
                result_dialog = response_dialog.json()

                if "result" in result_dialog:
                    if "content" in result_dialog["result"]:
                        content = result_dialog["result"]["content"][0]
                        if "text" in content:
                            dialog_result = json.loads(content["text"])
            except Exception:
                # Dialog注册失败不影响Agent注册
                pass

        # 合并结果
        final_result = {
            "success": agent_result.get("success", False),
            "agent_id": agent_id,
            "numeric_code": agent_result.get("numeric_code"),
            "role": role,
            "status": agent_result.get("status", "unknown"),
            "agent_registered": agent_result.get("success", False),
            "dialog_registered": dialog_result.get("success", False) if dialog_result else None,
        }

        return final_result

    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"请求失败: {str(e)}"}
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"JSON解析失败: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": f"注册失败: {str(e)}"}


def main():
    """命令行入口"""
    if len(sys.argv) < 2:
        print("用法: python register_agent.py <agent_id> [agent_type] [role] [capabilities...]")
        print("\n示例:")
        print(
            '  python register_agent.py "结构设计师" AI architect design structure_design planning'
        )
        print('  python register_agent.py "ATA系统" ATA system')
        print('  python register_agent.py "研究员" AI researcher research analysis documentation')
        sys.exit(1)

    agent_id = sys.argv[1]
    agent_type = sys.argv[2] if len(sys.argv) > 2 else "AI"
    role = sys.argv[3] if len(sys.argv) > 3 else "general"
    capabilities = sys.argv[4:] if len(sys.argv) > 4 else None

    print("=" * 60)
    print(f"注册Agent: {agent_id}")
    print("=" * 60)
    print(f"  Agent ID: {agent_id}")
    print(f"  类型: {agent_type}")
    print(f"  角色: {role}")
    if capabilities:
        print(f"  能力: {', '.join(capabilities)}")
    print()

    result = register_agent(
        agent_id=agent_id,
        agent_type=agent_type,
        role=role,
        capabilities=capabilities,
        dialog_name=agent_id,
    )

    if result.get("success"):
        print("[OK] 注册成功！")
        print("\nAgent信息:")
        print(f"  Agent ID: {result.get('agent_id')}")
        if result.get("numeric_code"):
            print(f"  数字编码: {result.get('numeric_code')}")
        print(f"  角色: {result.get('role')}")
        print(f"  状态: {result.get('status')}")
        if result.get("dialog_registered") is not None:
            print(f"  Dialog注册: {'成功' if result.get('dialog_registered') else '失败'}")
        print(f"\n现在可以在协作界面查看此Agent: {BASE_URL}/collaboration")
        return 0
    else:
        print(f"[ERROR] 注册失败: {result.get('error', '未知错误')}")
        print("\n完整响应:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
