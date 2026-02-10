# SCC Docker 自动同步策略

> 所属层级: L1 代码层 (L1_code_layer)  
> 功能分类: Docker 部署配置 - 自动同步  
> 版本: 1.0.0  
> 最后更新: 2026-02-10

---

## 📊 本地 vs Docker 功能差异对比

### 本地有但 Docker 没有的功能

| 类别 | 本地路径 | Docker 状态 | 同步策略 |
|------|---------|------------|---------|
| **Windows 服务** | `SCC-Enterprise/` | ❌ 不支持 | 无需同步 (Windows 专用) |
| **Windows 托盘** | `SCC-Tray/` | ❌ 不支持 | 无需同步 (Windows 专用) |
| **业务项目** | `projects/quantsys/` | ❌ 不存在 | 可选同步 (大型项目) |
| **插件目录** | `plugin/` | ❌ 不存在 | 部分同步 (通过 npm 安装) |
| **文档** | `docs/` | ❌ 不存在 | 可选同步 |
| **备份** | `backups/` | ❌ 不存在 | 无需同步 |
| **脚本** | `scripts/*.bat` | ❌ 不存在 | 转换后同步 |
| **测试文件** | `scc-bd/test_*.mjs` | ❌ 不存在 | 建议同步 |
| **UI 前端** | `scc-bd/ui/` | ❌ 不存在 | 建议同步 |
| **工具脚本** | `scc-bd/tools/` | ❌ 不存在 | 建议同步 |
| **技能脚本** | `scc-bd/scripts/` | ❌ 不存在 | 建议同步 |

### Docker 有但本地可能没有的功能

| 功能 | Docker | 本地 | 说明 |
|------|--------|------|------|
| **codex CLI** | ✅ 预装 | ❓ 需安装 | OpenAI Codex |
| **opencode** | ✅ 预装 | ❓ 需安装 | OpenCode AI CLI |
| **bun** | ✅ 预装 | ❓ 需安装 | JavaScript 运行时 |
| **wine** | ✅ 已装 | ❌ 不需要 | Windows 兼容层 |
| **Git 同步** | ✅ scc-sync | ❌ 无 | Docker 专用工具 |

---

## 🔄 自动同步机制设计

### 方案 1: Git Hook 自动同步 (推荐)

**原理**: 在本地 Git 仓库安装 hooks，在 commit/push 后自动触发 Docker 同步

**优点**:
- ✅ 完全自动化，无需手动操作
- ✅ 与开发流程无缝集成
- ✅ 实时同步，延迟最小

**缺点**:
- ⚠️ 需要 Docker 容器始终运行
- ⚠️ 同步失败时可能阻塞 Git 操作

**安装**:
```powershell
# 安装 Git Hooks
.\docker\install-git-hooks.ps1
```

### 方案 2: 定时同步 (备选)

**原理**: 使用 Windows 任务计划程序或 cron 定时执行同步

**优点**:
- ✅ 不依赖 Git 操作
- ✅ 可配置同步频率
- ✅ 不会阻塞开发流程

**缺点**:
- ❌ 非实时同步
- ❌ 需要额外配置

**配置**:
```powershell
# 创建定时任务 (每 5 分钟)
$action = New-ScheduledTaskAction -Execute "docker" -Argument "exec scc-server scc-sync"
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName "SCC-Docker-Sync" -Action $action -Trigger $trigger
```

### 方案 3: 文件监听同步 (高级)

**原理**: 使用文件系统监听工具 (如 chokidar) 监听文件变化，实时同步

**优点**:
- ✅ 真正的实时同步
- ✅ 只同步变化的文件
- ✅ 高效

**缺点**:
- ❌ 实现复杂
- ❌ 需要额外的同步逻辑

---

## 📋 推荐的同步策略

### 核心策略: Git Hook + 手动触发

```
本地开发 (c:\scc)
    ↓ git add & git commit
自动触发 post-commit hook
    ↓ 执行 auto-sync-hook.ps1
Docker 容器执行 scc-sync
    ↓ git fetch & git reset --hard
Docker 容器代码更新
```

### 同步范围

