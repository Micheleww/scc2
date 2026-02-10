# OLT CLI 执行器

> 所属层级: L6_execution_layer/executors

## 功能说明

OLT CLI (OpenCode LLM Tool CLI) 是 SCC 系统的统一执行器，融合了以下三个组件的功能：
- OpenCode CLI Executor V2
- OLT CLI Bridge V2
- SCC Server with OLT CLI

## 核心特性

- **7个工具**: read_file, write_file, edit_file, list_dir, search_files, grep_search, run_command
- **多轮对话**: 默认50轮
- **HTTP API**: OpenAI 兼容格式 + SCC 原生端点
- **端口**: 3458

## 使用方法

### 启动服务器

```bash
cd L6_execution_layer
node oltcli.mjs
```

### API 端点

#### OpenAI 兼容端点

| 端点 | 方法 | 功能 |
|------|------|------|
| `/v1/models` | GET | 模型列表 |
| `/v1/chat/completions` | POST | 聊天完成 |

#### SCC 原生端点

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/health` | GET | 健康检查 |
| `/api/olt-cli/health` | GET | OLT 健康检查 |
| `/api/olt-cli/models` | GET | 模型列表 |
| `/api/olt-cli/chat/completions` | POST | 聊天完成 |
| `/api/olt-cli/execute` | POST | 多轮执行（带工具） |

### 示例请求

```powershell
# 发送 hello 测试
$body = @{
    messages = @(@{role="user"; content="hello"})
} | ConvertTo-Json -Compress

Invoke-RestMethod -Uri "http://localhost:3458/v1/chat/completions" `
    -Method POST -ContentType "application/json" -Body $body
```

```powershell
# 多轮工具执行
$body = @{
    task = "列出当前目录的文件"
    maxRounds = 50
} | ConvertTo-Json -Compress

Invoke-RestMethod -Uri "http://localhost:3458/api/olt-cli/execute" `
    -Method POST -ContentType "application/json" -Body $body
```

## 工具列表

| 工具名 | 功能 | 参数 |
|--------|------|------|
| `read_file` | 读取文件 | file_path, offset, limit |
| `write_file` | 写入文件 | file_path, content |
| `edit_file` | 编辑文件 | file_path, old_string, new_string |
| `list_dir` | 列出目录 | path |
| `search_files` | glob搜索 | pattern, path |
| `grep_search` | ripgrep搜索 | pattern, path, glob |
| `run_command` | 执行命令 | command, cwd, timeout |

## 相关链接

- [上层文档](../README.md)
- [源代码](./oltcli.mjs)
