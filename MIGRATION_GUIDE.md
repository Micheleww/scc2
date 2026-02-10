# SCC Docker 同步架构迁移指南

## 变更总结

### 1. Docker 目录已移出工作区
- **旧位置**: `C:\scc\docker\`
- **新位置**: `C:\docker\`

### 2. 废弃 Git Hook 同步
- **旧方式**: Git commit → Hook → GitHub → 容器拉取
- **新方式**: Volume 挂载实时同步（毫秒级）

### 3. 文件同步速度对比

| 方式 | 延迟 | 可靠性 |
|------|------|--------|
| Git Hook | 5-30秒 | 低（网络依赖） |
| Volume 挂载 | **毫秒级** | **高**（文件系统级） |

## 手动清理 Git Hooks

由于系统限制，需要手动删除以下文件：

```powershell
# 在 PowerShell 中执行
Remove-Item "C:\scc\.git\hooks\post-commit" -Force
Remove-Item "C:\scc\.git\hooks\pre-push" -Force
Remove-Item "C:\scc\.git\hooks\post-merge" -Force
Remove-Item "C:\scc\.git\hooks\post-checkout" -Force
```

## 新架构使用方法

### 1. 启动 Docker（使用新配置）

```powershell
cd C:\scc
docker-compose down  # 停止旧容器
docker-compose up -d --build  # 使用新配置启动
```

### 2. 文件修改自动同步

修改 `C:\scc\scc-bd\` 下的任何文件：
- **代码文件** (`.mjs`, `.js`): 实时同步到容器
- **配置文件** (`.json`): 实时同步到容器
- **静态文件**: 实时同步到容器

### 3. 重启服务（仅在需要时）

如果修改了需要重启才能生效的文件：

```powershell
docker restart scc-server
```

### 4. 可选：启用文件监控自动重启

```powershell
cd C:\scc
.\tools\file-watcher.ps1
```

这会监控文件变更，当关键文件修改时自动重启容器。

## 目录结构

```
C:\
├── docker\                    # Docker 配置（已移出 scc）
│   ├── Dockerfile
│   └── ...
│
└── scc\                       # 项目代码
    ├── scc-bd\                # 源代码（挂载到容器）
    ├── docker-compose.yml     # 新配置（Volume 挂载）
    ├── tools\
    │   └── file-watcher.ps1   # 文件监控脚本
    └── .trae\rules\
        └── project_rules.md   # 更新后的规则
```

## 故障排除

### 问题：容器无法启动
```powershell
# 查看日志
docker logs scc-server

# 检查端口占用
netstat -ano | findstr 18788
```

### 问题：文件未同步
```powershell
# 进入容器检查
docker exec -it scc-server sh
ls -la /app/scc-bd/
```

### 问题：权限错误
Volume 挂载使用只读模式 (`:ro`)，容器内无法修改代码，这是预期行为。

## 回滚方案

如需恢复旧方案：
1. 使用 `C:\docker\` 中的备份文件
2. 恢复 `C:\scc\.git\hooks\` 中的 hooks
3. 使用旧的 `docker-compose.yml`
