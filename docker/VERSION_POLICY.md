# SCC Docker 版本管理规范

> 版本: 1.0.0  
> 最后更新: 2026-02-10  
> 状态: 强制执行

---

## 1. 核心原则

### 1.1 单一真相源 (Single Source of Truth)
- **唯一的 Dockerfile**: `c:\scc\docker\Dockerfile`
- **唯一的 docker-compose.yml**: `c:\scc\docker\docker-compose.yml`
- **唯一的构建脚本**: `c:\scc\scripts\build-docker.bat`

### 1.2 禁止行为 (严禁违反)
- ❌ 禁止在其他位置创建 Dockerfile
- ❌ 禁止在其他位置创建 docker-compose.yml
- ❌ 禁止手动运行 `docker build` 命令
- ❌ 禁止使用非标准镜像名称

---

## 2. 镜像命名规范

### 2.1 标准格式
```
scc:<version>
```

### 2.2 版本标签规则

| 标签类型 | 格式示例 | 使用场景 |
|---------|---------|---------|
| **latest** | `scc:latest` | 开发/测试环境，始终指向最新稳定版 |
| **语义版本** | `scc:1.0.0` | 生产环境，固定版本 |
| **日期版本** | `scc:20260210` | 特殊构建，按日期标记 |
| **Git 短哈希** | `scc:a1b2c3d` | CI/CD 构建，追踪代码版本 |

### 2.3 版本号规则 (语义化版本)
```
主版本号.次版本号.修订号
   │       │       │
   │       │       └── 修复 bug、小改动
   │       └────────── 新功能、向下兼容
   └────────────────── 重大变更、不兼容
```

---

## 3. 构建流程

### 3.1 标准构建命令
```batch
:: 构建 latest 版本
scripts\build-docker.bat

:: 构建指定版本
scripts\build-docker.bat 1.0.0

:: 构建并同时标记为 latest
scripts\build-docker.bat 1.0.0 latest
```

### 3.2 构建前检查清单
- [ ] 代码已提交到 Git
- [ ] 版本号已更新
- [ ] CHANGELOG.md 已更新
- [ ] 所有测试通过

### 3.3 构建后检查清单
- [ ] 镜像构建成功
- [ ] 容器能正常启动
- [ ] 健康检查通过
- [ ] 功能测试通过

---

## 4. 部署流程

### 4.1 开发环境
```batch
cd c:\scc\docker
docker-compose up -d
```

### 4.2 生产环境
```batch
:: 1. 拉取指定版本
docker pull scc:1.0.0

:: 2. 更新 docker-compose.yml 中的版本
:: 编辑 docker-compose.yml，修改 image: scc:1.0.0

:: 3. 重新部署
cd c:\scc\docker
docker-compose down
docker-compose up -d
```

---

## 5. 版本更新规则

### 5.1 何时更新版本号

| 变更类型 | 版本号变更 | 示例 |
|---------|-----------|------|
| 修复 bug | 修订号+1 | `1.0.0` → `1.0.1` |
| 新增功能 | 次版本号+1 | `1.0.1` → `1.1.0` |
| 重大重构 | 主版本号+1 | `1.1.0` → `2.0.0` |
| 紧急修复 | 修订号+1，加后缀 | `1.0.1` → `1.0.2-hotfix1` |

### 5.2 版本发布流程

```
1. 在 docker/Dockerfile 中更新版本注释
   # 版本: 1.0.0

2. 更新 docker/docker-compose.yml 中的版本注释
   # 版本: 1.0.0

3. 更新 VERSION_POLICY.md 中的版本
   > 版本: 1.0.0

4. 运行构建脚本
   scripts\build-docker.bat 1.0.0 latest

5. 测试验证
   docker-compose up -d

6. 打 Git 标签
   git tag -a v1.0.0 -m "Release version 1.0.0"
   git push origin v1.0.0
```

---

## 6. 容器管理

### 6.1 标准容器名称
- **主服务**: `scc-server`

### 6.2 常用操作命令
```batch
:: 查看状态
docker ps -f name=scc-server

:: 查看日志
docker logs -f scc-server

:: 重启服务
docker-compose restart

:: 进入容器
docker exec -it scc-server /bin/bash

:: 备份数据
docker exec scc-server tar -czf /tmp/backup.tar.gz /app/data /app/logs
docker cp scc-server:/tmp/backup.tar.gz ./backups/
```

---

## 7. 数据卷管理

### 7.1 标准数据卷
- `scc_artifacts` - 构建产物
- `scc_data` - 应用数据
- `scc_logs` - 日志文件
- `scc_state` - 状态数据

### 7.2 备份策略
```batch
:: 创建备份脚本 scripts\backup.bat
@echo off
docker exec scc-server tar -czf /tmp/scc_backup_%date:~0,4%%date:~5,2%%date:~8,2%.tar.gz /app/data /app/logs /app/state /app/artifacts
docker cp scc-server:/tmp/scc_backup_%date:~0,4%%date:~5,2%%date:~8,2%.tar.gz c:\scc\backups\
echo Backup completed: scc_backup_%date:~0,4%%date:~5,2%%date:~8,2%.tar.gz
```

---

## 8. 故障处理

### 8.1 容器无法启动
```batch
:: 1. 查看日志
docker logs scc-server

:: 2. 检查配置
docker-compose config

:: 3. 重新构建
docker-compose down
docker-compose up -d --build
```

### 8.2 回滚到上一个版本
```batch
:: 1. 停止当前容器
docker-compose down

:: 2. 切换到旧版本（假设旧版本是 0.9.0）
:: 编辑 docker-compose.yml，修改 image: scc:0.9.0

:: 3. 启动旧版本
docker-compose up -d
```

---

## 9. 文档维护

### 9.1 必须同步更新的文件
当发布新版本时，必须更新以下文件中的版本号：
1. `docker/Dockerfile` - 顶部注释
2. `docker/docker-compose.yml` - 顶部注释
3. `scripts/build-docker.bat` - 顶部注释
4. `VERSION_POLICY.md` - 本文档

### 9.2 变更日志 (CHANGELOG.md)
每个版本必须记录：
- 版本号
- 发布日期
- 变更内容（新增、修复、优化）
- 兼容性说明
- 已知问题

---

## 10. 附录

### 10.1 快速参考卡

```
┌─────────────────────────────────────────────────────────┐
│                    SCC Docker 快速参考                    │
├─────────────────────────────────────────────────────────┤
│ 构建:   scripts\build-docker.bat [版本]                  │
│ 启动:   cd docker && docker-compose up -d               │
│ 停止:   cd docker && docker-compose down                │
│ 日志:   docker logs -f scc-server                       │
│ 重启:   docker-compose restart                          │
│ 进入:   docker exec -it scc-server /bin/bash            │
│ 状态:   docker ps -f name=scc-server                    │
└─────────────────────────────────────────────────────────┘
```

### 10.2 联系与支持
- 维护者: SCC Team
- 问题反馈: 提交 Issue 到项目仓库
- 紧急联系: [填写联系方式]

---

**注意**: 本文档为强制执行规范，所有团队成员必须遵守。违反规范可能导致构建失败或部署错误。
