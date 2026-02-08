#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一服务器全面测试脚本

测试所有功能模块：
1. 基本功能测试
2. 健康检查测试
3. 服务集成测试
4. 性能测试
5. 错误处理测试
"""

import requests
import time
import sys
import json
import os
from typing import Dict, List, Tuple
from datetime import datetime

# 设置Windows控制台编码为UTF-8
if sys.platform == 'win32':
    try:
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
    except:
        pass

BASE_URL = "http://localhost:18788"
TIMEOUT = 10

class Colors:
    """终端颜色"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

# 使用ASCII字符替代emoji，避免编码问题
PASS_SYMBOL = "[PASS]"
FAIL_SYMBOL = "[FAIL]"
SUCCESS_SYMBOL = "[OK]"
WARNING_SYMBOL = "[WARN]"

class TestResult:
    """测试结果"""
    def __init__(self, name: str, passed: bool, message: str = "", duration: float = 0):
        self.name = name
        self.passed = passed
        self.message = message
        self.duration = duration
        self.timestamp = datetime.now()

def print_header(text: str):
    """打印标题"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text:^60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}\n")

def print_test(name: str, status: bool, message: str = "", duration: float = 0):
    """打印测试结果"""
    status_text = f"{Colors.GREEN}{PASS_SYMBOL}{Colors.RESET}" if status else f"{Colors.RED}{FAIL_SYMBOL}{Colors.RESET}"
    duration_text = f" ({duration:.2f}s)" if duration > 0 else ""
    print(f"{status_text} {name}{duration_text}")
    if message:
        print(f"      {message}")

def test_endpoint(url: str, method: str = "GET", data: dict = None, headers: dict = None, expected_status: int = 200) -> Tuple[bool, str, float]:
    """测试单个端点"""
    start_time = time.time()
    try:
        if method == "GET":
            response = requests.get(url, timeout=TIMEOUT, headers=headers)
        elif method == "POST":
            response = requests.post(url, json=data, timeout=TIMEOUT, headers=headers)
        else:
            return False, f"Unsupported method: {method}", time.time() - start_time
        
        duration = time.time() - start_time
        
        if response.status_code == expected_status:
            try:
                return True, json.dumps(response.json(), indent=2, ensure_ascii=False), duration
            except:
                return True, response.text[:200], duration
        else:
            return False, f"Expected status {expected_status}, got {response.status_code}", duration
    except requests.exceptions.ConnectionError:
        return False, "Connection failed - server may not be running", time.time() - start_time
    except Exception as e:
        return False, f"Error: {str(e)}", time.time() - start_time

def test_basic_functionality() -> List[TestResult]:
    """测试基本功能"""
    print_header("1. 基本功能测试")
    results = []
    
    # 根路径
    passed, message, duration = test_endpoint(f"{BASE_URL}/")
    results.append(TestResult("根路径", passed, message, duration))
    print_test("根路径", passed, message[:100] if len(message) > 100 else message, duration)
    
    # 健康检查
    passed, message, duration = test_endpoint(f"{BASE_URL}/health")
    results.append(TestResult("健康检查", passed, message, duration))
    print_test("健康检查", passed, message[:100] if len(message) > 100 else message, duration)
    
    return results

def test_health_checks() -> List[TestResult]:
    """测试健康检查系统"""
    print_header("2. 健康检查系统测试")
    results = []
    
    # 基本健康检查
    passed, message, duration = test_endpoint(f"{BASE_URL}/health")
    results.append(TestResult("基本健康检查", passed, message, duration))
    print_test("基本健康检查", passed, message[:100], duration)
    
    # 就绪检查
    passed, message, duration = test_endpoint(f"{BASE_URL}/health/ready")
    results.append(TestResult("就绪检查", passed, message, duration))
    print_test("就绪检查", passed, message[:100], duration)
    
    # 存活检查
    passed, message, duration = test_endpoint(f"{BASE_URL}/health/live")
    results.append(TestResult("存活检查", passed, message, duration))
    print_test("存活检查", passed, message[:100], duration)
    
    return results

def test_service_integration() -> List[TestResult]:
    """测试服务集成"""
    print_header("3. 服务集成测试")
    results = []
    
    # MCP总线
    passed, message, duration = test_endpoint(f"{BASE_URL}/mcp")
    results.append(TestResult("MCP总线", passed, message, duration))
    print_test("MCP总线", passed, message[:100], duration)
    
    # A2A Hub健康检查
    passed, message, duration = test_endpoint(f"{BASE_URL}/api/health")
    results.append(TestResult("A2A Hub健康检查", passed, message, duration))
    print_test("A2A Hub健康检查", passed, message[:100], duration)
    
    # Exchange Server版本
    passed, message, duration = test_endpoint(f"{BASE_URL}/exchange/version")
    results.append(TestResult("Exchange Server版本", passed, message, duration))
    print_test("Exchange Server版本", passed, message[:100], duration)
    
    return results

def test_performance() -> List[TestResult]:
    """测试性能"""
    print_header("4. 性能测试")
    results = []
    
    # 并发请求测试
    import concurrent.futures
    start_time = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(requests.get, f"{BASE_URL}/health", timeout=TIMEOUT) for _ in range(10)]
        success_count = sum(1 for f in concurrent.futures.as_completed(futures) if f.result().status_code == 200)
    duration = time.time() - start_time
    
    passed = success_count == 10
    message = f"10个并发请求，{success_count}个成功，耗时{duration:.2f}s"
    results.append(TestResult("并发性能", passed, message, duration))
    print_test("并发性能", passed, message, duration)
    
    # 响应时间测试
    times = []
    for _ in range(5):
        _, _, duration = test_endpoint(f"{BASE_URL}/health")
        times.append(duration)
    
    avg_time = sum(times) / len(times)
    max_time = max(times)
    min_time = min(times)
    
    passed = avg_time < 1.0  # 平均响应时间应小于1秒
    message = f"平均: {avg_time:.3f}s, 最大: {max_time:.3f}s, 最小: {min_time:.3f}s"
    results.append(TestResult("响应时间", passed, message, avg_time))
    print_test("响应时间", passed, message, avg_time)
    
    return results

def test_error_handling() -> List[TestResult]:
    """测试错误处理"""
    print_header("5. 错误处理测试")
    results = []
    
    # 404错误
    passed, message, duration = test_endpoint(f"{BASE_URL}/nonexistent", expected_status=404)
    results.append(TestResult("404错误处理", passed, message, duration))
    print_test("404错误处理", passed, message[:100], duration)
    
    # 无效方法
    try:
        response = requests.delete(f"{BASE_URL}/health", timeout=TIMEOUT)
        passed = response.status_code in [405, 404]  # Method not allowed or not found
        message = f"Status: {response.status_code}"
    except Exception as e:
        passed = False
        message = str(e)
    results.append(TestResult("无效方法处理", passed, message, 0))
    print_test("无效方法处理", passed, message[:100])
    
    return results

def main():
    """运行所有测试"""
    print_header("统一服务器全面测试")
    print(f"测试目标: {BASE_URL}")
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # 等待服务器启动
    print(f"{Colors.YELLOW}等待服务器启动...{Colors.RESET}")
    time.sleep(2)
    
    all_results = []
    
    # 运行所有测试
    try:
        all_results.extend(test_basic_functionality())
        all_results.extend(test_health_checks())
        all_results.extend(test_service_integration())
        all_results.extend(test_performance())
        all_results.extend(test_error_handling())
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}测试被用户中断{Colors.RESET}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Colors.RED}测试过程中发生错误: {e}{Colors.RESET}")
        sys.exit(1)
    
    # 汇总结果
    print_header("测试结果汇总")
    
    passed = sum(1 for r in all_results if r.passed)
    total = len(all_results)
    failed = total - passed
    
    for result in all_results:
        status = f"{Colors.GREEN}{PASS_SYMBOL}{Colors.RESET}" if result.passed else f"{Colors.RED}{FAIL_SYMBOL}{Colors.RESET}"
        duration_text = f" ({result.duration:.2f}s)" if result.duration > 0 else ""
        print(f"{status} {result.name}{duration_text}")
    
    print(f"\n{Colors.BOLD}总计: {passed}/{total} 通过{Colors.RESET}")
    
    if failed > 0:
        print(f"{Colors.RED}失败: {failed} 个测试{Colors.RESET}")
    
    # 保存测试报告
    report = {
        "timestamp": datetime.now().isoformat(),
        "total": total,
        "passed": passed,
        "failed": failed,
        "results": [
            {
                "name": r.name,
                "passed": r.passed,
                "message": r.message[:200] if len(r.message) > 200 else r.message,
                "duration": r.duration,
                "timestamp": r.timestamp.isoformat()
            }
            for r in all_results
        ]
    }
    
    report_path = "test_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n测试报告已保存到: {report_path}")
    
    # 返回退出码
    if failed == 0:
        print(f"\n{Colors.GREEN}{Colors.BOLD}{SUCCESS_SYMBOL} 所有测试通过！{Colors.RESET}")
        return 0
    else:
        print(f"\n{Colors.RED}{Colors.BOLD}{WARNING_SYMBOL} {failed} 个测试失败{Colors.RESET}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
