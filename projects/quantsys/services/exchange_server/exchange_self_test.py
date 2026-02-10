#!/usr/bin/env python3
"""Exchange Server 公网连通自检脚本"""

import sys
import time

import requests


def main():
    """Main function"""
    print("=== Exchange Server 公网连通自检脚本 ===")

    # 配置
    exchange_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:80"
    timeout = 30
    print(f"测试目标URL: {exchange_url}")

    # 1. 测试 /mcp 端点
    print("\n1. 测试 /mcp 端点...")
    try:
        response = requests.get(
            f"{exchange_url}/mcp",
            headers={"Content-Type": "application/json", "Authorization": "Bearer dummy-token"},
            timeout=timeout,
        )
        status_code = response.status_code
        print(f"   HTTP状态码: {status_code}")
        if status_code in [200, 401]:
            print("   ✅ /mcp 端点访问成功（预期状态码：200或401）")
        else:
            print(f"   ❌ /mcp 端点访问失败，状态码：{status_code}")
            return 1
    except Exception as e:
        print(f"   ❌ /mcp 端点访问失败：{e}")
        return 1

    # 2. 测试 /sse 端点（持续心跳）
    print(f"\n2. 测试 /sse 端点（持续心跳，{timeout}秒）...")
    try:
        # 使用流式请求
        with requests.get(
            f"{exchange_url}/sse",
            headers={"Content-Type": "text/event-stream"},
            stream=True,
            timeout=timeout,
        ) as response:
            # 读取前60秒的响应
            start_time = time.time()
            heartbeat_count = 0

            for line in response.iter_lines():
                if time.time() - start_time > timeout:
                    break
                if line:
                    decoded_line = line.decode("utf-8")
                    if "event: heartbeat" in decoded_line:
                        heartbeat_count += 1
                        print(f"   📡 收到心跳 {heartbeat_count}")

        print("   检查SSE心跳...")
        print(f"   收到心跳次数: {heartbeat_count}")

        if heartbeat_count >= 1:
            print("   ✅ /sse 端点心跳正常")
            print("\n=== 自检结果 ===")
            print("✅ 所有测试通过")
            return 0
        else:
            print("   ❌ /sse 端点未收到心跳")
            print("\n=== 自检结果 ===")
            print("❌ 测试失败")
            return 1
    except Exception as e:
        print(f"   ❌ /sse 端点访问失败：{e}")
        print("\n=== 自检结果 ===")
        print("❌ 测试失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
