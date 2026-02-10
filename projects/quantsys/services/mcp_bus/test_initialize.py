import json

import requests

# AWS MCP服务器配置
MCP_URL = "https://mcp.timquant.tech/mcp"


# 测试initialize方法
def test_initialize():
    print("Testing initialize method to AWS MCP...")

    # 构建请求体
    request_body = {"jsonrpc": "2.0", "id": "test-initialize", "method": "initialize"}

    try:
        # 发送请求
        response = requests.post(MCP_URL, json=request_body)

        print(f"Status code: {response.status_code}")
        print("Response:")
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))

        return response.json()
    except Exception as e:
        print(f"Error: {str(e)}")
        return None


if __name__ == "__main__":
    test_initialize()
