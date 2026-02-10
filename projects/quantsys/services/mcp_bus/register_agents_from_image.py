
#!/usr/bin/env python3
"""根据图片中的编号注册/更新所有AI"""

import json
import sys

import requests


def register_agents():
    """批量注册AI"""
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

    # 根据图片中的编号注册/更新每个AI
    agents = [
        {
            "agent_id": "功能升级",
            "numeric_code": 4,
            "role": "implementer",
            "capabilities": ["feature_upgrade", "enhancement"],
        },
        {
            "agent_id": "数据模块",
            "numeric_code": 6,
            "role": "data_engineer",
            "capabilities": ["data_processing", "data_analysis"],
        },
        {
            "agent_id": "总网页与总服务器",
            "numeric_code": 5,
            "role": "infra_ops",
            "capabilities": ["web_server", "mcp_server"],
        },
        {
            "agent_id": "文档模块",
            "numeric_code": 9,
            "role": "doc_writer",
            "capabilities": ["documentation", "report_generation"],
        },
        {
            "agent_id": "交易模块",
            "numeric_code": 2,
            "role": "trading",
            "capabilities": ["trading", "backtest"],
        },
        {
            "agent_id": "FWS工程师",
            "numeric_code": 10,
            "role": "fws_engineer",
            "capabilities": ["fws", "engineering"],
        },
        {
            "agent_id": "cursor自进化",
            "numeric_code": 7,
            "role": "skill_evolution",
            "capabilities": ["skill_detection", "skill_integration"],
        },
    ]

    results = []
    for idx, agent in enumerate(agents):
        payload = {
            "jsonrpc": "2.0",
            "id": 200 + idx,
            "method": "tools/call",
            "params": {
                "name": "agent_register",
                "arguments": {
                    "agent_id": agent["agent_id"],
                    "agent_type": "AI",
                    "role": agent["role"],
                    "capabilities": agent["capabilities"],
                    "numeric_code": agent["numeric_code"],
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
                        "agent_id": agent["agent_id"],
                        "numeric_code": agent["numeric_code"],
                        "success": success,
                        "error": error,
                    }
                )
                status = "[OK]" if success else "[FAIL]"
                print(
                    f"{status} {agent['agent_id']} (#{agent['numeric_code']}): {error if error else 'OK'}"
                )
            else:
                print(
                    f"[FAIL] {agent['agent_id']} (#{agent['numeric_code']}): HTTP {resp.status_code}"
                )
                results.append(
                    {
                        "agent_id": agent["agent_id"],
                        "numeric_code": agent["numeric_code"],
                        "success": False,
                        "error": f"HTTP {resp.status_code}",
                    }
                )
        except Exception as e:
            print(f"[FAIL] {agent['agent_id']} (#{agent['numeric_code']}): {str(e)}")
            results.append(
                {
                    "agent_id": agent["agent_id"],
                    "numeric_code": agent["numeric_code"],
                    "success": False,
                    "error": str(e),
                }
            )

    # 总结
    success_count = sum(1 for r in results if r["success"])
    print(f"\n总计: {success_count}/{len(agents)} 成功")

    return success_count == len(agents)


if __name__ == "__main__":
    success = register_agents()
    sys.exit(0 if success else 1)
