# SCC 项目规则

## 文件同步规则（重要）

### 新架构：Volume 挂载实时同步

**废弃 git 中转同步，改用 Docker Volume 挂载**

```
本地文件修改
    ↓
Volume 挂载自动同步（毫秒级）
    ↓
Docker 容器内立即可见
```

### 为什么废弃 git hook？

| 问题 | 说明 |
|------|------|
| 网络依赖 | git fetch 需要访问远程仓库 |
| 时序问题 | commit 和 push 之间存在延迟 |
| 复杂度高 | 多层脚本调用，失败点太多 |
| 锁机制 | 并发控制增加复杂度和死锁风险 |

### 新方案优势

| 特性 | Volume 挂载 | Git Hook |
|------|------------|----------|
| 同步速度 | **毫秒级** | 秒级~分钟级 |
| 网络依赖 | **无** | 需要 GitHub |
| 可靠性 | **高**（文件系统级） | 低（多层脚本） |
| 复杂度 | **低** | 高 |

### AI 助手操作规范

#### ✅ 允许操作
- 修改 `scc-bd/` 目录下的源代码
- 修改 `scc-bd/` 目录下的配置文件
- 提交代码到 git（仅用于版本控制，不触发同步）

#### ❌ 禁止操作
- 禁止执行 `docker build`
- 禁止修改 `C:\docker\` 目录下的文件
- 禁止手动执行任何同步脚本

### 文件变更自动处理

1. **代码文件** (`.mjs`, `.js`, `.json`) 修改后：
   - Volume 挂载实时同步到容器
   - 如需重启服务，手动执行：`docker restart scc-server`

2. **静态文件** 修改后：
   - 立即生效，无需重启

### 手动重启服务

```powershell
# 如果修改了关键文件需要重启
docker restart scc-server

# 查看容器状态
docker ps

# 查看日志
docker logs scc-server -f
```

### Docker 配置位置

- **Dockerfile**: `C:\docker\Dockerfile`
- **docker-compose.yml**: `C:\scc\docker-compose.yml`
- **Docker 目录**: `C:\docker\`（已移出 scc 工作区）

---

## 其他规则

### 代码提交
- 正常提交代码到 git
- 提交仅用于版本控制，不再触发 Docker 同步

### 文件监控（可选）
如需自动重启，可运行：
```powershell
.\tools\file-watcher.ps1
```
