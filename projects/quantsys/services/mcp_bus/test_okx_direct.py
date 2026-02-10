#!/usr/bin/env python3
"""
直接测试OKX API连接（不使用缓存）
"""

import json
import sys
import urllib.request
from pathlib import Path

# 添加scripts目录到路径
repo_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(repo_root / "scripts" / "dashboard"))

from data_access import DataAccess


def test_direct_connection():
    """直接测试OKX连接"""
    print("=== 直接测试OKX API连接 ===\n")

    # 1. 测试公开API（不使用缓存）
    print("1. 测试公开API连接...")
    try:
        url = "https://www.okx.com/api/v5/market/tickers?instType=SPOT&limit=1"
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Mozilla/5.0")

        with urllib.request.urlopen(req, timeout=15) as resp:
            status = resp.status
            body = resp.read().decode("utf-8")
            data = json.loads(body)

            if status == 200 and data.get("code") == "0":
                print("   [OK] 公开API连接成功")
                print(f"   状态码: {status}")
                print(f"   响应代码: {data.get('code')}")
                print(f"   数据: {len(data.get('data', []))} 条记录")
            else:
                print(f"   [WARN] 状态码: {status}, 响应: {data.get('msg', 'N/A')}")
    except Exception as e:
        print(f"   [ERROR] 连接失败: {e}")
        import traceback

        traceback.print_exc()

    # 2. 测试私有API
    print("\n2. 测试私有API连接...")
    da = DataAccess()
    creds = da.get_exchange_credentials()

    if not creds["key"] or not creds["secret"] or not creds["passphrase"]:
        print("   [ERROR] 凭据缺失")
        return

    print(f"   [INFO] 使用API Key: {creds['key'][:20]}...")

    # 清除缓存
    da._invalidate_cache(["okx_private_status"])

    try:
        status = da.get_okx_private_status()
        print(f"   [INFO] 私有API状态: {status.get('state')}")
        print(f"   详情: {status.get('detail', 'N/A')}")

        if status.get("state") == "connected":
            print("   [OK] 私有API连接成功")
        else:
            print(f"   [WARN] 私有API连接失败: {status.get('detail')}")
    except Exception as e:
        print(f"   [ERROR] 测试失败: {e}")
        import traceback

        traceback.print_exc()

    print("\n=== 测试完成 ===")


if __name__ == "__main__":
    test_direct_connection()
