# 统一服务器文件保护指南

## 概述

统一服务器实现了文件保护机制，确保只有授权用户可以修改服务器代码文件。

## 文件保护机制

### 1. 文件锁定

所有服务器代码文件（.py, .ps1, .json, .yaml等）默认被锁定，只有提供正确密钥才能修改。

### 2. 密钥管理

- **密钥存储位置**: 项目导航文档 (`docs/arch/project_navigation__v0.1.0__ACTIVE__20260115.md`)
- **密钥位置**: 统一服务器章节 > 文件保护密钥部分
- **密钥格式**: 32字符的URL安全随机字符串

### 3. 权限检查

在修改文件时，系统会：
1. 检查文件是否受保护
2. 验证提供的密钥是否正确
3. 如果密钥正确，允许修改
4. 如果密钥错误或未提供，拒绝修改

## 使用方法

### 生成密钥

```bash
python lock_server_files.py generate-key
```

生成的密钥需要添加到导航文档中。

### 锁定文件

```bash
# 使用密钥锁定文件
python lock_server_files.py lock --secret-key <密钥>

# 或设置环境变量
export UNIFIED_SERVER_SECRET_KEY=<密钥>
python lock_server_files.py lock
```

### 解锁文件（修改前）

```bash
# 方法1: 使用环境变量
export UNIFIED_SERVER_MODIFY_KEY=<密钥>
# 然后可以修改文件

# 方法2: 使用命令行参数
python lock_server_files.py unlock --key <密钥>
```

### 查看锁定状态

```bash
python lock_server_files.py status
```

## 受保护的文件

以下类型的文件会被自动保护：
- `*.py` - Python源代码
- `*.ps1` - PowerShell脚本
- `*.json` - JSON配置文件
- `*.yaml`, `*.yml` - YAML配置文件

排除的文件：
- 以`.`开头的隐藏文件
- `__pycache__`目录
- `.pytest_cache`目录
- 测试文件（可选）

## 修改文件流程

### 步骤1: 获取密钥

从导航文档中获取密钥：
```
docs/arch/project_navigation__v0.1.0__ACTIVE__20260115.md
统一服务器章节 > 文件保护密钥
```

### 步骤2: 设置环境变量

```bash
export UNIFIED_SERVER_MODIFY_KEY=<密钥>
```

### 步骤3: 修改文件

现在可以正常修改文件了。

### 步骤4: 重新锁定（可选）

修改完成后，可以重新锁定文件：

```bash
python lock_server_files.py lock --secret-key <密钥>
```

## 安全建议

1. **密钥保密** - 不要将密钥提交到代码仓库
2. **定期更换** - 定期生成新密钥并更新导航文档
3. **最小权限** - 只给需要修改代码的用户密钥
4. **审计日志** - 记录所有文件修改操作

## 故障排除

### 问题1: 无法修改文件

**错误**: `PermissionError: 文件受保护，无法修改`

**解决**:
1. 检查是否设置了`UNIFIED_SERVER_MODIFY_KEY`环境变量
2. 验证密钥是否正确（从导航文档获取）
3. 使用`python lock_server_files.py unlock --key <密钥>`解锁

### 问题2: 密钥验证失败

**错误**: `Invalid modification key`

**解决**:
1. 检查密钥是否正确（从导航文档获取最新密钥）
2. 确保密钥没有多余的空格或换行
3. 如果密钥已更改，更新环境变量

### 问题3: 找不到密钥

**错误**: `UNIFIED_SERVER_MODIFY_KEY environment variable not set`

**解决**:
1. 从导航文档获取密钥
2. 设置环境变量: `export UNIFIED_SERVER_MODIFY_KEY=<密钥>`
3. 或使用命令行参数: `--key <密钥>`

## 技术实现

### 文件保护模块

- **`core/file_protection.py`** - 文件保护核心模块
  - 文件锁定状态管理
  - 密钥验证
  - 权限检查

- **`core/file_modification_guard.py`** - 文件修改守卫
  - 装饰器支持
  - 权限检查函数

- **`core/file_write_guard.py`** - 文件写入守卫
  - 拦截文件写入操作
  - 自动权限检查

### 锁定状态文件

锁定状态存储在：
```
tools/unified_server/.file_protection_lock.json
```

包含信息：
- 锁定状态
- 锁定时间
- 受保护文件列表

## 最佳实践

1. **开发环境** - 可以临时禁用文件保护进行开发
2. **生产环境** - 必须启用文件保护
3. **代码审查** - 所有文件修改都需要密钥验证
4. **密钥管理** - 使用密钥管理工具管理密钥
