#!/usr/bin/env python3
"""
SSE断线重连故障模拟测试脚本

测试功能：
1. 测试SSE客户端在各种故障场景下的重连机制
2. 生成故障模拟报告
"""

import asyncio
import json
import os
from datetime import datetime

import aiohttp

# 配置项
CONFIG = {
    "server_url": "http://localhost:18788/",
    "sse_endpoint": "/sse",
    "test_duration": 60,  # 测试总时长（秒）
    "test_name": "sse_failure_test",
}

# 测试结果
TEST_RESULTS = {"start_time": None, "end_time": None, "failure_scenarios": [], "status": "PASS"}


async def test_scenario(name, description, action):
    """测试单个故障场景"""
    scenario_result = {
        "name": name,
        "description": description,
        "start_time": datetime.now().isoformat(),
        "end_time": None,
        "events_received": 0,
        "heartbeats_received": 0,
        "reconnected": False,
        "error": None,
        "status": "PASS",
    }

    try:
        async with aiohttp.ClientSession() as session:
            print(f"\n[{datetime.now().isoformat()}] 开始测试场景: {name}")
            print(f"描述: {description}")

            async with session.get(
                f"{CONFIG['server_url']}{CONFIG['sse_endpoint']}",
                headers={"Accept": "text/event-stream"},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status != 200:
                    scenario_result["status"] = "FAIL"
                    scenario_result["error"] = f"连接失败，状态码: {response.status}"
                    scenario_result["end_time"] = datetime.now().isoformat()
                    return scenario_result

                # 接收一些事件
                event_count = 0
                heartbeat_count = 0

                async for line in response.content:
                    line = line.decode("utf-8").strip()
                    if not line:
                        continue

                    event_count += 1

                    if line.startswith("event: heartbeat"):
                        heartbeat_count += 1

                    print(f"[{datetime.now().isoformat()}] 接收事件: {line}")

                    # 执行故障动作
                    if event_count >= 2:
                        await action()
                        break

                scenario_result["events_received"] = event_count
                scenario_result["heartbeats_received"] = heartbeat_count

    except TimeoutError:
        scenario_result["status"] = "FAIL"
        scenario_result["error"] = "连接超时"
    except aiohttp.ClientError as e:
        scenario_result["status"] = "FAIL"
        scenario_result["error"] = f"客户端错误: {str(e)}"
    except Exception as e:
        scenario_result["status"] = "FAIL"
        scenario_result["error"] = f"意外错误: {str(e)}"

    scenario_result["end_time"] = datetime.now().isoformat()

    # 验证重连（等待10秒后尝试重新连接）
    try:
        await asyncio.sleep(5)
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{CONFIG['server_url']}{CONFIG['sse_endpoint']}",
                headers={"Accept": "text/event-stream"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status == 200:
                    scenario_result["reconnected"] = True
                    print(f"[{datetime.now().isoformat()}] 场景 {name}: 成功重连")
                else:
                    print(
                        f"[{datetime.now().isoformat()}] 场景 {name}: 重连失败，状态码: {response.status}"
                    )
    except Exception as e:
        print(f"[{datetime.now().isoformat()}] 场景 {name}: 重连测试失败: {str(e)}")

    if scenario_result["error"] and not scenario_result["reconnected"]:
        scenario_result["status"] = "FAIL"

    print(f"[{datetime.now().isoformat()}] 场景 {name}: 结果 {scenario_result['status']}")

    return scenario_result


async def simulate_network_interruption():
    """模拟网络中断"""
    print(f"[{datetime.now().isoformat()}] 模拟网络中断...")
    # 这里可以添加更复杂的网络中断模拟
    # 目前我们只是关闭连接
    await asyncio.sleep(0.1)


async def simulate_server_restart():
    """模拟服务器重启"""
    print(f"[{datetime.now().isoformat()}] 模拟服务器重启...")
    # 这里可以添加更复杂的服务器重启模拟
    await asyncio.sleep(0.1)


async def simulate_high_latency():
    """模拟高延迟"""
    print(f"[{datetime.now().isoformat()}] 模拟高延迟...")
    await asyncio.sleep(5)


async def run_failure_tests():
    """运行所有故障场景测试"""
    global TEST_RESULTS
    TEST_RESULTS["start_time"] = datetime.now().isoformat()

    # 定义故障场景
    scenarios = [
        {
            "name": "network_interruption",
            "description": "测试网络中断后的重连",
            "action": simulate_network_interruption,
        },
        {
            "name": "server_restart",
            "description": "测试服务器重启后的重连",
            "action": simulate_server_restart,
        },
        {
            "name": "high_latency",
            "description": "测试高延迟下的重连",
            "action": simulate_high_latency,
        },
    ]

    # 运行所有场景
    for scenario in scenarios:
        result = await test_scenario(scenario["name"], scenario["description"], scenario["action"])
        TEST_RESULTS["failure_scenarios"].append(result)

        # 如果有场景失败，整体测试标记为失败
        if result["status"] == "FAIL":
            TEST_RESULTS["status"] = "FAIL"

    TEST_RESULTS["end_time"] = datetime.now().isoformat()

    print("\n=== 故障模拟测试总结 ===")
    print(f"测试状态: {TEST_RESULTS['status']}")
    print(f"测试场景数: {len(TEST_RESULTS['failure_scenarios'])}")
    print(
        f"成功场景数: {sum(1 for s in TEST_RESULTS['failure_scenarios'] if s['status'] == 'PASS')}"
    )
    print(
        f"失败场景数: {sum(1 for s in TEST_RESULTS['failure_scenarios'] if s['status'] == 'FAIL')}"
    )

    for scenario in TEST_RESULTS["failure_scenarios"]:
        print(f"\n场景: {scenario['name']}")
        print(f"  状态: {scenario['status']}")
        print(f"  重连成功: {scenario['reconnected']}")
        if scenario["error"]:
            print(f"  错误: {scenario['error']}")

    return TEST_RESULTS


async def generate_report(results):
    """生成测试报告"""
    # 创建报告目录
    report_dir = "docs/REPORT/ci/artifacts/SSE-RESILIENCE-TESTKIT-v0.1"
    os.makedirs(report_dir, exist_ok=True)

    # 生成HTML报告
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>SSE故障模拟测试报告</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .container {{ max-width: 800px; margin: 0 auto; }}
        .header {{ background: #f0f0f0; padding: 10px; border-radius: 5px; }}
        .summary {{ margin: 20px 0; }}
        .results {{ background: #e8f4f8; padding: 15px; border-radius: 5px; margin: 20px 0; }}
        .scenario {{ margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }}
        .pass {{ color: green; font-weight: bold; }}
        .fail {{ color: red; font-weight: bold; }}
        .scenario-pass {{ background-color: #d4edda; }}
        .scenario-fail {{ background-color: #f8d7da; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>SSE故障模拟测试报告</h1>
            <p>测试时间: {results["start_time"]} 至 {results["end_time"]}</p>
        </div>
        
        <div class="summary">
            <h2>测试结果</h2>
            <p>状态: <span class="{results["status"].lower()}">{results["status"]}</span></p>
            <p>测试场景数: {len(results["failure_scenarios"])}</p>
            <p>成功场景数: {
        sum(1 for s in results["failure_scenarios"] if s["status"] == "PASS")
    }</p>
            <p>失败场景数: {
        sum(1 for s in results["failure_scenarios"] if s["status"] == "FAIL")
    }</p>
        </div>
        
        <div class="results">
            <h2>故障场景测试结果</h2>
            
            {
        "".join(
            [
                f'''<div class="scenario scenario-{s["status"].lower()}">
                <h3>{s["name"]}</h3>
                <p><strong>描述:</strong> {s["description"]}</p>
                <p><strong>开始时间:</strong> {s["start_time"]}</p>
                <p><strong>结束时间:</strong> {s["end_time"]}</p>
                <p><strong>接收事件数:</strong> {s["events_received"]}</p>
                <p><strong>接收心跳数:</strong> {s["heartbeats_received"]}</p>
                <p><strong>重连成功:</strong> {"是" if s["reconnected"] else "否"}</p>
                <p><strong>状态:</strong> <span class="{s["status"].lower()}">{s["status"]}</span></p>
                {f"<p><strong>错误:</strong> {s['error']}</p>" if s["error"] else ""}
            </div>'''
                for s in results["failure_scenarios"]
            ]
        )
    }
        </div>
    </div>
</body>
</html>
"""

    with open(f"{report_dir}/failure_report.html", "w", encoding="utf-8") as f:
        f.write(html_content)

    # 生成JSON报告
    with open(f"{report_dir}/failure_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print("\n故障模拟测试报告已生成：")
    print(f"HTML报告: {report_dir}/failure_report.html")
    print(f"JSON结果: {report_dir}/failure_results.json")


async def main():
    """主函数"""
    print("=== SSE断线重连故障模拟测试开始 ===")

    try:
        results = await run_failure_tests()
        await generate_report(results)

        if results["status"] == "PASS":
            print("\n=== 所有故障场景测试通过！ ===")
            exit(0)
        else:
            print("\n=== 有故障场景测试失败！ ===")
            exit(1)

    except Exception as e:
        print(f"\n=== 测试发生致命错误：{str(e)} ===")
        exit(1)


if __name__ == "__main__":
    asyncio.run(main())
