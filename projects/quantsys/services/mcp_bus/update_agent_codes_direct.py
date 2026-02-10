#!/usr/bin/env python3
"""直接修改注册表文件，调整编号冲突"""

import json
from pathlib import Path


def update_agent_codes():
    """直接修改注册表文件"""
    repo_root = Path("d:/quantsys")
    registry_file = repo_root / ".cursor" / "agent_registry.json"

    # 读取注册表
    with open(registry_file, encoding="utf-8") as f:
        data = json.load(f)

    agents = data.get("agents", {})

    # 调整编号冲突
    # 1. Cursor-Auto: 4 -> 11 (功能升级需要4)
    if "Cursor-Auto" in agents:
        agents["Cursor-Auto"]["numeric_code"] = 11
        print("[UPDATE] Cursor-Auto: 4 -> 11")

    # 2. ci完备: 5 -> 11 (总网页与总服务器需要5)
    if "ci完备" in agents:
        agents["ci完备"]["numeric_code"] = 11
        print("[UPDATE] ci完备: 5 -> 11")

    # 3. NewAgentY: 2 -> 11 (交易模块需要2)
    if "NewAgentY" in agents:
        agents["NewAgentY"]["numeric_code"] = 11
        print("[UPDATE] NewAgentY: 2 -> 11")

    # 4. NewAgentX: 33 -> 11 (清理测试Agent)
    if "NewAgentX" in agents:
        agents["NewAgentX"]["numeric_code"] = 11
        print("[UPDATE] NewAgentX: 33 -> 11")

    # 保存注册表
    with open(registry_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("[OK] 注册表已更新")
    return True


if __name__ == "__main__":
    update_agent_codes()
