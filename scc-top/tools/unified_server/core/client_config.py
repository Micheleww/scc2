"""
客户端配置适配模块

提供客户端配置示例和适配指南
"""

CLIENT_CONFIG_EXAMPLES = {
    "trae_mcp": {
        "description": "TRAE MCP客户端配置",
        "config": {
            "mcpServers": {
                "qcc-bus-local": {
                    "transport": {
                        "type": "http",
                        "url": "http://localhost:18788/mcp"
                    },
                    "auth": {
                        "type": "none"
                    },
                    "description": "本地统一服务器 - MCP总线服务",
                    "enabled": True
                }
            }
        },
        "file_path": ".trae/mcp.json"
    },
    "python_client": {
        "description": "Python客户端配置示例",
        "code": """
import requests

# 统一服务器配置
UNIFIED_SERVER_URL = "http://localhost:18788"

# MCP总线端点
MCP_URL = f"{UNIFIED_SERVER_URL}/mcp"

# A2A Hub端点
A2A_HUB_URL = f"{UNIFIED_SERVER_URL}/api"

# Exchange Server端点
EXCHANGE_URL = f"{UNIFIED_SERVER_URL}/exchange"

# 示例：调用MCP工具
def call_mcp_tool(tool_name, arguments):
    response = requests.post(
        MCP_URL,
        json={
            "jsonrpc": "2.0",
            "id": "1",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
    )
    return response.json()

# 示例：调用A2A Hub API
def create_task(task_code, instructions):
    response = requests.post(
        f"{A2A_HUB_URL}/task/create",
        json={
            "task_code": task_code,
            "instructions": instructions,
            "owner_role": "admin"
        }
    )
    return response.json()
"""
    },
    "javascript_client": {
        "description": "JavaScript客户端配置示例",
        "code": """
// 统一服务器配置
const UNIFIED_SERVER_URL = 'http://localhost:18788';

// MCP总线端点
const MCP_URL = `${UNIFIED_SERVER_URL}/mcp`;

// A2A Hub端点
const A2A_HUB_URL = `${UNIFIED_SERVER_URL}/api`;

// Exchange Server端点
const EXCHANGE_URL = `${UNIFIED_SERVER_URL}/exchange`;

// 示例：调用MCP工具
async function callMcpTool(toolName, arguments) {
    const response = await fetch(MCP_URL, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            jsonrpc: '2.0',
            id: '1',
            method: 'tools/call',
            params: {
                name: toolName,
                arguments: arguments
            }
        })
    });
    return await response.json();
}

// 示例：调用A2A Hub API
async function createTask(taskCode, instructions) {
    const response = await fetch(`${A2A_HUB_URL}/task/create`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            task_code: taskCode,
            instructions: instructions,
            owner_role: 'admin'
        })
    });
    return await response.json();
}
"""
    }
}


def get_client_config(client_type: str) -> dict:
    """获取客户端配置"""
    return CLIENT_CONFIG_EXAMPLES.get(client_type, {})


def generate_client_config_file(client_type: str, output_path: str):
    """生成客户端配置文件"""
    config = get_client_config(client_type)
    if not config:
        raise ValueError(f"Unknown client type: {client_type}")
    
    import json
    from pathlib import Path
    
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    if "config" in config:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(config["config"], f, indent=2, ensure_ascii=False)
    elif "code" in config:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(config["code"])
    
    return output_file
