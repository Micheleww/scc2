#!/usr/bin/env python3
"""最终完成Agent注册，确保图片中的编号对应"""

import json
from datetime import datetime
from pathlib import Path


def finalize_registry():
    """完成注册表更新"""
    repo_root = Path("d:/quantsys")
    registry_file = repo_root / ".cursor" / "agent_registry.json"

    # 读取注册表
    with open(registry_file, encoding="utf-8") as f:
        data = json.load(f)

    agents = data["agents"]
    roles = data["roles"]

    # 1. 删除测试Agent
    if "NewAgentX" in agents:
        del agents["NewAgentX"]
    if "NewAgentY" in agents:
        del agents["NewAgentY"]

    # 2. 调整冲突编号
    agents["Cursor-Auto"]["numeric_code"] = 11
    agents["ci完备"]["numeric_code"] = 12

    # 3. 添加缺失的Agent
    now = datetime.utcnow().isoformat() + "Z"

    agents["交易模块"] = {
        "agent_id": "交易模块",
        "agent_type": "AI",
        "role": "trading",
        "capabilities": ["trading", "backtest"],
        "current_load": 0,
        "max_concurrent_tasks": 5,
        "status": "available",
        "registered_at": now,
        "last_heartbeat": now,
        "numeric_code": 2,
        "send_enabled": True,
        "response_time_avg": 0.0,
        "success_rate": 1.0,
        "total_tasks": 0,
        "completed_tasks": 0,
    }

    agents["功能升级"] = {
        "agent_id": "功能升级",
        "agent_type": "AI",
        "role": "implementer",
        "capabilities": ["feature_upgrade", "enhancement"],
        "current_load": 0,
        "max_concurrent_tasks": 5,
        "status": "available",
        "registered_at": now,
        "last_heartbeat": now,
        "numeric_code": 4,
        "send_enabled": True,
        "response_time_avg": 0.0,
        "success_rate": 1.0,
        "total_tasks": 0,
        "completed_tasks": 0,
    }

    agents["总网页与总服务器"] = {
        "agent_id": "总网页与总服务器",
        "agent_type": "AI",
        "role": "infra_ops",
        "capabilities": ["web_server", "mcp_server"],
        "current_load": 0,
        "max_concurrent_tasks": 5,
        "status": "available",
        "registered_at": now,
        "last_heartbeat": now,
        "numeric_code": 5,
        "send_enabled": True,
        "response_time_avg": 0.0,
        "success_rate": 1.0,
        "total_tasks": 0,
        "completed_tasks": 0,
    }

    # 4. 更新roles索引
    # 清理implementer角色
    if "implementer" in roles:
        roles["implementer"]["agents"] = [
            a for a in roles["implementer"]["agents"] if a not in ["NewAgentX"] and a in agents
        ]
        if "功能升级" not in roles["implementer"]["agents"]:
            roles["implementer"]["agents"].append("功能升级")
        roles["implementer"]["total_capacity"] = sum(
            agents[a].get("max_concurrent_tasks", 5)
            for a in roles["implementer"]["agents"]
            if a in agents
        )
        roles["implementer"]["available_capacity"] = roles["implementer"]["total_capacity"]

    # 清理reviewer角色
    if "reviewer" in roles:
        roles["reviewer"]["agents"] = [
            a for a in roles["reviewer"]["agents"] if a not in ["NewAgentY"] and a in agents
        ]
        roles["reviewer"]["total_capacity"] = (
            sum(
                agents[a].get("max_concurrent_tasks", 5)
                for a in roles["reviewer"]["agents"]
                if a in agents
            )
            if roles["reviewer"]["agents"]
            else 0
        )
        roles["reviewer"]["available_capacity"] = roles["reviewer"]["total_capacity"]

    # 添加新角色
    roles["trading"] = {"agents": ["交易模块"], "total_capacity": 5, "available_capacity": 5}

    roles["infra_ops"] = {
        "agents": ["总网页与总服务器"],
        "total_capacity": 5,
        "available_capacity": 5,
    }

    # 保存注册表
    with open(registry_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # 打印编号映射
    print("编号映射:")
    mapping = sorted(
        [
            (name, agent.get("numeric_code"))
            for name, agent in agents.items()
            if agent.get("numeric_code")
        ],
        key=lambda x: x[1],
    )
    for name, code in mapping:
        print(f"  {name}: #{code}")

    print("\n完成！所有Agent已按图片中的编号注册。")


if __name__ == "__main__":
    finalize_registry()
