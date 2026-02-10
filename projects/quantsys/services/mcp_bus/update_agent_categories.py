#!/usr/bin/env python3
"""更新现有Agent的category字段"""

import json
from pathlib import Path


def update_categories():
    """更新category字段"""
    repo_root = Path("d:/quantsys")
    registry_file = repo_root / ".cursor" / "agent_registry.json"

    with open(registry_file, encoding="utf-8") as f:
        data = json.load(f)

    agents = data["agents"]
    updated = 0

    for k, a in agents.items():
        if "category" not in a:
            nc = a.get("numeric_code")
            if nc is not None and 1 <= nc <= 10:
                a["category"] = "system_ai"
            else:
                a["category"] = "user_ai"
            updated += 1

    with open(registry_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Updated {updated} agents with category field")
    return updated


if __name__ == "__main__":
    update_categories()
