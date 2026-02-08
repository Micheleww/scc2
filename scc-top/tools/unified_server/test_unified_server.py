
#!/usr/bin/env python3
"""
统一服务器测试脚本

用于测试统一服务器的各个端点是否正常工作
"""

import requests
import time
import sys

BASE_URL = "http://localhost:18788"

def test_endpoint(url, description):
    """测试单个端点"""
    print(f"\n测试: {description}")
    print(f"URL: {url}")
    try:
        response = requests.get(url, timeout=5)
        print(f"状态码: {response.status_code}")
        if response.status_code == 200:
            print(f"✅ 成功")
            try:
                data = response.json()
                print(f"响应: {data}")
            except:
                print(f"响应: {response.text[:100]}")
            return True
        else:
            print(f"❌ 失败 - 状态码: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print(f"❌ 连接失败 - 服务器可能未启动")
        return False
    except Exception as e:
        print(f"❌ 错误: {e}")
        return False

def main():
    """运行所有测试"""
    print("=" * 60)
    print("统一服务器功能测试")
    print("=" * 60)
    
    # 等待服务器启动
    print("\n等待服务器启动...")
    time.sleep(2)
    
    results = []
    
    # 测试根路径
    results.append(("根路径", test_endpoint(f"{BASE_URL}/", "根路径")))
    
    # 测试健康检查
    results.append(("健康检查", test_endpoint(f"{BASE_URL}/health", "健康检查")))
    
    # 测试MCP总线
    results.append(("MCP总线", test_endpoint(f"{BASE_URL}/mcp", "MCP总线根路径")))
    
    # 测试A2A Hub
    results.append(("A2A Hub", test_endpoint(f"{BASE_URL}/api/health", "A2A Hub健康检查")))
    
    # 测试Exchange Server
    results.append(("Exchange Server", test_endpoint(f"{BASE_URL}/exchange/version", "Exchange Server版本")))
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{name}: {status}")
    
    print(f"\n总计: {passed}/{total} 通过")
    
    if passed == total:
        print("\n🎉 所有测试通过！")
        return 0
    else:
        print(f"\n⚠️ {total - passed} 个测试失败")
        return 1

if __name__ == "__main__":
    sys.exit(main())
