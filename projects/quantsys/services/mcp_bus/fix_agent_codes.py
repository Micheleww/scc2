#!/usr/bin/env python3
"""修复Agent编号冲突，确保图片中的编号对应"""

import json
import sys

import requests


def fix_agent_codes():
    """修复编号冲突"""
    session = requests.Session()

    # 管理员登录
    login_resp = session.post(
        "http://127.0.0.1:18788/api/auth/login",
        json={"username": "admin", "password": "admin123"},
        timeout=10,
    )
    if login_resp.status_code != 200:
        print(f"ERROR: Login failed: {login_resp.status_code}")
        return False

    # 图片中的编号映射（agent_id -> numeric_code）
    target_mapping = {
        "ATA系统": 1,
        "交易模块": 2,
        "CI完备": 3,
        "功能升级": 4,
        "总网页与总服务器": 5,
        "数据模块": 6,
        "cursor自进化": 7,
        "结构设计师": 8,
        "文档模块": 9,
        "FWS工程师": 10,
    }

    # 先删除测试Agent（NewAgentX, NewAgentY），释放编号
    test_agents = ["NewAgentX", "NewAgentY"]
    for agent_id in test_agents:
        # 注意：当前系统可能没有删除API，先跳过
        print(f"[SKIP] 测试Agent {agent_id} 需要手动清理")

    # 更新/注册每个Agent
    results = []
    for agent_id, numeric_code in target_mapping.items():
        # 根据agent_id确定role和capabilities
        role_map = {
            "ATA系统": ("implementer", ["coding", "testing", "debugging"]),
            "交易模块": ("trading", ["trading", "backtest"]),
            "CI完备": ("infra_quality", ["ci_enforcement", "evidence_triplet", "guard_gate"]),
            "功能升级": ("implementer", ["feature_upgrade", "enhancement"]),
            "总网页与总服务器": ("infra_ops", ["web_server", "mcp_server"]),
            "数据模块": ("data_engineer", ["data_processing", "data_analysis"]),
            "cursor自进化": ("skill_evolution", ["skill_detection", "skill_integration"]),
            "结构设计师": ("designer", ["design", "structure_design", "planning"]),
            "文档模块": ("doc_writer", ["documentation", "report_generation"]),
            "FWS工程师": ("fws_engineer", ["fws", "engineering"]),
        }

        role, capabilities = role_map.get(agent_id, ("implementer", ["general"]))

        payload = {
            "jsonrpc": "2.0",
            "id": 300,
            "method": "tools/call",
            "params": {
                "name": "agent_register",
                "arguments": {
                    "agent_id": agent_id,
                    "agent_type": "AI",
                    "role": role,
                    "capabilities": capabilities,
                    "numeric_code": numeric_code,
                    "send_enabled": True,
                },
            },
        }

        try:
            resp = session.post("http://127.0.0.1:18788/mcp", json=payload, timeout=10)
            if resp.status_code == 200:
                result_text = resp.json()["result"]["content"][0]["text"]
                result = json.loads(result_text)
                success = result.get("success", False)
                error = result.get("error", "")
                results.append(
                    {
                        "agent_id": agent_id,
                        "numeric_code": numeric_code,
                        "success": success,
                        "error": error,
                    }
                )
                status = "[OK]" if success else "[FAIL]"
                print(f"{status} {agent_id} (#{numeric_code}): {error if error else 'OK'}")
            else:
                print(f"[FAIL] {agent_id} (#{numeric_code}): HTTP {resp.status_code}")
                results.append(
                    {
                        "agent_id": agent_id,
                        "numeric_code": numeric_code,
                        "success": False,
                        "error": f"HTTP {resp.status_code}",
                    }
                )
        except Exception as e:
            print(f"[FAIL] {agent_id} (#{numeric_code}): {str(e)}")
            results.append(
                {
                    "agent_id": agent_id,
                    "numeric_code": numeric_code,
                    "success": False,
                    "error": str(e),
                }
            )

    # 总结
    success_count = sum(1 for r in results if r["success"])
    print(f"\n总计: {success_count}/{len(target_mapping)} 成功")

    # 检查编号冲突
    if success_count < len(target_mapping):
        print("\n注意：部分Agent注册失败，可能是编号冲突。")
        print("需要手动处理：")
        print("1. 删除测试Agent（NewAgentX, NewAgentY）")
        print("2. 调整 Cursor-Auto 的编号（当前4，功能升级需要4）")
        print("3. 调整 ci完备 的编号（当前5，总网页与总服务器需要5）")

    return success_count == len(target_mapping)


if __name__ == "__main__":
    success = fix_agent_codes()
    sys.exit(0 if success else 1)
