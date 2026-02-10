# AWS MCP 连接 GPT 检查清单

## 一、云 MCP 配置检查

### 1. 基础配置

- [ ] **服务器地址**：确保使用正确的域名或弹性IP
- [ ] **HTTPS 配置**：必须使用 HTTPS（GPT 要求）
- [ ] **端口配置**：
  - 建议使用默认 HTTPS 端口（443），可省略
  - 如果使用自定义端口，确保在安全组中开放
- [ ] **安全组配置**：允许来自 GPT 平台的 IP 访问

### 2. OAuth 端点检查

使用 `curl` 或浏览器测试以下端点：

```bash
# 检查 OAuth 资源元数据
curl -X GET https://your-real-server.com/.well-known/oauth-protected-resource

# 检查 OAuth 授权服务器元数据
curl -X GET https://your-real-server.com/.well-known/oauth-authorization-server

# 检查 JWKS 密钥集
curl -X GET https://your-real-server.com/.well-known/jwks.json
```

**关键检查点**：

- [ ] `oauth-protected-resource` 端点返回的 `resource` 字段与请求 URL 匹配
- [ ] `oauth-authorization-server` 端点返回完整的 OAuth 2.0 元数据
- [ ] 所有端点返回 200 OK 状态码

### 3. OAuth 元数据要求

确保 `/.well-known/oauth-authorization-server` 端点返回：

```json
{
  "issuer": "https://your-issuer.com",
  "authorization_endpoint": "https://your-real-server.com/oauth2/authorize",
  "token_endpoint": "https://your-real-server.com/oauth2/token",
  "jwks_uri": "https://your-real-server.com/.well-known/jwks.json",
  "registration_endpoint": "https://your-real-server.com/oauth2/client/register",
  "response_types_supported": ["code"],
  "grant_types_supported": ["authorization_code", "refresh_token"],
  "subject_types_supported": ["public"],
  "id_token_signing_alg_values_supported": ["RS256"],
  "scopes_supported": ["openid", "profile", "email", "mcp.tools"],
  "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"],
  "code_challenge_methods_supported": ["S256"]
}
```

### 4. 工具调用格式支持

确保服务器支持 GPT 格式的工具调用：

```json
{
  "method": "tools/call",
  "params": {
    "toolName": "ping",
    "params": {}
  }
}
```

## 二、GPT 连接页填写指南

### 1. 名称
- 填写：`TimQuant MCP Tools`
- 用途：标识您的 MCP 工具集

### 2. 描述
- 填写：`连接到 TimQuant AWS MCP 服务器，使用各种工具进行数据处理和管理`

### 3. MCP 服务器 URL
- **错误示例**：`https://your-real-server.com:8001/mcp`
- **正确格式**：
  - 使用 HTTPS
  - 使用实际域名或弹性 IP
  - 使用默认 HTTPS 端口（443）或正确的自定义端口
  - 正确示例：`https://your-real-server.com/mcp`（使用 443 端口）
  - 或：`https://your-real-server.com:8001/mcp`（使用自定义端口）

### 4. 身份验证
- **选择**：`OAuth`

### 5. OAuth 参数
- **客户端 ID**：使用 AWS Cognito 或其他 OAuth 提供商分配的客户端 ID
- **客户端密钥**：使用 OAuth 提供商分配的客户端密钥
- **授权范围**：包含 `mcp.tools` 以及其他所需范围

## 三、验证连接

### 1. 本地测试

使用以下脚本测试云 MCP 是否符合 GPT 要求：

```python
import requests
import json

url = "https://your-real-server.com/mcp"
headers = {
    "Content-Type": "application/json"
}

# 测试 initialize 请求
initialize_request = {
    "jsonrpc": "2.0",
    "id": "test-1",
    "method": "initialize",
    "params": {
        "clientInfo": {
            "name": "test-client",
            "version": "1.0.0"
        }
    }
}

response = requests.post(url, headers=headers, json=initialize_request)
print(f"Initialize status: {response.status_code}")

# 测试 list_tools 请求
list_tools_request = {
    "jsonrpc": "2.0",
    "id": "test-2",
    "method": "tools/list",
    "params": {}
}

response = requests.post(url, headers=headers, json=list_tools_request)
print(f"List tools status: {response.status_code}")
```

### 2. GPT 连接测试

1. 填写正确的连接信息
2. 点击 "创建" 按钮
3. 如果出现错误，检查错误信息：
   - **502 Bad Gateway**：服务器无法访问或端口错误
   - **OAuth 配置错误**：OAuth 端点配置问题
   - **URL 格式错误**：URL 格式不正确

## 四、常见问题排查

### 1. 502 Bad Gateway
- 检查服务器是否运行正常
- 检查安全组是否开放了端口
- 检查 HTTPS 配置是否正确

### 2. OAuth 配置错误
- 确保所有 OAuth 端点返回正确的 JSON 格式
- 确保 `resource` 字段与请求 URL 匹配
- 确保提供了完整的 OAuth 2.0 元数据

### 3. 工具调用失败
- 检查工具名称是否正确
- 检查工具参数格式是否正确
- 确保服务器支持 GPT 格式的工具调用

## 五、云 MCP 部署建议

### 1. 推荐配置

- **服务器**：AWS EC2 t3.medium 或更高
- **操作系统**：Ubuntu 22.04 LTS
- **Web 服务器**：Nginx（反向代理到 MCP 服务）
- **HTTPS**：使用 Let's Encrypt 或 AWS ACM 证书
- **端口**：使用默认 HTTPS 端口（443）

### 2. 部署架构

```
Internet → AWS ELB → EC2 实例