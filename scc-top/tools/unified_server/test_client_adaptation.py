#!/usr/bin/env python3
"""
客户端适配测试脚本

测试应用与统一服务器之间的请求适配
"""

import requests
import json
import sys
from typing import Dict, Any

BASE_URL = "http://localhost:18788"

def test_mcp_connection():
    """测试MCP连接"""
    print("\n=== 测试MCP连接 ===")
    
    # 测试tools/list
    try:
        response = requests.post(
            f"{BASE_URL}/mcp",
            json={
                "jsonrpc": "2.0",
                "id": "test-1",
                "method": "tools/list"
            },
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            if "result" in data:
                tools = data["result"].get("tools", [])
                print(f"✅ MCP连接成功，可用工具数: {len(tools)}")
                return True
            else:
                print(f"⚠️ MCP响应格式异常: {data}")
                return False
        else:
            print(f"❌ MCP连接失败，状态码: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ MCP连接错误: {e}")
        return False

def test_a2a_hub_connection():
    """测试A2A Hub连接"""
    print("\n=== 测试A2A Hub连接 ===")
    
    # 测试健康检查
    try:
        response = requests.get(f"{BASE_URL}/api/health", timeout=5)
        
        if response.status_code == 200:
            print("✅ A2A Hub连接成功")
            return True
        else:
            print(f"❌ A2A Hub连接失败，状态码: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ A2A Hub连接错误: {e}")
        return False

def test_exchange_server_connection():
    """测试Exchange Server连接"""
    print("\n=== 测试Exchange Server连接 ===")
    
    # 测试版本端点
    try:
        response = requests.get(f"{BASE_URL}/exchange/version", timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Exchange Server连接成功")
            print(f"   版本: {data.get('toolset_version', 'unknown')}")
            return True
        else:
            print(f"❌ Exchange Server连接失败，状态码: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Exchange Server连接错误: {e}")
        return False

def test_request_id_propagation():
    """测试请求ID传播"""
    print("\n=== 测试请求ID传播 ===")
    
    request_id = "test-request-id-12345"
    
    try:
        response = requests.get(
            f"{BASE_URL}/health",
            headers={"X-Request-ID": request_id},
            timeout=5
        )
        
        if response.status_code == 200:
            returned_id = response.headers.get("X-Request-ID")
            if returned_id == request_id:
                print(f"✅ 请求ID传播成功: {request_id}")
                return True
            else:
                print(f"⚠️ 请求ID不匹配: 发送={request_id}, 返回={returned_id}")
                return False
        else:
            print(f"❌ 请求失败，状态码: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 请求ID传播测试错误: {e}")
        return False

def test_cors():
    """测试CORS"""
    print("\n=== 测试CORS ===")
    
    try:
        # 发送OPTIONS预检请求
        response = requests.options(
            f"{BASE_URL}/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET"
            },
            timeout=5
        )
        
        if response.status_code == 200:
            cors_headers = {
                "Access-Control-Allow-Origin": response.headers.get("Access-Control-Allow-Origin"),
                "Access-Control-Allow-Methods": response.headers.get("Access-Control-Allow-Methods"),
            }
            print(f"✅ CORS配置正确: {cors_headers}")
            return True
        else:
            print(f"⚠️ CORS预检请求状态码: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ CORS测试错误: {e}")
        return False

def main():
    """运行所有测试"""
    print("=" * 60)
    print("客户端适配测试")
    print("=" * 60)
    
    results = []
    
    results.append(("MCP连接", test_mcp_connection()))
    results.append(("A2A Hub连接", test_a2a_hub_connection()))
    results.append(("Exchange Server连接", test_exchange_server_connection()))
    results.append(("请求ID传播", test_request_id_propagation()))
    results.append(("CORS", test_cors()))
    
    # 汇总
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
        print("\n🎉 所有适配测试通过！")
        return 0
    else:
        print(f"\n⚠️ {total - passed} 个测试失败")
        return 1

if __name__ == "__main__":
    sys.exit(main())