**必须同步** (已包含在 scc-bd 17层架构):
- ✅ L1_code_layer/ - 代码层
- ✅ L2_task_layer/ - 任务层
- ✅ L4_prompt_layer/ - 提示词层
- ✅ L5_model_layer/ - 模型层
- ✅ L6_agent_layer/ - Agent层
- ✅ L6_execution_layer/ - 执行层
- ✅ L7_tool_layer/ - 工具层
- ✅ L9_state_layer/ - 状态层
- ✅ L11_routing_layer/ - 路由层
- ✅ L13_security_layer/ - 安全层
- ✅ L14_quality_layer/ - 质量层
- ✅ L15_change_layer/ - 变更层
- ✅ L16_observability_layer/ - 观测层
- ✅ L17_ontology_layer/ - 本体层

**建议同步**:
- 🔄 scc-bd/scripts/ - 技能生成脚本
- 🔄 scc-bd/ui/ - 前端 UI
- 🔄 scc-bd/tools/ - 工具脚本
- 🔄 scc-bd/test_*.mjs - 测试文件

**无需同步**:
- ❌ SCC-Enterprise/ - Windows 专用
- ❌ SCC-Tray/ - Windows 专用
- ❌ SCC-Service/ - Windows 专用
- ❌ backups/ - 备份文件
- ❌ .opencode/ - 本地数据库
- ❌ plugin/ - 通过 npm 安装

**可选同步**:
- ⚪ projects/ - 业务项目 (大型)
- ⚪ docs/ - 文档

---

## 🚀 快速开始

### 1. 安装自动同步

```powershell
# 进入 SCC 目录
cd c:\scc

# 安装 Git Hooks
.\docker\install-git-hooks.ps1
```

### 2. 验证安装

```powershell
# 检查 hooks 是否安装
ls .git/hooks/post-commit
ls .git/hooks/post-push

# 测试同步
docker exec scc-server scc-sync
```

### 3. 开始使用

```bash
# 正常开发流程
git add .
git commit -m "feat: 添加新功能"
# ↓ 自动同步触发
# Docker 容器自动更新
```

---

## 🔧 高级配置

### 自定义同步行为

编辑 `c:\scc\docker\auto-sync-hook.ps1`:

```powershell
# 修改同步前的检查
# 修改同步后的操作
# 添加通知功能
```

### 选择性同步

编辑 `c:\scc\docker\sync-from-git.sh`:

```bash
# 只同步特定目录
git checkout origin/main -- L1_code_layer/
git checkout origin/main -- L6_execution_layer/
```

### 同步前备份

在 `sync-from-git.sh` 中添加:

```bash
# 备份当前状态
cp -r /app/L6_execution_layer /app/backups/L6_execution_layer_$(date +%Y%m%d_%H%M%S)
```

---

## 🐛 故障排除

### 问题 1: Hook 执行失败

**症状**: Git commit 后报错

**解决**:
```powershell
# 检查 Docker 容器状态
docker ps

# 手动测试同步
docker exec scc-server scc-sync

# 检查 Hook 脚本权限
ls .git/hooks/post-commit
```

### 问题 2: 同步后服务未重启

**症状**: 代码已更新但服务未生效

**解决**:
```bash
# 在容器内重启服务
docker exec scc-server pkill -f node
docker exec scc-server start-olt-cli
```

### 问题 3: 同步冲突

**症状**: git reset 失败

**解决**:
```bash
# 进入容器手动解决
docker exec -it scc-server sh
cd /app
git status
git reset --hard origin/main
```

---

## 📈 大规模修改建议

### 修改前准备

1. **备份当前状态**:
   ```bash
   docker exec scc-server tar czf /app/backups/pre_change_$(date +%Y%m%d).tar.gz /app
   ```

2. **停止自动同步** (可选):
   ```powershell
   Remove-Item .git/hooks/post-commit
   Remove-Item .git/hooks/post-push
   ```

3. **创建特性分支**:
   ```bash
   git checkout -b feature/big-change
   ```

### 修改后验证

1. **手动同步测试**:
   ```bash
   docker exec scc-server scc-sync
   ```

2. **验证服务状态**:
   ```bash
   docker exec scc-server start-olt-cli
   ```

3. **重新启用自动同步**:
   ```powershell
   .\docker\install-git-hooks.ps1
   ```

---

## 📝 更新记录

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-02-10 | 1.0.0 | 初始版本，设计自动同步策略 |

---

## 🔗 相关文档

- [DOCKER_TOOLS_GUIDE.md](./DOCKER_TOOLS_GUIDE.md) - Docker 工具部署指南
- [BUILD_GUIDE.md](./BUILD_GUIDE.md) - Docker 构建指南
- [VERSION_POLICY.md](./VERSION_POLICY.md) - 版本管理规范
