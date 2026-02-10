# SCC Docker 工具部署指南

> 所属层级: L1 代码层 (L1_code_layer)  
> 功能分类: Docker 部署配置 - 工具集成  
> 版本: 1.2.0  
> 最后更新: 2026-02-10

---

## 📦 已部署到 Docker 容器的工具

### 1. LLM CLI 工具

| 工具 | 命令 | 版本 | 说明 |
|------|------|------|------|
| **opencode** | `opencodecli` | 1.1.53 | OpenCode AI CLI (musl 版本) |
| **codex** | `codex` | 0.98.0 | OpenAI Codex CLI |
| **bun** | `bun` | 1.3.9 | JavaScript 运行时 |

### 2. OLT CLI 桥接器

| 组件 | 路径 | 说明 |
|------|------|------|
| **OLT CLI Bridge** | `/app/L6_execution_layer/olt_cli_bridge.mjs` | OLT CLI 桥接器 v1 |
| **OLT CLI Bridge v2** | `/app/L6_execution_layer/olt_cli_bridge_v2.mjs` | OLT CLI 桥接器 v2 |
| **OpenCode LLM Bridge** | `/app/L6_execution_layer/opencode_llm_bridge.mjs` | OpenCode LLM 桥接器 |
| **SCC Server with OLT** | `/app/L6_execution_layer/scc_server_with_olt.mjs` | 集成 OLT 的 SCC 服务器 |
| **OpenCode CLI Executor** | `/app/L6_execution_layer/executors/opencodecli_executor.mjs` | OpenCode CLI 执行器 |
| **Trae Executor v2** | `/app/L6_execution_layer/executors/trae_executor_v2.mjs` | Trae 执行器 v2 |

### 3. Git 同步工具

| 工具 | 命令 | 说明 |
|------|------|------|
| **SCC Sync** | `scc-sync` | 从 GitHub 同步最新代码 |
| **Start OLT CLI** | `start-olt-cli` | 启动 OLT CLI 服务器 |

---

## 🚀 使用方法

### 启动 OLT CLI 服务器

```bash
# 在容器内启动 OLT CLI 服务器
docker exec scc-server start-olt-cli

# 或在后台启动
docker exec -d scc-server start-olt-cli
```

服务器将在端口 3458 上运行，提供以下端点：
- `GET  /api/health` - 健康检查
- `GET  /api/olt-cli/health` - OLT CLI 健康检查
- `GET  /api/olt-cli/models` - 获取可用模型列表
- `POST /api/olt-cli/chat/completions` - 聊天补全
- `POST /api/olt-cli/execute` - 执行命令
- `POST /api/olt-cli/tools/:tool` - 调用工具

### 同步代码

```bash
# 从 GitHub 拉取最新代码
docker exec scc-server scc-sync
```

### 使用 LLM CLI 工具

```bash
# 使用 opencode
docker exec scc-server opencodecli --version
docker exec scc-server opencodecli --help

# 使用 codex
docker exec scc-server codex --version
docker exec scc-server codex --help
```

---

## 🔧 系统命令

| 命令 | 说明 |
|------|------|
| `docker exec scc-server opencodecli` | 运行 opencode CLI |
| `docker exec scc-server codex` | 运行 codex CLI |
| `docker exec scc-server bun` | 运行 bun |
| `docker exec scc-server scc-sync` | 同步代码 |
| `docker exec scc-server start-olt-cli` | 启动 OLT CLI 服务器 |
| `docker exec scc-server git ...` | 运行 git 命令 |

---

## 📁 本地 vs Docker 对比

### 本地 (c:\scc)
- ✅ 源代码开发
- ✅ Git 仓库管理
- ✅ IDE 集成
- ❌ 需要本地安装所有工具

### Docker (scc-server)
- ✅ 所有工具已预装
- ✅ 与本地代码同步
- ✅ 独立运行环境
- ✅ 可直接连接 GitHub
- ❌ 需要重建镜像更新 Dockerfile

---

## 🔄 代码同步流程

```
本地开发 (c:\scc)
    ↓ git commit & push
GitHub (github.com/Micheleww/scc2)
    ↓ scc-sync
Docker 容器 (scc-server)
    ↓ start-olt-cli
运行 OLT CLI 服务
```

---

## 📝 更新 Dockerfile

如果需要添加新工具到 Docker 镜像，编辑 `c:\scc\docker\Dockerfile`：

```dockerfile
# 添加新工具示例
RUN npm install -g <new-tool>
```

然后重建镜像：

```bash
cd c:\scc\docker
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

---

## 🔗 相关文档

- [DOCKER_NORMALIZATION.md](./DOCKER_NORMALIZATION.md) - Docker 归一化文档
- [VERSION_POLICY.md](./VERSION_POLICY.md) - 版本管理规范
- [BUILD_GUIDE.md](./BUILD_GUIDE.md) - 构建指南
- [LAYER_MAPPING.md](../../LAYER_MAPPING.md) - 分层映射文档

---

## 📊 版本历史

| 日期 | 版本 | 变更内容 |
|------|------|---------|
| 2026-02-10 | 1.2.0 | 添加 OLT CLI 桥接器和 Git 同步功能 |
| 2026-02-10 | 1.1.0 | 集成 opencode 和 codex CLI |
| 2026-02-10 | 1.0.0 | 初始版本，完成 Docker 归一化 |
