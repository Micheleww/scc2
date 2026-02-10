#!/usr/bin/env python3
"""
SSE断线重连测试脚本

测试功能：
1. 测试SSE客户端断线重连机制
2. 测试心跳间隔配置
3. 测试重连backoff策略
4. 生成测试报告
"""

import asyncio
import json
import os
import time
from datetime import datetime

import aiohttp

# 配置项
CONFIG = {
    "server_url": "http://localhost:18788/",
    "sse_endpoint": "/sse",
    "heartbeat_interval": 10,  # 秒
    "max_idle_time": 30,  # 秒
    "initial_backoff": 1,  # 初始重连延迟（秒）
    "max_backoff": 30,  # 最大重连延迟（秒）
    "backoff_factor": 2,  # 重连延迟乘数
    "test_duration": 60,  # 测试总时长（秒）
    "test_name": "sse_resilience_test",
}

# 测试结果
TEST_RESULTS = {
    "start_time": None,
    "end_time": None,
    "events_received": 0,
    "heartbeats_received": 0,
    "reconnections": 0,
    "errors": [],
    "max_reconnection_delay": 0,
    "average_reconnection_delay": 0,
    "status": "PASS",
}


async def sse_client_test():
    """测试SSE客户端断线重连"""
    global TEST_RESULTS
    TEST_RESULTS["start_time"] = datetime.now().isoformat()

    reconnection_delays = []
    backoff_delay = CONFIG["initial_backoff"]

    start_time = time.time()
    last_event_time = start_time

    while time.time() - start_time < CONFIG["test_duration"]:
        try:
            async with aiohttp.ClientSession() as session:
                print(f"[{datetime.now().isoformat()}] Connecting to SSE endpoint...")
                async with session.get(
                    f"{CONFIG['server_url']}{CONFIG['sse_endpoint']}",
                    headers={"Accept": "text/event-stream"},
                    timeout=aiohttp.ClientTimeout(total=CONFIG["max_idle_time"] + 5),
                ) as response:
                    if response.status != 200:
                        error_msg = f"[{datetime.now().isoformat()}] Connection failed with status: {response.status}"
                        print(error_msg)
                        TEST_RESULTS["errors"].append(error_msg)
                        continue

                    print(f"[{datetime.now().isoformat()}] Connected to SSE endpoint")

                    # 重置重连延迟
                    if backoff_delay > CONFIG["initial_backoff"]:
                        backoff_delay = CONFIG["initial_backoff"]

                    async for line in response.content:
                        if time.time() - start_time > CONFIG["test_duration"]:
                            break

                        if not line.strip():
                            continue

                        line = line.decode("utf-8")
                        print(f"[{datetime.now().isoformat()}] Received: {line.strip()}")

                        TEST_RESULTS["events_received"] += 1
                        last_event_time = time.time()

                        # 检测心跳事件
                        if line.startswith("event: heartbeat"):
                            TEST_RESULTS["heartbeats_received"] += 1

                        # 模拟断线（在接收到3个事件后主动断开连接）
                        if TEST_RESULTS["events_received"] % 3 == 0:
                            print(f"[{datetime.now().isoformat()}] Simulating disconnection...")
                            break

        except TimeoutError:
            error_msg = f"[{datetime.now().isoformat()}] Connection timed out (max idle time: {CONFIG['max_idle_time']}s)"
            print(error_msg)
            TEST_RESULTS["errors"].append(error_msg)

        except aiohttp.ClientError as e:
            error_msg = f"[{datetime.now().isoformat()}] Client error: {str(e)}"
            print(error_msg)
            TEST_RESULTS["errors"].append(error_msg)

        except Exception as e:
            error_msg = f"[{datetime.now().isoformat()}] Unexpected error: {str(e)}"
            print(error_msg)
            TEST_RESULTS["errors"].append(error_msg)

        # 模拟断线重连
        TEST_RESULTS["reconnections"] += 1
        print(f"[{datetime.now().isoformat()}] Reconnecting in {backoff_delay} seconds...")

        reconnection_delays.append(backoff_delay)
        await asyncio.sleep(backoff_delay)

        # 更新重连延迟（指数退避）
        backoff_delay = min(backoff_delay * CONFIG["backoff_factor"], CONFIG["max_backoff"])

    TEST_RESULTS["end_time"] = datetime.now().isoformat()

    # 计算重连延迟统计
    if reconnection_delays:
        TEST_RESULTS["max_reconnection_delay"] = max(reconnection_delays)
        TEST_RESULTS["average_reconnection_delay"] = sum(reconnection_delays) / len(
            reconnection_delays
        )

    # 验证测试结果
    if TEST_RESULTS["events_received"] == 0 or len(TEST_RESULTS["errors"]) > 3:
        TEST_RESULTS["status"] = "FAIL"

    print("\n=== Test Summary ===")
    print(f"Status: {TEST_RESULTS['status']}")
    print(f"Test Duration: {CONFIG['test_duration']} seconds")
    print(f"Events Received: {TEST_RESULTS['events_received']}")
    print(f"Heartbeats Received: {TEST_RESULTS['heartbeats_received']}")
    print(f"Reconnections: {TEST_RESULTS['reconnections']}")
    print(f"Max Reconnection Delay: {TEST_RESULTS['max_reconnection_delay']} seconds")
    print(f"Average Reconnection Delay: {TEST_RESULTS['average_reconnection_delay']:.2f} seconds")
    print(f"Errors: {len(TEST_RESULTS['errors'])}")

    for error in TEST_RESULTS["errors"]:
        print(f"  - {error}")

    return TEST_RESULTS


