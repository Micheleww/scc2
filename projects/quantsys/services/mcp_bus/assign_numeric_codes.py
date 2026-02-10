
#!/usr/bin/env python3
"""
为已注册的Agent分配数字编码
"""

import json
import sys
from pathlib import Path


def assign_numeric_codes():
    """为现有Agent分配数字编码"""
    repo_root = Path(__file__).parent.parent.parent
    registry_file = repo_root / ".cursor" / "agent_registry.json"

    if not registry_file.exists():
        print(f"[ERROR] 注册表文件不存在: {registry_file}")
        return 1

    # 读取注册表
    with open(registry_file, encoding="utf-8") as f:
        data = json.load(f)

    agents_data = data.get("agents", {})

    # 找出没有数字编码的Agent
    agents_without_code = []
    used_codes = set()

    for agent_id, agent_info in agents_data.items():
        if agent_info.get("numeric_code") is None:
            agents_without_code.append(agent_id)
        else:
            used_codes.add(agent_info["numeric_code"])

    if not agents_without_code:
        print("[OK] 所有Agent都已分配数字编码")
        return 0

    print(f"[INFO] 找到 {len(agents_without_code)} 个未分配数字编码的Agent")

    # 为每个Agent分配编码
    next_code = 1
    assigned = 0

    for agent_id in agents_without_code:
        # 找到下一个可用的编码
        while next_code in used_codes and next_code <= 100:
            next_code += 1

        if next_code > 100:
            print("[ERROR] 已达到最大Agent数量限制（100）")
            break

        # 分配编码
        agents_data[agent_id]["numeric_code"] = next_code
        used_codes.add(next_code)
        print(f"[OK] {agent_id} -> 数字编码: {next_code}")
        assigned += 1
        next_code += 1

    # 保存注册表
    data["agents"] = agents_data
    with open(registry_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n[OK] 成功为 {assigned} 个Agent分配了数字编码")
    return 0


if __name__ == "__main__":
    sys.exit(assign_numeric_codes())
