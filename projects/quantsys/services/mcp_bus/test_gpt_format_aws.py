import json

import requests


# 测试使用GPT格式连接到AWS MCP服务器
def test_gpt_format_aws():
    # 使用实际的AWS MCP服务器URL
    url = "https://mcp.timquant.tech/mcp"
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer test_token",  # 使用测试令牌
    }

    # 测试GPT格式的ping请求
    gpt_ping_request = {
        "jsonrpc": "2.0",
        "id": "gpt-aws-test-1",
        "method": "tools/call",
        "params": {"toolName": "ping", "params": {}},
    }

    print("Testing GPT format ping request to AWS MCP...")
    try:
        response = requests.post(url, headers=headers, json=gpt_ping_request)
        print(f"Status code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
    except Exception as e:
        print(f"Error: {e}")

    # 测试原始格式的ping请求（作为对比）
    original_ping_request = {
        "jsonrpc": "2.0",
        "id": "original-aws-test-1",
        "method": "tools/call",
        "params": {"name": "ping", "arguments": {}},
    }

    print("\nTesting original format ping request to AWS MCP...")
    try:
        response = requests.post(url, headers=headers, json=original_ping_request)
        print(f"Status code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    test_gpt_format_aws()
