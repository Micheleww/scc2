#!/usr/bin/env python3
"""
测试脚本：验证 exchange_server 的限流和 SSE 连接上限功能
"""

import asyncio
import time
import uuid

import aiohttp

# 测试配置
BASE_URL = "http://localhost:18788/"


async def test_rate_limit():
    """测试 JSON-RPC 端点的限流功能"""
    print("=== 测试 JSON-RPC 限流功能 ===")

    async with aiohttp.ClientSession() as session:
        # 生成请求头
        headers = {
            "Authorization": "Bearer default_secret_token",
            "Content-Type": "application/json",
        }

        # 快速发送多个请求，触发限流
        request_count = 120  # 超过默认限流阈值（100）
        responses = []

        start_time = time.time()

        for i in range(request_count):
            # 生成唯一 nonce 和 timestamp
            nonce = str(uuid.uuid4())
            timestamp = int(time.time())

            # 添加到请求头
            request_headers = headers.copy()
            request_headers["X-Request-Nonce"] = nonce
            request_headers["X-Request-Ts"] = str(timestamp)

            try:
                async with session.post(
                    f"{BASE_URL}/mcp",
                    headers=request_headers,
                    json={"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": 1},
                ) as resp:
                    status = resp.status
                    responses.append(status)

                    if status == 429:
                        print(f"✅ 成功触发限流，请求 #{i + 1} 返回 429")
                        break
            except Exception as e:
                print(f"请求 #{i + 1} 出错: {e}")

        end_time = time.time()

        print("\n=== 限流测试结果 ===")
        print(f"总请求数: {len(responses)}")
        print(f"成功请求数: {responses.count(200)}")
        print(f"限流请求数: {responses.count(429)}")
        print(f"请求耗时: {end_time - start_time:.2f} 秒")

        if 429 in responses:
            print("✅ 限流功能正常工作")
            return True
        else:
            print("❌ 限流功能未触发")
            return False


async def test_sse_connection_limit():
    """测试 SSE 连接上限功能"""
    print("\n=== 测试 SSE 连接上限功能 ===")

    max_connections = 5  # 测试时设置的最大连接数
    connections = []
    connected_count = 0

    try:
        # 创建多个 SSE 连接
        for i in range(max_connections + 2):  # 超过限制
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.get(
                        f"{BASE_URL}/sse", headers={"X-Trace-ID": str(uuid.uuid4())}
                    ) as resp:
                        if resp.status == 200:
                            print(f"✅ SSE 连接 #{i + 1} 成功建立")
                            connected_count += 1
                            # 保持连接短暂时间
                            await asyncio.sleep(1)
                        elif resp.status == 429:
                            print(f"✅ SSE 连接 #{i + 1} 被拒绝（连接数超过限制）")
                            # 检查是否是在达到限制后才拒绝
                            if i >= max_connections - 1:
                                return True
                        else:
                            print(f"❌ SSE 连接 #{i + 1} 失败，状态码: {resp.status}")
                except Exception as e:
                    print(f"❌ SSE 连接 #{i + 1} 异常: {e}")
                    await asyncio.sleep(0.1)
    finally:
        # 关闭所有连接
        for conn in connections:
            await conn.close()

    print("❌ SSE 连接上限功能未正常工作")
    return False


async def main():
    """主测试函数"""
    print("开始测试 exchange_server 限流和 SSE 连接上限功能...")
    print(f"测试地址: {BASE_URL}")
    print()

    # 测试顺序
    test1_passed = await test_rate_limit()
    test2_passed = await test_sse_connection_limit()

    print("\n=== 测试总结 ===")
    if test1_passed and test2_passed:
        print("✅ 所有测试通过")
        return 0
    else:
        print("❌ 部分测试失败")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
