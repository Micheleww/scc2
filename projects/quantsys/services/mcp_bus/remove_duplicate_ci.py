#!/usr/bin/env python3
"""删除重复的 ci完备（小写），保留 CI完备（大写，系统AI）"""

import json
from pathlib import Path


def remove_duplicate():
    """删除重复的 ci完备"""
    repo_root = Path("d:/quantsys")
    registry_file = repo_root / ".cursor" / "agent_registry.json"

    with open(registry_file, encoding="utf-8") as f:
        data = json.load(f)

    agents = data["agents"]
    roles = data["roles"]

    print("删除前:")
    if "ci完备" in agents:
        print(
            f"  ci完备: numeric_code={agents['ci完备'].get('numeric_code')}, category={agents['ci完备'].get('category')}"
        )
    if "CI完备" in agents:
        print(
            f"  CI完备: numeric_code={agents['CI完备'].get('numeric_code')}, category={agents['CI完备'].get('category')}"
        )

    # 删除小写的 ci完备
    if "ci完备" in agents:
        del agents["ci完备"]
        print("已删除 ci完备（小写）")

    # 更新 roles 索引
    if "infra_quality" in roles:
        roles["infra_quality"]["agents"] = [
            a for a in roles["infra_quality"]["agents"] if a != "ci完备" and a in agents
        ]
        roles["infra_quality"]["total_capacity"] = sum(
            agents[a].get("max_concurrent_tasks", 5)
            for a in roles["infra_quality"]["agents"]
            if a in agents
        )
        roles["infra_quality"]["available_capacity"] = roles["infra_quality"]["total_capacity"]

    with open(registry_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("保留 CI完备（大写，系统AI，numeric_code=3）")
    print("删除完成")


if __name__ == "__main__":
    remove_duplicate()
