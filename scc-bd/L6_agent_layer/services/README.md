# SCC Agent Services - 模块化服务架构

## 已完成

### 1. Skills Registry Service ✅
- **位置**: `services/skills-registry/`
- **端口**: 18001
- **职责**: 独立加载和管理所有 skills，提供查询 API
- **API**:
  - `GET /health` - 健康检查
  - `GET /search?q=xxx` - 搜索 skills
  - `POST /find-for-task` - 为任务查找相关 skills
  - `GET /get?id=xxx` - 获取单个 skill
  - `GET /list` - 列出 skills
  - `GET /stats` - 统计信息

### 2. Skills Client ✅
- **位置**: `agent/core/skills-client.mjs`
- **职责**: Agent 用于查询 Skills Registry 的客户端

## 建议的模块化组件

### 3. Role Registry Service
```
端口: 18002
职责: 独立管理所有 roles
API:
  - GET /roles - 列出所有 roles
  - GET /roles/:name - 获取 role 详情
  - POST /match - 为任务匹配最佳 role
  - POST /compose - 组合多个 roles
```

### 4. TaskBox Storage Service
```
端口: 18003
职责: 统一任务存储层
存储后端: 文件 / Redis / PostgreSQL
API:
  - POST /tasks - 创建任务
  - GET /tasks/:id - 获取任务
  - PUT /tasks/:id - 更新任务
  - GET /tasks?status=pending - 查询任务
  - POST /tasks/:id/decompose - 分解任务
```

### 5. Context Renderer Service ✅
- **位置**: `services/context-renderer/`
- **端口**: 18004
- **职责**: 基于 opencode_executor 的七个 slot 上下文渲染
- **七个 Slot**:
  - Slot 0: LEGAL_PREFIX - 法律前缀/免责声明
  - Slot 1: BINDING_REFS - 绑定引用
  - Slot 2: ROLE_CAPSULE - Role 胶囊
  - Slot 3: TASK_BUNDLE - 任务包
  - Slot 4: STATE - 状态
  - Slot 5: TOOLS - 工具
  - Slot 6: OPTIONAL_CONTEXT - 可选上下文
- **API**:
  - `GET /health` - 健康检查
  - `POST /render` - 渲染完整上下文包（七个 slot）
  - `POST /render/slot` - 渲染单个 slot
  - `POST /render/text` - 渲染为文本格式

### 6. Context Renderer Client ✅
- **位置**: `agent/core/context-client.mjs`
- **职责**: Agent 用于查询 Context Renderer Service

### 6. Executor Scheduler Service
```
端口: 18005
职责: 执行器调度和任务队列
功能: 任务队列、负载均衡、重试机制
API:
  - POST /schedule - 调度任务
  - GET /queue - 查看队列
  - POST /executors/register - 注册执行器
  - GET /executors - 列出执行器
```

### 7. Hook Registry Service
```
端口: 18006
职责: 管理 hooks
功能: 动态注册、触发、链式调用
API:
  - POST /hooks/register - 注册 hook
  - POST /hooks/trigger - 触发 hook
  - GET /hooks - 列出 hooks
```

### 8. Artifact Store Service
```
端口: 18007
职责: 存储执行产物
存储: 文件 / S3 / MinIO
API:
  - POST /artifacts - 上传产物
  - GET /artifacts/:id - 下载产物
  - GET /artifacts/:id/metadata - 获取元数据
```

## 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                         Agent Core                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │  TaskBox    │  │   Hooks     │  │  Context Renderer   │  │
│  │  (Client)   │  │  (Client)   │  │     (Client)        │  │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘  │
│  ┌──────┴──────┐  ┌──────┴──────┐  ┌──────────┴──────────┐  │
│  │ Skills      │  │  Role       │  │  Executor           │  │
│  │ Client      │  │  Client     │  │  Client             │  │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘  │
└─────────┼────────────────┼────────────────────┼─────────────┘
          │                │                    │
          ▼                ▼                    ▼
┌─────────────────────────────────────────────────────────────┐
│                      Service Mesh                           │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐   │
│  │ Skills   │ │  Role    │ │  TaskBox │ │   Context    │   │
│  │Registry  │ │ Registry │ │ Storage  │ │   Renderer   │   │
│  │  :18001  │ │  :18002  │ │  :18003  │ │    :18004    │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────┘   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                    │
│  │ Executor │ │   Hook   │ │ Artifact │                    │
│  │Scheduler │ │ Registry │ │  Store   │                    │
│  │  :18005  │ │  :18006  │ │  :18007  │                    │
│  └──────────┘ └──────────┘ └──────────┘                    │
└─────────────────────────────────────────────────────────────┘
```

## 优势

1. **独立部署** - 每个服务可以独立更新和扩展
2. **按需加载** - Agent 启动更快，不需要加载所有数据
3. **多 Agent 共享** - 多个 Agent 可以共享同一个服务
4. **水平扩展** - 服务可以独立水平扩展
5. **技术异构** - 不同服务可以使用不同技术栈
6. **故障隔离** - 单个服务故障不会影响整个系统

## Docker Compose 示例

```yaml
version: '3.8'

services:
  agent:
    build: ./agent
    environment:
      - SKILLS_REGISTRY_URL=http://skills-registry:18001
      - ROLE_REGISTRY_URL=http://role-registry:18002
      - TASKBOX_URL=http://taskbox-storage:18003
  
  skills-registry:
    build: ./services/skills-registry
    ports:
      - "18001:18001"
    volumes:
      - ./L4_prompt_layer/skills:/app/skills:ro
  
  role-registry:
    build: ./services/role-registry
    ports:
      - "18002:18002"
    volumes:
      - ./L4_prompt_layer/roles:/app/roles:ro
  
  taskbox-storage:
    build: ./services/taskbox-storage
    ports:
      - "18003:18003"
    environment:
      - STORAGE_TYPE=redis
      - REDIS_URL=redis://redis:6379
  
  redis:
    image: redis:alpine
```
