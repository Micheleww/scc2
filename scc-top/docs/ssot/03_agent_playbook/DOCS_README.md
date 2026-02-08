---
oid: 01KGEJFTEYYVDGX3R5P37RK5P2
layer: DOCOPS
primary_unit: A.ROUTER
tags: [V.SKILL_GUARD]
status: active
---

# QuantSys 量化交易系统

**Doc-ID**: QUANTSYS-README
**Category**: ARCH
**Version**: v1.0.0
**Status**: active
**Last-Updated**: 2026-01-14
**Related-Task**: DOC-GOVERNANCE-001

---

## 项目概述

QuantSys 是一个功能完整的量化交易系统，用于策略开发、回测和实盘交易。该系统支持多种交易所、多种交易策略和多种数据格式，具备完整的风险控制和监控功能。

## 核心功能

- **策略开发** - 支持多种策略开发框架
- **回测引擎** - 高性能回测系统
- **实盘交易** - 支持多种交易所实盘交易
- **数据管理** - 完整的数据收集、存储和管理
- **云同步** - 云本地数据同步和策略部署
- **监控报警** - 实时监控和报警系统

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置文件

主要配置文件位于 `configs/` 目录下：

- `aws_data_sync_config.json` - AWS数据同步配置
- `cloud_sync_config.json` - 云本地同步配置

### 3. 启动系统

```bash
# 运行主程序
python main.py

# 运行AWS数据同步
python scripts/aws_data_sync.py
```

## 文档

### 控制面区域

- [Go/Stop操作清单](GO_STOP_CHECKLIST.md) - 验收者检查清单，包含CI全绿、报告存在、日志存在、证据路径存在、status规则5个关键验收点

### AWS连接与数据同步

详细的AWS连接和数据同步指南请参考：

- [AWS连接与数据同步指南](docs/aws_connection_guide.md)

### 策略开发

策略开发相关文档请参考：

- `docs/strategy_development.md`

### 回测指南

回测相关文档请参考：

- `docs/backtesting_guide.md`

## 目录结构

```
<REPO_ROOT>/
├── configs/           # 配置文件目录
├── corefiles/         # 核心功能文件
├── docs/              # 文档目录
├── freqtrade-strategies-main/  # Freqtrade策略
├── logs/              # 日志目录
├── scripts/           # 脚本目录
├── src/               # 源代码目录
├── tests/             # 测试目录
├── user_data/         # 用户数据目录
└── README.md          # 项目说明文档
```

## 系统要求

- Python 3.8+
- Windows/Linux/macOS
- 推荐配置：8GB RAM, 50GB 磁盘空间

## 常见问题

### AWS连接问题

如果您遇到AWS连接问题，请参考：

- [AWS连接与数据同步指南](docs/aws_connection_guide.md) - 第6节 "常见问题及解决方案"

### 数据同步问题

数据同步相关问题请参考：

- [AWS连接与数据同步指南](docs/aws_connection_guide.md) - 第5节 "数据同步流程"

## 联系方式

如有任何问题或建议，请通过以下方式联系：

- Email: support@quantsys.com
- GitHub: https://github.com/quantsys/quantsys

## 许可证

本项目采用 MIT 许可证，详情请参考 LICENSE 文件。

---

## CHANGELOG

### v1.0.0 (2026-01-14)
**新增内容**:
- 添加文档版本化元数据（Doc-ID, Category, Version, Status等）
- 添加CHANGELOG区块

**本次修改内容**:
- 无（初始版本化）

**是否影响接口/逻辑/后续任务**:
- 否，本文档为项目说明文档，不影响系统功能

---

## 文档可追溯性

### 代码路径映射
- **项目根目录**: `<REPO_ROOT>`
- **配置文件**: configs/
- **源代码**: src/quantsys/
- **脚本**: scripts/
- **测试**: tests/

### 相关文档
- [SYSTEM_OVERVIEW.md](SYSTEM_OVERVIEW.md) - 系统核心结构
- [STATUS.md](STATUS.md) - 系统状态追踪
- [DOC_GOVERNANCE_OVERVIEW.md](DOC_GOVERNANCE_OVERVIEW.md) - 文档治理总览