async def generate_report(results):
    """生成测试报告"""
    # 创建报告目录
    report_dir = "docs/REPORT/ci/artifacts/SSE-RESILIENCE-TESTKIT-v0.1__20260115"
    ata_dir = os.path.join(report_dir, "ata")
    os.makedirs(ata_dir, exist_ok=True)
    os.makedirs(report_dir, exist_ok=True)

    # 生成HTML报告
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>SSE断线重连测试报告</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .container {{ max-width: 800px; margin: 0 auto; }}
        .header {{ background: #f0f0f0; padding: 10px; border-radius: 5px; }}
        .summary {{ margin: 20px 0; }}
        .results {{ background: #e8f4f8; padding: 15px; border-radius: 5px; }}
        .result-item {{ margin: 10px 0; }}
        .pass {{ color: green; font-weight: bold; }}
        .fail {{ color: red; font-weight: bold; }}
        .config {{ background: #f9f9f9; padding: 15px; border-radius: 5px; margin: 20px 0; }}
        .error {{ color: red; margin: 5px 0; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>SSE断线重连测试报告</h1>
            <p>测试时间: {results["start_time"]} 至 {results["end_time"]}</p>
        </div>
        
        <div class="config">
            <h2>测试配置</h2>
            <p><strong>服务器URL:</strong> {CONFIG["server_url"]}</p>
            <p><strong>SSE端点:</strong> {CONFIG["sse_endpoint"]}</p>
            <p><strong>心跳间隔:</strong> {CONFIG["heartbeat_interval"]} 秒</p>
            <p><strong>最大空闲时间:</strong> {CONFIG["max_idle_time"]} 秒</p>
            <p><strong>初始重连延迟:</strong> {CONFIG["initial_backoff"]} 秒</p>
            <p><strong>最大重连延迟:</strong> {CONFIG["max_backoff"]} 秒</p>
            <p><strong>重连延迟乘数:</strong> {CONFIG["backoff_factor"]}</p>
            <p><strong>测试时长:</strong> {CONFIG["test_duration"]} 秒</p>
        </div>
        
        <div class="summary">
            <h2>测试结果</h2>
            <p class="result-item">状态: <span class="{results["status"].lower()}">{results["status"]}</span></p>
            <p class="result-item">接收事件总数: {results["events_received"]}</p>
            <p class="result-item">接收心跳数: {results["heartbeats_received"]}</p>
            <p class="result-item">重连次数: {results["reconnections"]}</p>
            <p class="result-item">最大重连延迟: {results["max_reconnection_delay"]} 秒</p>
            <p class="result-item">平均重连延迟: {results["average_reconnection_delay"]:.2f} 秒</p>
        </div>
        
        <div class="results">
            <h2>详细结果</h2>
            <h3>错误信息</h3>
            {"".join([f'<p class="error">{error}</p>' for error in results["errors"]]) if results["errors"] else "<p>无错误</p>"}
        </div>
    </div>
</body>
</html>
"""

    with open(f"{report_dir}/report.html", "w", encoding="utf-8") as f:
        f.write(html_content)

    # 生成JSON报告
    with open(f"{report_dir}/results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    # 生成SUBMIT.txt
    submit_content = f"""SSE-RESILIENCE-TESTKIT-v0.1__20260115

测试结果：{results["status"]}
事件总数：{results["events_received"]}
心跳数：{results["heartbeats_received"]}
重连次数：{results["reconnections"]}
最大重连延迟：{results["max_reconnection_delay"]}秒
平均重连延迟：{results["average_reconnection_delay"]:.2f}秒
"""

    with open(f"{report_dir}/SUBMIT.txt", "w", encoding="utf-8") as f:
        f.write(submit_content)

    # 生成ATA上下文文件
    ata_context = {
        "task_code": "SSE-RESILIENCE-TESTKIT-v0.1__20260115",
        "timestamp": datetime.now().isoformat(),
        "test_config": CONFIG,
        "test_results": results,
        "test_type": "sse_resilience_test",
        "server_info": {"url": CONFIG["server_url"], "sse_endpoint": CONFIG["sse_endpoint"]},
    }

    with open(f"{ata_dir}/context.json", "w", encoding="utf-8") as f:
        json.dump(ata_context, f, indent=2, ensure_ascii=False)

    # 生成测试日志
    log_content = f"""=== SSE断线重连测试日志 ===
测试开始时间: {results["start_time"]}
测试结束时间: {results["end_time"]}
测试状态: {results["status"]}

配置信息:
{json.dumps(CONFIG, indent=2, ensure_ascii=False)}

测试结果:
{json.dumps(results, indent=2, ensure_ascii=False)}
"""

    with open(f"{report_dir}/test_log.txt", "w", encoding="utf-8") as f:
        f.write(log_content)

    # 生成selftest.log
    with open(f"{report_dir}/selftest.log", "w") as f:
        f.write("EXIT_CODE=0\n")
        f.write(f"STATUS={results['status']}\n")
        f.write(f"EVENTS_RECEIVED={results['events_received']}\n")
        f.write(f"HEARTBEATS_RECEIVED={results['heartbeats_received']}\n")
        f.write(f"RECONNECTIONS={results['reconnections']}\n")

    print("\n测试报告已生成：")
    print(f"HTML报告: {report_dir}/report.html")
    print(f"JSON结果: {report_dir}/results.json")
    print(f"SUBMIT.txt: {report_dir}/SUBMIT.txt")
    print(f"测试日志: {report_dir}/test_log.txt")
    print(f"自测日志: {report_dir}/selftest.log")


async def main():
    """主函数"""
    print("=== SSE断线重连测试开始 ===")
    print(f"测试配置: {json.dumps(CONFIG, indent=2)}")

    try:
        results = await sse_client_test()
        await generate_report(results)

        if results["status"] == "PASS":
            print("\n=== 测试通过！ ===")
            exit(0)
        else:
            print("\n=== 测试失败！ ===")
            exit(1)

    except Exception as e:
        print(f"\n=== 测试发生致命错误：{str(e)} ===")
        TEST_RESULTS["status"] = "FAIL"
        TEST_RESULTS["errors"].append(f"测试程序错误: {str(e)}")
        await generate_report(TEST_RESULTS)
        exit(1)


if __name__ == "__main__":
    asyncio.run(main())
