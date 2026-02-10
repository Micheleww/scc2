#!/usr/bin/env python3
"""验证Agent编号是否与图片中的编号对应"""

import json
from pathlib import Path


def verify_codes():
    """验证编号映射"""
    repo_root = Path("d:/quantsys")
    registry_file = repo_root / ".cursor" / "agent_registry.json"

    with open(registry_file, encoding="utf-8") as f:
        data = json.load(f)

    agents = data["agents"]

    # 图片中的目标映射
    target = {
        1: "ATA系统",
        2: "交易模块",
        3: "CI完备",
        4: "功能升级",
        5: "总网页与总服务器",
        6: "数据模块",
        7: "cursor自进化",
        8: "结构设计师",
        9: "文档模块",
        10: "FWS工程师",
    }

    print("图片中的Agent编号验证:")
    all_ok = True

    for code, name in target.items():
        actual = [k for k, a in agents.items() if a.get("numeric_code") == code]
        if name in actual:
            print(f"[OK] #{code}: {name}")
        else:
            print(f"[FAIL] #{code}: {name} (实际: {actual})")
            all_ok = False

    print("\n" + ("所有Agent编号已正确对应！" if all_ok else "部分Agent编号需要调整"))

    return all_ok


if __name__ == "__main__":
    verify_codes()
