---
oid: 01KGEM51P0ZA8Q0WWCKDN4M249
layer: ARCH
primary_unit: A.PLANNER
tags: [S.NAV_UPDATE, V.GUARD]
status: active
---

# NOTE (SSOT migration):
# - This document is preserved here as legacy reference.
# - It MUST NOT be treated as an entrypoint/navigation root.
# - Authoritative navigation is `docs/START_HERE.md` -> `docs/ssot/` indices.

# 项目导航文档

## 基本信息

- **kind**: ARCH
- **scope**: project
- **topic**: navigation
- **version**: "0.1.0"
- **status**: ACTIVE
- **owner**: execution_ai
- **created**: "2026-01-15"
- **updated**: "2026-01-22T23:52:00Z"
- **last_update**: "2026-01-22T23:52:00Z - 创建因子库排行表格生成脚本，支持多种排序方式"
- **law_ref**:
  - law/QCC-README.md
- **contracts_ref**: []
- **task_ref**:
  - TC-DOCS-260115-04-Axx-001
  - GOV_P0_CORE_VALIDATION__20260118
- **supersedes**: []
- **superseded_by**: []

## 更新记录

详细更新记录请参见：[项目导航文档更新记录](docs/ARCH/project_navigation_changelog__v0.1.0.md)

## 目录

- [第一部分：通讯层 (Communication Layer)](#第一部分通讯层-communication-layer)
  - [1.1 本地总服务器](#11-本地总服务器agent-to-agent通信)
  - [1.2 AWS云服务器](#12-aws云服务器云端总服务器)
  - [1.3 ATA系统](#13-ata系统agent-to-agent通信)
  - [1.4 开源项目集成](#14-开源项目集成)
  - [1.5 技术架构与配置](#15-技术架构与配置)
- [第二部分：交易层 (Trading Layer)](#第二部分交易层-trading-layer)
  - [2.1 核心业务系统](#21-核心业务系统订单执行投资组合策略因子数据模型监控)
  - [2.2 辅助系统](#22-辅助系统调度状态故障注入回测通知)
  - [2.3 系统级架构文档](#23-系统级架构文档系统集成数据流和状态机)
  - [2.4 核心工具和入口](#24-核心工具和入口回测数据下载器)
  - [2.5 数据源与API集成（OKX API）](#25-数据源与api集成okx-api)
- [第三部分：显示层 (Display Layer)](#第三部分显示层-display-layer)
  - [3.1 统一管理平台](#31-统一管理平台)
  - [3.2 Dashboard](#32-dashboard量化控制中心)
  - [3.3 Web Viewer](#33-web-viewerata多方会话记录系统)
  - [3.4 配置管理系统](#34-配置管理系统)
  - [3.5 FreqUI](#35-frequi交易界面)
  - [3.6 相关文档](#36-相关文档)
- [第四部分：控制面与工程管理](#第四部分控制面与工程管理)
  - [4.1 宪法典与执行规则](#41-宪法典与执行规则)
  - [4.2 Skills文档汇总](#42-skills文档汇总)
  - [4.3 CI完备性系统](#43-ci完备性系统)
    - [4.3.1 核心规范与合约](#431-核心规范与合约)
    - [4.3.2 控制面导航入口](#432-控制面导航入口)
    - [4.3.3 验证与门禁工具](#433-验证与门禁工具)
    - [4.3.4 MVM 完备 CI 系统（Phase 0-5）](#434-mvm-完备-ci-系统phase-0-5)
    - [4.3.5 CI 约束与强制集成](#435-ci-约束与强制集成)
    - [4.3.6 状态机与守卫系统](#436-状态机与守卫系统)
    - [4.3.7 核心工具与脚本](#437-核心工具与脚本)
    - [4.3.8 防守方专用文档](#438-防守方专用文档)
    - [4.3.9 Prompt Blocks 索引](#439-prompt-blocks-索引)
  - [4.4 文档管理系统](#44-文档管理系统)
  - [4.5 数据库系统](#45-数据库系统)
- [5. 使用约定](#5-使用约定)

## 第一部分：通讯层 (Communication Layer)

### 1.1 本地总服务器（Agent-to-Agent通信）

**服务端点**：
- `http://127.0.0.1:8000/mcp` - MCP服务端点（JSON-RPC 2.0协议，支持HTTP和stdio传输）
- `http://127.0.0.1:8000/health` - 健康检查端点（返回服务器状态和基本信息）
- `http://127.0.0.1:8000/` - 根路径（重定向到统一平台首页）
- `/api/viewer/messages` - ATA消息查看（与Web Viewer共享消息数据）

**核心实现**：
| Path | What | Notes/Owner |
|------|------|-------------|
| tools/mcp_bus/server/tools.py | MCP工具实现 | 包含inbox、board、ata_send、ata_receive等21个MCP工具 |
| tools/mcp_bus/server/ata_enhanced.py | ATA增强功能 | 会话上下文管理、消息队列、统计信息 |
| tools/mcp_bus/register_agent.py | 统一Agent注册工具 | 供AI使用的统一Agent注册工具，支持快速注册Agent到ATA协作系统，自动分配数字编码（1-100）⭐ **AI直接使用** |
| tools/mcp_bus/test_agent_conversation.py | Agent对话测试工具 | 测试两个注册Agent之间的ATA消息通信，用于验证协作功能 ⭐ |
| tools/mcp_bus/assign_numeric_codes.py | 数字编码分配工具 | 为已注册的Agent分配唯一数字编码（1-100）的工具 ⭐ |

**ATA功能特性**：
- ✅ 消息优先级支持（priority: low, normal, high, urgent）
- ✅ 消息状态跟踪（status: pending, delivered, read, acked）
- ✅ 未读消息过滤（unread_only参数）
- ✅ 会话上下文管理（include_context参数）
- ✅ 消息队列机制（可靠传递和跟踪）
- ✅ 优先级排序和统计信息
- ✅ 标记已读功能（ata_mark_read工具）

**桌面快捷方式**：
| Path | What | Notes/Owner |
|------|------|-------------|
| 启动本地总服务器.lnk | 普通模式快捷方式 | 窗口可见，自动重启，包含-NoExit参数 |
| 启动本地总服务器_后台服务.lnk | 后台服务快捷方式 | 无窗口运行（Hidden模式），常驻后台 |
| tools/mcp_bus/创建桌面快捷方式.ps1 | 快捷方式创建脚本 | 自动创建两个快捷方式到桌面 |
| docs/arch/TIMQUANT_TOTAL_SERVER_SUMMARY__v0.1.0.md | TIMQuant 总服务器总结 | 汇总本地总服务器 + TIMQuant desktop 的启动、打包、快捷方式与调试路径 ⭐ **维护参考** |

**运行模式**：
- ✅ **普通模式**：窗口可见，可查看运行日志
- ✅ **后台模式**：无窗口运行，自动重启，定时重启（每24小时）
- ✅ **健康检查监控**：每5分钟检查一次
- ✅ **进程监控**：每30秒检查一次

### 1.2 AWS云服务器（云端总服务器）

**服务端点**：
- `https://mcp.timquant.tech/mcp` - AWS MCP服务端点（JSON-RPC 2.0协议，HTTPS加密，支持公网访问）
- `http://54.179.47.252:18080/mcp` - AWS MCP服务端点（HTTP，内部端口，仅用于测试）
- `http://54.179.47.252:18080/health` - 健康检查端点（返回服务器状态和基本信息）

**服务器信息**：
- 服务器IP: `54.179.47.252` (主) / `13.229.100.10` (备用)
- 域名: `mcp.timquant.tech`
- HTTPS端口: `443`
- HTTP端口: `18080` (内部)
- 服务名称: `qcc-bus`
- SSH用户: `ubuntu`
- SSH密钥: `<ABS_PATH>/corefiles/aws_key.pem`

**核心文档**：
| Path | What | Notes/Owner |
|------|------|-------------|
| [AWS云服务器功能文档](docs/arch/AWS_CLOUD_SERVER_DOCUMENTATION__v0.1.0.md) | AWS云服务器完整功能文档 | 包含21个MCP工具、域名系统、HTTPS加密、OAuth认证、部署管理等详细说明 ⭐ **必读** |
| docs/arch/misc/GPT连接AWS_MCP指南.md | GPT连接指南 | ChatGPT连接AWS云服务器的完整配置指南 ⭐ |
| docs/arch/misc/AWS_MCP_Connection_Guide.md | AWS连接指南 | AWS MCP服务器连接和故障排查指南 ⭐ |

**部署文档**：
| Path | What | Notes/Owner |
|------|------|-------------|
| tools/mcp_bus/deploy/ec2_deployment.md | EC2部署指南 | AWS EC2实例部署详细步骤 |
| tools/mcp_bus/deploy/ec2_deploy.sh | EC2部署脚本 | 自动化EC2部署脚本 |
| tools/mcp_bus/deploy_aws.sh | AWS部署脚本 | 快速部署到AWS的脚本 |
| tools/mcp_bus/deploy_aws_docker.sh | Docker部署脚本 | 使用Docker容器部署 |
| tools/mcp_bus/deploy/dns_configuration.md | DNS配置指南 | 域名系统配置和DNS解析设置 |
| tools/mcp_bus/deploy/caddy_https_setup.md | Caddy HTTPS设置 | HTTPS加密、SSL证书自动续期配置 |
| tools/mcp_bus/deploy/caddy_setup.sh | Caddy设置脚本 | Caddy反向代理和HTTPS配置脚本 |
| tools/mcp_bus/deploy/cloudflared_tunnel.md | Cloudflare Tunnel | Cloudflare Tunnel配置指南 |
| tools/mcp_bus/deploy/ngrok.md | Ngrok配置 | Ngrok内网穿透配置指南 |
| [AWS SSH 连接指南](aws_ssh_guide.md) | AWS SSH 连接 | 连接 AWS 服务器的操作指南 |

**AWS云服务器特性**：
- ✅ 与本地总服务器功能完全一致（21个MCP工具）
- ✅ 域名系统集成（mcp.timquant.tech）
- ✅ 自动HTTPS加密（Caddy + Let's Encrypt）
- ✅ 自动证书续期
- ✅ OAuth 2.0认证支持
- ✅ 公网访问（全球可用）
- ✅ 反向代理（Caddy → MCP Bus）
- ✅ 健康检查和监控
- ✅ 服务管理和日志

### 1.3 ATA系统（Agent-to-Agent通信）

**核心标准与规范**：
| Path | What | Notes/Owner |
|------|------|-------------|
| docs/ARCH/ops/SUBAGENTS_MCP_ATA_STANDARD__v0.1.0.md | Sub-Agents MCP 与 ATA 融合标准 | 四角色最小集 + 映射规则 ⭐ |
| docs/ARCH/ops/ATA_ADMIN_RBAC__v0.1.0.md | ATA 管理员硬权限 | fail-closed 与 Admin Vault 说明 ⭐ |
| docs/ARCH/ops/ATA_COMMUNICATION_RULES__v0.1.0.md | ATA 通信规则 | 统一称呼=名字#NN、握手/发任务/回任务模板、回应强制三件套审计信息 ⭐ |
| [ATA 检查集成规范](docs/arch/ops/ata_check_integration__v0.1.0.md) | ATA 检查集成规范 | ATA 作为 verdict.checks 类型的集成规范，包括输入输出格式、证据目录结构等 |

**路由系统**：
| Path | What | Notes/Owner |
|------|------|-------------|
| docs/arch/ops/ATA_ROUTING_SYSTEM__v0.1.0.md | ATA路由系统完整指南 | ATA消息路由系统完整实现，支持基于角色的智能消息路由，包含13个角色（5个量化交易+5个软件工程+3个通用） ⭐ |
| docs/arch/ops/ATA路由系统使用示例.md | ATA路由系统使用示例 | ATA路由系统的实际使用示例，展示角色间消息路由和协作 ⭐ |
| docs/arch/ops/角色定义完整列表.md | 角色定义完整列表 | 所有13个角色的完整定义、职责、技能、路由目标和使用示例 ⭐ |

**Agent协作系统**：
| Path | What | Notes/Owner |
|------|------|-------------|
| docs/arch/ops/ATA_AGENT_COLLABORATION_UPGRADE_PLAN__v0.1.0.md | ATA Agent协作系统升级计划 | ATA系统升级为多Agent协作系统的完整计划，包括任务编排器、Agent协调器、结果聚合器和工作流引擎 ⭐ |
| docs/arch/ops/ATA_AGENT_COLLABORATION_USAGE_GUIDE__v0.1.0.md | ATA Agent协作系统使用指南 | ATA Agent协作系统的完整使用指南，包括快速开始、工作流执行、Agent管理和最佳实践 ⭐ |
| docs/arch/ops/ATA_AGENT_COLLABORATION_IMPLEMENTATION_REPORT__v0.1.0.md | ATA Agent协作系统实现报告 | P0和P1阶段实现完成报告，包括功能清单、配置文件说明和后续工作计划 ⭐ |
| docs/arch/ops/ATA_DIALOG_REGISTRATION_GUIDE__v0.1.0.md | ATA对话框注册与协作指南 | 如何将对话框与AI对应、注册编号、实现协作的完整指南 ⭐ |

**连接与触发**：
| Path | What | Notes/Owner |
|------|------|-------------|
| docs/arch/ops/CODEX_ATA_CONNECTION_GUIDE__v0.1.0.md | Codex连接ATA配置指南 | Cursor Codex连接本地总服务器和ATA通信系统的完整配置指南 ⭐ |
| docs/arch/ops/ATA_POLLING_TRIGGER_GUIDE__v0.1.0.md | ATA轮询触发指南 | 手动和定时脚本触发ATA消息轮询的完整指南 ⭐ |

### 1.4 开源项目集成

**AI Agent 与 A2A**：
| Path | What | Notes/Owner |
|------|------|-------------|
| [AI Agent系统集成综合指南](docs/arch/ops/AI_AGENT_SYSTEM_INTEGRATION_COMPLETE__v0.1.0.md) | AI Agent系统集成综合指南 | 整合全部 AI Agent 系统集成文档与工具：集成分析、融合状态、UI-TARS 集成、Cursor Agent 工具、安装配置、ATA 工作流与触发器、子代理系统、通信规则等；含来源文档索引，信息不遗失不稀释 ⭐ **必读** ⭐ **唯一入口** |
| [A2A Hub文档](docs/arch/A2A_HUB_DOCUMENTATION__v0.1.0.md) | A2A Hub完整文档 | 任务管理、Agent管理、容量管理、优先级调度、队列分区、RBAC、工作流管理 ⭐ |
| [A2A Worker文档](docs/arch/A2A_WORKER_DOCUMENTATION__v0.1.0.md) | A2A Worker完整文档 | 任务轮询、命令执行、输出控制、状态管理、交付物生成 ⭐ |
| [Collaboration A2A 架构](docs/arch/collaboration_a2a__v0.1.0__DRAFT__20260115.md) | Collaboration A2A 架构 | Collaboration A2A 架构主入口 |

**Cursor IDE 与 Agent 协作工具**：
| Path | What | Notes/Owner |
|------|------|-------------|
| docs/arch/ops/CURSOR_AGENT_INSTALLATION_GUIDE.md | Cursor Agent 协作工具安装指南 | Sub-Agents MCP、Cursor Agents Template、AgentBase 的完整安装和配置指南 ⭐ |
| docs/arch/ops/CURSOR_AGENT_QUICK_START.md | Cursor Agent 快速开始 | Cursor Agent 协作工具的快速开始指南，包含基本使用和测试方法 ⭐ |
| docs/arch/ops/CURSOR_AGENT_INSTALLATION_COMPLETE.md | Cursor Agent 安装完成报告 | Sub-Agents MCP 与 ATA 集成安装完成报告，包含功能验证和使用说明 ⭐ |
| docs/arch/ops/CURSOR_AGENT_INSTALLATION_SUMMARY.md | Cursor Agent 安装总结 | Cursor Agent 协作工具安装总结，包含核心功能状态和下一步操作 ⭐ |
| docs/arch/ops/CURSOR_AGENT_FINAL_REPORT.md | Cursor Agent 最终报告 | Cursor Agent 协作工具最终安装报告，包含所有测试结果和功能确认 ⭐ |
| docs/arch/ops/CURSOR_AGENT_COLLABORATION_GITHUB.md | Cursor Agent 协作 GitHub 项目汇总 | Cursor IDE 中 Agent 协作相关的 GitHub 项目汇总和推荐矩阵 ⭐ |
| docs/arch/ops/CURSOR_CHAT_OPTIMIZATION_GITHUB.md | Cursor Chat 优化 GitHub 项目汇总 | Cursor Chat 界面优化相关的 GitHub 项目汇总和推荐矩阵 ⭐ |
| docs/arch/ops/CURSOR_CHAT_SIDE_BY_SIDE.md | Cursor Chat 并排显示指南 | 如何在 Cursor IDE 中实现 Chat 页并排显示的完整指南 ⭐ |
| docs/arch/ops/CURSOR_MULTI_WINDOW_VISUALIZATION.md | Cursor 多窗口可视化指南 | Cursor IDE 多窗口和分屏显示可视化内容的完整指南 ⭐ |
| docs/arch/ops/CURSOR_EDITOR_LIMITS.md | Cursor 编辑器限制说明 | Cursor IDE 编辑器标签页、分屏等限制的详细说明 ⭐ |
| docs/arch/ops/CLAUDE_CODE_CURSOR_DEPLOYMENT.md | Claude Code Cursor 部署指南 | Claude Code 在 Cursor IDE 中的部署和使用指南，区分 Claude CoWorker 和 Claude Code ⭐ |

**桌面应用与开源方案**：
| Path | What | Notes/Owner |
|------|------|-------------|
| docs/arch/ops/WINDOWS_DESKTOP_AI_AGENT_GUI.md | Windows 桌面 AI Agent GUI 工具汇总 | Windows 操作界面直接给 AI 发消息的 agent 工具汇总，包括 ChatWizard、UI-TARS、自建方案等 ⭐ **桌面应用** |
| docs/arch/ops/CLAUDE_COWORK_OPEN_SOURCE_ALTERNATIVES.md | Claude Cowork 开源替代方案 | Claude Cowork 开源替代方案汇总，包括 Agent Cowork、OpenWork 等，MIT 许可证，可自托管 ⭐ **开源方案** |
| [Claude 系统托盘应用](tools/desktop/claude_tray_app.py) | Windows 系统托盘 AI 对话应用 | 在 Windows 系统托盘提供快速 AI 对话界面，支持 Claude API，无需打开浏览器 ⭐ **已实现** |
| [桌面应用使用文档](tools/desktop/README.md) | Claude 托盘应用使用指南 | 安装、配置、使用说明，包含故障排除和未来增强计划 |

**AI Agent 能力与 ATA 集成**：
| Path | What | Notes/Owner |
|------|------|-------------|
| docs/arch/ops/AI_AGENT_CAPABILITIES.md | AI Agent 功能与能力详解 | AI Agent 的完整功能列表，包括文件操作、Shell 命令、浏览器自动化、多模态交互、任务规划等 ⭐ **功能参考** |
| docs/arch/ops/AI_AGENT_AS_ATA_TRIGGER.md | AI Agent 作为 ATA 激发器 | AI Agent 功能作为 ATA 系统激发器的集成方案，包括文件监控、命令执行、浏览器自动化等触发机制 ⭐ **集成方案** |
| docs/arch/ops/UI_TARS_VS_AI_AGENT_CAPABILITIES.md | UI-TARS 与 AI Agent 能力对比 | UI-TARS-desktop 与通用 AI Agent 功能对比分析，明确一致性和差异，以及互补关系 ⭐ **对比分析** |
| docs/arch/ops/SYSTEM_EFFICIENCY_IMPROVEMENTS.md | 系统效率提升方案（非软件工具类） | 除软件工具外的效率提升方向：流程优化、配置管理、数据管理、基础设施、开发实践、监控诊断、团队协作等 ⭐ **效率提升** |

**Sub-Agents 与工程习惯**：
| Path | What | Notes/Owner |
|------|------|-------------|
| tools/subagents/README.md | Sub-Agents MCP 使用说明 | Sub-Agents MCP 与 ATA 集成的快速使用说明 |
| tools/subagents/ata_adapter.py | ATA 适配器 | Sub-Agents MCP 与 ATA 消息系统的适配器实现 |
| tools/subagents/final_verification.py | 最终验证脚本 | 验证所有 Sub-Agents MCP 与 ATA 集成功能的测试脚本 |
| tools/subagents/test_integration.py | 集成测试脚本 | Sub-Agents MCP 与 ATA 集成的集成测试脚本 |
| tools/subagents/test_ata_collaboration.py | ATA 协作测试脚本 | 测试子代理通过 ATA 消息系统协作的测试脚本 |
| docs/arch/ops/MCP_TECHNICAL_DETAILS.md | MCP 工程习惯技术细节 | 工程标准与流程规范 |
| docs/arch/ops/USER_RULES_PERSONAL.md | 个人习惯规范 | 个人工作习惯与沟通规则 |
| docs/arch/ops/ROOT_DIRECTORY_GOVERNANCE.md | 根目录文件治理规范 | 规范根目录文件存放，禁止文件堆积（每次对话自动读取）⭐ |
| docs/arch/ops/PERSONAL_WORKFLOW_RULES.md | 个人工作流程规范 | 个人工作流程、文件管理习惯和 AI 协作约定（每次对话自动读取）⭐ |
| docs/arch/ops/TASK_COMPLETION_GOAL_CHECK_HOOK.md | 任务完成前目标检查 Hook | 在任务完成前重新检查目标，未达成则继续执行（每次对话自动读取）⭐ |

### 1.5 技术架构与配置

| 组件 | 技术栈 | 说明 |
|------|--------|------|
| 后端框架 | FastAPI | Python异步Web框架 |
| 前端框架 | Vue.js + Vite | FreqUI前端 |
| 静态文件服务 | FastAPI StaticFiles | 服务Web Viewer和FreqUI静态文件 |
| API代理 | HTTPX | 异步HTTP客户端，转发FreqUI API请求 |
| WebSocket代理 | FastAPI WebSocket | 支持FreqUI WebSocket连接（预留） |
| 通信协议 | JSON-RPC 2.0 | MCP标准协议 |
| 部署方式 | Uvicorn | ASGI服务器 |

| Path | What | Notes/Owner |
|------|------|-------------|
| tools/mcp_bus/config/config.example.json | MCP配置文件示例 | 包含路径配置、安全设置等 |
| .cursor/mcp.json | Cursor MCP配置 | Cursor IDE连接本地总服务器的配置 |
| configs/secrets.yaml.template | 密钥配置模板 | 密钥配置文件模板，包含API密钥配置说明 ⚠️ **请勿提交真实密钥** |
| **环境变量配置** | **LangGraph/LangChain API密钥** | **OPENAI_API_KEY**: OpenAI API密钥（用于LangGraph/LangChain）<br>**LANGCHAIN_API_KEY**: LangSmith API密钥（可选，用于监控）<br>**设置方式**: `$env:OPENAI_API_KEY = "your-key"` ⚠️ **密钥配置** |

## 第二部分：交易层 (Trading Layer)

### 2.1 核心业务系统（订单、执行、投资组合、策略、因子、数据、模型、监控）

| Path | What | Notes/Owner |
|------|------|-------------|
| [监控系统文档](docs/arch/MONITOR_SYSTEM_DOCUMENTATION__v0.1.0.md) | 监控系统完整文档 | 包含6个监控组件（策略监控、实时指标、实时监督、容量监控、降级监控、性能监控）的详细说明 ⭐ **核心系统** |
| [订单系统文档](docs/arch/ORDER_SYSTEM_DOCUMENTATION__v0.1.0.md) | 订单系统完整文档 | 包含订单管理器、订单状态机、幂等性保证、订单日志等功能的详细说明 ⭐ **核心系统** |
| [模型系统文档](docs/arch/MODELS_SYSTEM_DOCUMENTATION__v0.1.0.md) | 模型系统完整文档 | 包含4个模型（成本模型、成交模型、清算模型、保证金模型）的详细说明 ⭐ **核心系统** |
| [投资组合系统文档](docs/arch/PORTFOLIO_SYSTEM_DOCUMENTATION__v0.1.0.md) | 投资组合系统完整文档 | 包含投资组合管理器、仓位管理器、资金分配器、仓位平滑器等功能的详细说明 ⭐ **核心系统** |
| [执行系统基础文档](src/quantsys/execution/README.md) | 执行系统基础文档 | 执行系统总体架构和核心功能说明 ⭐ **核心系统** |
| [执行系统子模块文档](docs/arch/EXECUTION_SUBMODULES_DOCUMENTATION__v0.1.0.md) | 执行系统子模块完整文档 | 包含门禁系统、订单执行、执行管理、对账系统、就绪检查、灾难恢复等子模块的详细说明 ⭐ **执行系统子模块** |
| [数据系统基础文档](src/quantsys/data/README.md) | 数据系统基础文档 | 数据系统总体架构和核心功能说明 ⭐ **核心系统** |
| [数据系统子模块文档](docs/arch/DATA_SUBMODULES_DOCUMENTATION__v0.1.0.md) | 数据系统子模块完整文档 | 包含数据质量门禁、数据漂移门禁、数据版本管理、实时数据管理器等子模块的详细说明 ⭐ **数据系统子模块** |
| [因子系统基础文档](src/quantsys/factors/README.md) | 因子系统基础文档 | 因子系统总体架构和核心功能说明 ⭐ **核心系统** |
| [因子系统子模块文档](docs/arch/FACTORS_SUBMODULES_DOCUMENTATION__v0.1.0.md) | 因子系统子模块完整文档 | 包含因子质量门禁、因子优化器、自动因子生成器、因子准入等子模块的详细说明 ⭐ **因子系统子模块** |
| [因子挖掘模块工作原理](docs/ARCH/factors/FACTOR_MINING_WORKFLOW__v0.1.0.md) | 因子挖掘工作流程 | 详细说明因子挖掘模块的工作原理，包括算子组合法、5层搭积木法、深度学习法和混合方法 ⭐ **因子挖掘** ⭐ **必读** |
| [因子模块完整结构](docs/ARCH/factors/FACTOR_MODULE_COMPLETE_STRUCTURE__v0.1.0.md) | 因子模块完整结构 | 因子模块除挖掘外的10个主要部分：因子库、注册表、评估、优化、准入、质量门禁、存储、引擎、特征工程、工具 ⭐ **因子系统架构** ⭐ **必读** |
| [因子模块前后端同步检查](docs/ARCH/factors/FACTOR_MODULE_FRONTEND_BACKEND_SYNC__v0.1.0.md) | 前后端同步情况 | 检查因子模块10个功能在前后端的同步情况，识别已实现、部分实现和未实现的功能，提供实现优先级建议 ⭐ **同步检查** ⭐ **必读** |
| [因子库排行表格生成脚本](scripts/generate_factor_ranking_table.py) | 因子排行表格工具 | 从因子库调取数据，生成多种排序方式的排行表格（按类型、版本数量、使用情况），输出CSV和Markdown格式 ⭐ **因子分析工具** |
| [策略系统基础文档](src/quantsys/strategy/README.md) | 策略系统基础文档 | 策略系统总体架构和核心功能说明 ⭐ **核心系统** |
| [策略系统子模块文档](docs/arch/STRATEGY_SUBMODULES_DOCUMENTATION__v0.1.0.md) | 策略系统子模块完整文档 | 包含策略冲突解决器、策略筛选、策略快照、策略包构建器等子模块的详细说明 ⭐ **策略系统子模块** |
| [风险系统基础文档](src/quantsys/risk/README.md) | 风险系统基础文档 | 风险系统总体架构和核心功能说明 ⭐ **核心系统** |
| docs/REPORT/tasks/TC-TRADING-SYSTEM-REVIEW-001/trading_system_review.md | 交易系统架构与代码审查报告 | 交易系统整体架构、核心代码审查，包含30个具体问题和改进建议 ⭐ |
| docs/REPORT/tasks/TC-TRADING-SYSTEM-REVIEW-001/改进建议执行清单.md | 改进建议执行清单 | 交易系统改进建议的执行清单，按优先级分类，包含工作量估算和风险评估 ⭐ |

### 2.2 辅助系统（调度、状态、故障注入、回测、通知）

| Path | What | Notes/Owner |
|------|------|-------------|
| [调度系统文档](docs/arch/SCHEDULER_SYSTEM_DOCUMENTATION__v0.1.0.md) | 调度系统完整文档 | 包含因子调度器、刷新状态管理、可用性检查等功能的详细说明 ⭐⭐ **辅助系统** |
| [状态系统文档](docs/arch/STATE_SYSTEM_DOCUMENTATION__v0.1.0.md) | 状态系统完整文档 | 包含权重估计器、状态标签生成、迟滞效应管理等功能的详细说明 ⭐⭐ **辅助系统** |
| [故障注入系统文档](docs/arch/FAULT_INJECTION_SYSTEM_DOCUMENTATION__v0.1.0.md) | 故障注入系统完整文档 | 包含故障配置管理、故障触发和恢复、故障状态跟踪等功能的详细说明 ⭐⭐ **辅助系统** |
| [回测系统详细文档](docs/arch/BACKTEST_SYSTEM_DETAILED_DOCUMENTATION__v0.1.0.md) | 回测系统详细文档 | 包含回测引擎、回测执行、回测可视化、压力场景、多策略对比等功能的详细说明 ⭐⭐ **辅助系统** |

### 2.3 系统级架构文档（系统集成、数据流和状态机）

| Path | What | Notes/Owner |
|------|------|-------------|
| [系统集成文档](docs/arch/SYSTEM_INTEGRATION_DOCUMENTATION__v0.1.0.md) | 系统集成完整文档 | 包含本地总服务器与AWS云服务器、监控系统与Dashboard、数据系统与数据库、执行系统与Freqtrade、A2A Hub与MCP服务器等集成架构说明 ⭐ **系统架构** |
| [数据流和状态机文档](docs/arch/DATAFLOW_STATEMACHINE_DOCUMENTATION__v0.1.0.md) | 数据流和状态机完整文档 | 包含完整数据流图、订单状态机、策略状态机、任务状态机、执行就绪状态机的详细说明 ⭐ **系统架构** |
| [通知系统文档](docs/arch/NOTIFICATIONS_SYSTEM_DOCUMENTATION__v0.1.0.md) | 通知系统完整文档 | 包含桌面通知、企业微信、Telegram、本地日志等通知渠道的详细说明 ⭐ **系统架构** |

### 2.4 核心工具和入口（回测、数据下载器）

| Path | What | Notes/Owner |
|------|------|-------------|
| [统一回测入口文档](docs/BACKTEST/unified_backtest_entry_documentation.md) | 统一回测入口 | QuantSys系统唯一的回测入口点，整合所有回测功能，提供统一API接口 ⭐⭐⭐ **核心入口** |
| [统一市场数据下载器](corefiles/unified_market_data_downloader.py) | 统一市场数据下载器 | 整合所有下载功能，支持智能/全量/增量三种模式，硬执行功能（避免重复下载、增量下载、数据格式统一、自动去重、自动保存）。可作为脚本运行或作为类被AI直接使用 ⭐ **唯一下载器** ⭐ **推荐使用** ⭐ **AI直接使用** |
| [统一下载进度检查和报告器](scripts/unified_download_progress_checker.py) | 统一下载进度检查器 | 整合所有下载进度检查功能（基础检查、详细检查、进度报告、监控模式），作为唯一的检查入口 ⭐ **唯一检查器** ⭐ **推荐使用** |
| [数据下载完整指南](docs/DATA_DOWNLOAD_GUIDE.md) | 数据下载指南 | 完整的数据下载指南，汇总所有下载方法、文档链接和使用示例 ⭐ **使用指南** |
| [避免重复下载规则](docs/TEST/avoid_duplicate_download_rules.md) | 避免重复下载规则 | 数据下载的去重规则，避免重复下载相同数据 ⭐ **规则文档** |
| [下载器硬执行功能实现报告](docs/TEST/downloader_hard_enforcement_20260122.md) | 硬执行功能报告 | 下载器硬执行功能实现报告，包含避免重复下载、增量下载、数据格式统一、自动去重、自动保存的完整实现 ⭐ **实现报告** |
| [配置问题排查和修复报告](docs/TEST/config_issue_fix_20260122.md) | 配置问题修复 | 配置问题排查和修复报告，包含代理配置优化、错误日志增强、配置验证增强 ⭐ **问题修复** |
| [数据合并去重脚本](scripts/merge_and_deduplicate_data.py) | 数据合并工具 | 合并和去重不同格式的交易对数据，统一为标准格式 ⭐ **数据清理工具** |
| [本地数据回测测试结果](docs/TEST/local_data_backtest_test_results.md) | 回测功能测试 | 测试freq内的本地数据回测功能，验证从PostgreSQL数据库读取数据进行回测的能力 ⭐ **测试报告** |

### 2.5 数据源与API集成（OKX API）

| Path | What | Notes/Owner |
|------|------|-------------|
| [OKX API 综合指南](docs/TROUBLESHOOTING/OKX_API_INTEGRATED_GUIDE__v0.1.0.md) | OKX API 综合指南 | 整合 2.5 所列全部 OKX 文档与工具：连接与配置、2026 年 API 要求、故障排除、错误分析、测试与脚本；含来源文档索引，信息不遗失不稀释 ⭐ **必读** ⭐ **唯一入口** |

## 第三部分：显示层 (Display Layer)

### 3.1 统一管理平台

| Path | What | Notes/Owner |
|------|------|-------------|
| http://127.0.0.1:8000 | 量化系统统一管理平台 | 单点入口，集成Web Viewer、Dashboard、配置管理、FreqUI、本地总服务器、健康检查 ⭐ **统一入口** |
| http://127.0.0.1:8000/dashboard | Dashboard（通过本地总服务器） | Dashboard已集成到本地总服务器，自动启动，无需单独启动 ⭐ **推荐访问方式** |
| [总网页和总服务器文档](docs/arch/总网页和总服务器__v0.1.0.md) | 总网页和总服务器完整文档 | 总服务器（21个MCP工具+15个REST API+6个Web服务）和总网页（统一管理平台）的完整说明 ⭐ **核心入口文档** |
| tools/mcp_bus/web_viewer/dashboard.html | 统一平台首页 | 左侧导航栏，包含六个主要模块 |
| tools/mcp_bus/server/main.py | 本地总服务器主程序 | FastAPI应用，提供API代理和静态文件服务，自动启动Dashboard |
| http://127.0.0.1:8051 | Dashboard控制中心（直接访问） | Dash应用，包含配置管理、交易控制、日志查看等功能（内部端口） |
| scripts/dashboard/app.py | Dashboard主应用 | 集成配置管理、交易控制、风险管理等功能 |

### 3.2 Dashboard（量化控制中心）

| Path | What | Notes/Owner |
|------|------|-------------|
| http://127.0.0.1:8000/dashboard | Dashboard（通过本地总服务器） | Dashboard已集成到本地总服务器，自动启动，推荐访问方式 ⭐ **推荐** |
| http://127.0.0.1:8051 | Dashboard控制中心（直接访问） | Dash应用，量化交易控制中心（内部端口，本地总服务器自动启动） |
| scripts/dashboard/app.py | Dashboard主应用 | 集成配置管理、交易控制、风险管理等功能 |
| tools/mcp_bus/server/main.py | 本地总服务器（含Dashboard集成） | FastAPI应用，自动启动Dashboard，提供代理路由 |
| scripts/dashboard/config_api.py | 配置管理API | 配置管理API路由，集成到Dashboard服务器 |
| scripts/dashboard/navigation.py | 导航栏组件 | Dashboard顶部导航栏 |
| [Dashboard 集成到本地总服务器](docs/DASHBOARD/dashboard_mcp_integration.md) | Dashboard MCP 集成 | Dashboard 已集成到本地总服务器，自动启动，经 8000 端口统一访问 ⭐ **重要** |
| [Dashboard 启动说明](docs/DASHBOARD/START_DASHBOARD.md) | Dashboard 启动 | 快速启动指南（含独立启动方式） ⭐ **必读** |
| [Dashboard 问题排查](docs/DASHBOARD/dashboard_troubleshooting.md) | Dashboard 问题排查 | 启动问题排查与解决方案 |

**功能特性**：
- ✅ 交易控制（启动/停止、模式切换）
- ✅ 自检功能（Preflight检查）
- ✅ 日志查看（实时日志、错误摘要）
- ✅ 权益曲线（Equity、Drawdown）
- ✅ 交易和持仓（Trades、Positions、Orders）
- ✅ 信号图表（Signals）
- ✅ 风险管理（Risk Summary、Pairlocks）
- ✅ **配置管理** ⭐ - 集中管理所有配置文件（JSON/YAML）
- ✅ **交易系统UI集成** ⭐ - P0/P1改进功能已全部接入Dashboard（8个功能模块：账户服务、风险门禁、信号总线、订单执行器、状态存储、异常处理、交易所适配器、订单验证器），详见 [交易系统UI集成方案](docs/arch/交易系统UI集成方案.md) 和 [交易系统UI集成完成报告](docs/arch/交易系统UI集成完成报告.md)

### 3.3 Web Viewer（ATA多方会话记录系统）

| Path | What | Notes/Owner |
|------|------|-------------|
| http://127.0.0.1:8000/viewer | ATA Web Viewer | 查看GPT、Cursor、TRAE三方通信记录 |
| tools/mcp_bus/web_viewer/index.html | Web Viewer前端 | Vue.js界面，支持筛选、搜索、消息详情 |
| /api/viewer/messages | 消息列表API | 获取ATA消息，支持筛选（from_agent, to_agent, kind, taskcode） |
| /api/viewer/statistics | 统计信息API | 获取消息总数、参与代理数、会话数量等 |
| /api/viewer/agents | 代理列表API | 获取所有参与通信的代理名称 |

**功能特性**：
- ✅ 智能滚动位置恢复（基于消息ID锚点）
- ✅ 静默刷新（自动刷新时不显示加载指示器）
- ✅ 用户滚动检测（滚动时暂停自动刷新）
- ✅ 页面可见性检测（标签页隐藏时暂停刷新）
- ✅ 内容变化检测（只有新消息时才更新DOM）
- ✅ 刷新频率优化（15秒自动刷新）
- ✅ 平滑滚动（scroll-behavior: smooth）
- ✅ 防止布局偏移（min-height设置）
- ✅ 三方代理筛选（GPT、Cursor、TRAE）

### 3.4 配置管理系统

| Path | What | Notes/Owner |
|------|------|-------------|
| http://127.0.0.1:8051 | Dashboard（配置管理Tab） | 通过Dashboard访问配置管理 |
| http://127.0.0.1:8000/config | 配置管理（通过统一平台） | 通过统一管理平台访问配置管理 |
| scripts/dashboard/config_api.py | 配置管理API | 提供配置的读取、保存、验证、备份等API |
| scripts/dashboard/config_manager.py | 配置管理UI | Dash组件，可视化配置编辑界面 |
| configs/current/ | 当前配置目录 | 所有配置文件统一入口 |
| configs/_backup/ | 配置备份目录 | 自动备份的配置文件 |

**支持的配置文件**：
- `config.json` - 系统主配置
- `config_live.json` - 实盘交易配置
- `freqtrade_config.json` - Freqtrade配置
- `cloud_sync_config.json` - 云端同步配置
- `config_okx_aws.yaml` - OKX AWS配置

**功能特性**：
- ✅ 集中管理：统一管理所有配置文件
- ✅ 可视化编辑：友好的Web界面，支持JSON/YAML
- ✅ 实时验证：基于Pydantic Schema的配置验证
- ✅ 自动备份：保存前自动备份
- ✅ 备份恢复：一键恢复历史备份

### 3.5 FreqUI（交易界面）

| Path | What | Notes/Owner |
|------|------|-------------|
| http://127.0.0.1:8000/frequi | FreqUI交易界面 | 集成Freqtrade UI，支持策略管理、回测、实盘交易 |
| frequi-main/ | FreqUI源码目录 | Vue.js + Vite构建，支持个性化修改 |
| /frequi/api/v1 | FreqUI API代理 | 通过本地总服务器转发到Freqtrade后端 |
| tools/mcp_bus/FreqUI个性化修改指南.md | FreqUI修改指南 | 说明如何直接修改源码或使用开发模式 |

**功能特性**：
- ✅ 静态文件服务（assets目录）
- ✅ API代理转发（支持CORS和OPTIONS请求）
- ✅ WebSocket代理（预留接口）
- ✅ 基础路径配置（base: '/frequi/'）
- ✅ 个性化修改支持（直接修改源码）

### 3.6 相关文档

#### Dashboard和配置管理文档

| Path | What | Notes/Owner |
|------|------|-------------|
| docs/arch/统一平台集成说明.md | 统一平台集成说明 | Dashboard和配置管理系统集成到统一管理平台的详细说明 |
| docs/arch/配置管理集成完成报告.md | 配置管理集成完成报告 | 配置管理系统集成工作的完整报告 |
| docs/arch/交易系统UI集成方案.md | 交易系统UI集成方案 | P0/P1改进功能接入Dashboard的详细方案，包含8个功能模块的集成建议 ⭐ |
| docs/arch/交易系统UI集成完成报告.md | 交易系统UI集成完成报告 | 交易系统UI集成实施完成报告，8个功能模块已全部接入Dashboard，包含组件清单、API端点、文件清单等 ⭐ |
| docs/arch/交易系统UI集成测试指南.md | 交易系统UI集成测试指南 | 交易系统UI集成的测试指南，包含自动化测试脚本、手动测试步骤、故障排查等 ⭐ |
| scripts/dashboard/test_ui_integration.py | UI集成测试脚本 | 自动化测试脚本，测试8个功能模块的API端点和组件导入 |
| scripts/dashboard/README_CONFIG.md | Dashboard配置管理说明 | Dashboard中配置管理功能的详细说明 |
| scripts/dashboard/README_NAVIGATION.md | Dashboard导航说明 | Dashboard导航系统说明 |
| tools/config_manager/集成说明.md | 配置管理系统集成说明 | 配置管理系统集成到Dashboard的说明 |
| tools/config_manager/README.md | 配置管理系统文档 | 配置管理系统的完整文档 |

#### 其他相关文档

| Path | What | Notes/Owner |
|------|------|-------------|
| ATA优化完成总结.md | ATA优化总结 | 详细说明ATA功能优化内容 |
| FreqUI个性化修改指南.md | FreqUI修改指南 | 如何对FreqUI进行个性化修改 |
| tools/mcp_bus/README.md | 本地总服务器说明 | 本地总服务器的详细说明 |

## 第四部分：控制面与工程管理

### 4.1 宪法典与执行规则

| Path | What | Notes/Owner |
|------|------|-------------|
| law/QCC-README.md | QuantSys 宪法与执行规则总入口 | 系统最高法源 |
| docs/ARCH/ops/SUBAGENTS_MCP_ATA_STANDARD__v0.1.0.md | Sub-Agents MCP 与 ATA 融合标准（四角色最小集 + 映射规则） | ATA系统 |
| docs/ARCH/ops/ATA_ADMIN_RBAC__v0.1.0.md | ATA 管理员硬权限（fail-closed）与 Admin Vault 说明 | ATA系统 |
| docs/constitution/QUANTSYS_CONSTITUTION_V1.1.md | QuantSys 宪法 v1.1（Legacy） | Legacy/DoNotUse；仅作历史参考，不得作为规则入口；应迁至 legacy/docs_navigation/ |

### 4.2 Skills文档汇总

| Path | What | Notes/Owner |
|------|------|-------------|
| [Skills完整文档汇总](docs/arch/skills/SKILLS_COMPLETE_DOCUMENTATION__v0.1.0.md) | Skills完整文档 | 包含本地技能列表（22个）、系统内置技能（5个）、系统技能列表（23个）的完整汇总 ⭐ **完整文档** |
| docs/arch/skills/skills_documentation.md | Skills 文档汇总 | 包含所有本地 skills 的详细描述、输入输出 Schema 等信息 |
| docs/arch/skills/trae_skills_documentation.md | Trae 技能文档汇总 | 包含Trae配置界面中所有技能的详细描述和功能列表 |
| docs/arch/skills/CURSOR_SKILLS_IMPORT.md | Cursor Skills 导入文档 | 包含所有技术能力文档（Skills）的完整信息，供 Cursor AI 使用 |

### 4.3 CI完备性系统

#### 4.3.1 核心规范与合约

| Path | What | Notes/Owner |
|------|------|-------------|
| [Verdict合约规范](docs/arch/control_plane/VERDICT_CONTRACT_SPEC__v0.1.0.md) | Verdict合约规范 | 定义mvm-verdict.py（生成者）与pre-receive hook（裁判）对verdict.json的字段和语义要求，确保合约一致性 ⭐ **CI核心** |
| [Phase4证据Supersede规则](docs/arch/control_plane/PHASE4_EVIDENCE_SUPERSEDE_RULE__v0.1.0.md) | Phase4证据Supersede规则 | 定义当同一任务存在多份Phase4检查结果时的权威性判定和supersede关系规则 ⭐ **CI核心** |
| [Phase4证据权威性规则](docs/arch/control_plane/PHASE4_EVIDENCE_AUTHORITY_RULE__v0.1.0.md) | 证据权威性规则 | 定义 Phase4 证据权威性规则，明确哪份证据是权威，如何 supersede ⚠️ **重要** |
| [门禁权威来源锁定规范](docs/arch/control_plane/GATE_AUTHORITY_SOURCE__v0.1.0.md) | 门禁权威来源锁定规范 | 明确bare repo门禁的唯一权威路径（<ABS_PATH>/git_hooks/pre-receive），要求审计时只认这一份 ⭐ **CI核心** |
| [Gate 规则说明](docs/spec/qcc_enforcement_spec_v1.0.0.md) | 门禁规则规范 | QCC 强制执行规范与 Fail-Closed 机制说明 |
| [控制面保护说明](docs/arch/control_plane_protection__v0.1.0__20260115.md) | 控制面保护说明 | 受保护路径、触发条件、回滚方法的详细说明 |
| [MVM 门禁工作流](docs/arch/control_plane/mvm_defender_workflow__v0.1.0.md) | MVM 门禁工作流 | MVM 门禁方案的详细工作流程、错误处理与验收标准 |

#### 4.3.2 控制面导航入口

| Path | What | Notes/Owner |
|------|------|-------------|
| [Program Board](docs/arch/program_board__v0.1.0__ACTIVE__20260115.md) | 任务看板 | 控制面板-任务状态追踪主入口 |
| [聚合 Program Board](docs/arch/program_board_aggregate.md) | 自动聚合任务看板 | 自动生成的REPORT聚合看板 |
| [静态 Program Board](docs/REPORT/_index/PROGRAM_BOARD__STATIC.md) | 静态任务看板 | 自动生成的静态Program Board |
| [今日 Inbox](docs/REPORT/inbox/2026-01-15.md) | 每日收件箱 | 控制面板-日更收件记录 |
| [ATA Ledger](docs/REPORT/_index/ATA_LEDGER__STATIC.md) | ATA Ledger | ATA记录总入口 |
| [ATA 规范文档](docs/REPORT/ata/REPORT__ATA-LEDGER-STATIC-v0.1__20260115.md) | ATA 规范文档 | ATA规范与使用说明 |
| [REPORT 模板入口](docs/templates/template_report.md) | 报告模板 | 任务报告标准模板（挂载链接） |
| [文档归档规范](docs/REPORT/docs_governance/REPORT__DOC-ARCHIVE-POLICY-v0.1__20260115.md) | 文档归档规范 | 报告文件、自测日志和证据附件的存储规则 |

#### 4.3.3 验证与门禁工具

| Path | What | Notes/Owner |
|------|------|-------------|
| [Verify Hardness 使用指南](docs/arch/verify_hardness_howto.md) | Verify Hardness 使用指南 | 硬度验证功能的使用说明，包括运行方式、结果判定和产物落点 |
| [CI Hardness Gate 指南](docs/arch/ci_hardness_gate_guide.md) | CI 硬度门禁指南 | 说明 CI 必跑 verify_hardness，绿勾是唯一推进信号 |
| [tools/gatekeeper/](tools/gatekeeper/) | 门禁工具 | 代码质量检查与门禁 |
| [tools/docs_governance/](tools/docs_governance/) | 文档治理工具 | 文档质量检查与治理 |

#### 4.3.4 MVM 完备 CI 系统（Phase 0-5）

**路线图与总览**：

| Path | What | Notes/Owner |
|------|------|-------------|
| [MVM 完备 CI 路线图](docs/arch/control_plane/MVM_COMPLETE_CI_ROADMAP__v0.1.0.md) | MVM 完备 CI 路线图 | MVM 升级为完备 CI 的 6 阶段路线图，包含达标要求和攻击验证 ⭐ |
| [🎉 MVM 完备 CI 达成报告](docs/REPORT/control_plane/REPORT__MVM_COMPLETE_CI_ACHIEVED__20260120__20260120.md) | MVM 完备 CI 达成 | 所有 Phase（0-5）已完成，MVM 完备 CI 已达成，包含所有验收标准和攻击验证（19个攻击场景全部通过） |
| [⚠️ CI 完备性审查报告](docs/REPORT/control_plane/REPORT__CI_COMPLETENESS_AUDIT__20260120__20260120.md) | CI 完备性审查 | 审查"CI 完备"判定口径，识别证据不一致和口径缺陷，定义硬条件判定标准 ⚠️ **重要** |
| [CI 完备性修复报告](docs/REPORT/control_plane/REPORT__CI_COMPLETENESS_FIX__20260120__20260120.md) | CI 完备性修复 | 修复所有 CI 完备性审查中发现的问题，确保所有硬条件满足 |
| [CI 关键问题修复报告](docs/REPORT/control_plane/REPORT__CI_CRITICAL_FIXES__20260120__20260120.md) | CI 关键问题修复 | 修复所有 CI 关键问题（fail-closed、证据权威性、文档链接等） |
| [CI 缺口修复报告](docs/REPORT/control_plane/REPORT__CI_GAP_FIXES__20260120__20260120.md) | CI 缺口修复 | 修复所有 CI 缺口（P0-P4：hook 合约、verdict 合约、checks 可信、selftest 冲突、docs-governance） ⚠️ **重要** |
| [CI 规范口径对齐修复报告](docs/REPORT/control_plane/REPORT__CI_SPEC_ALIGNMENT__20260120__20260120.md) | CI 规范口径对齐 | 修复所有 CI 规范口径冲突和语义不一致（运行环境分流、可信 CI 证据、selftest 规则、evidence_paths 语义、证据哈希清单格式） ⚠️ **重要** |

**Phase 0: 基线巩固**

| Path | What | Notes/Owner |
|------|------|-------------|
| [Phase 0 基线巩固报告](docs/REPORT/control_plane/REPORT__PHASE0_BASELINE_COMPLETE__20260120__20260120.md) | Phase 0 完成报告 | Phase 0 基线巩固实施完成，包含 KeyID 白名单检查和 tag 不可移动检查 |
| [Phase 0 攻击变种清单](docs/arch/control_plane/PHASE0_ATTACK_VARIANTS__v0.1.0.md) | Phase 0 攻击变种 | 30个攻击变种清单，涵盖 Tag 存在性、KeyID 白名单、Tag 不可移动、分支绕过、时间戳格式等攻击类型 |
| [Phase 0 攻击执行报告](docs/REPORT/control_plane/REPORT__PHASE0_ATTACK_EXECUTION__20260120.md) | Phase 0 攻击执行 | 使用30个攻击变种对系统进行实际攻击测试的报告，包含测试结果、环境限制和解决方案 |
| [Phase 0 攻防对抗总结](docs/REPORT/control_plane/REPORT__PHASE0_ATTACK_DEFENSE_SUMMARY__20260120.md) | Phase 0 攻防总结 | Phase 0 攻防对抗测试结果总结，判定防方获胜（防御机制100%实现，攻击突破率0%） |
| [pre-receive-phase0.sh](tools/ci/pre-receive-phase0.sh) | Phase 0 服务器端钩子 | 实现 bare repo pre-receive 钩子，检查 mvm/pass/* tag、GPG 签名、KeyID 白名单、tag 不可移动 |
| [test_phase0_attacks.py](tools/ci/test_phase0_attacks.py) | Phase 0 攻击测试脚本 | 逻辑验证脚本，测试 Phase 0 防御机制 |
| [test_phase0_all_attacks.py](tools/ci/test_phase0_all_attacks.py) | Phase 0 全部攻击测试 | 执行所有 Phase 0 攻击变种的测试脚本 |
| [execute_phase0_attacks.py](tools/ci/execute_phase0_attacks.py) | Phase 0 攻击执行脚本 | 在实际 bare repo 环境中执行攻击测试 |

**Phase 1: Verdict 合约**

| Path | What | Notes/Owner |
|------|------|-------------|
| [Phase 1 Verdict 合约报告](docs/REPORT/control_plane/REPORT__PHASE1_VERDICT_CONTRACT__20260120__20260120.md) | Phase 1 完成报告 | Phase 1 放行语义升级为 verdict 合约实施完成，包含 verdict.json 生成和 server-side 校验 |
| [MVM CI Verdict 绑定报告](docs/REPORT/control_plane/REPORT__MVM_CI_VERDICT_BINDING__20260120.md) | Verdict 绑定实施 | MVM CI Verdict 绑定实施报告，从"仅 tag 验证"升级为"tag 验证 + verdict 强绑定 + 证据可复核" |
| [pre-receive-phase1.sh](tools/ci/pre-receive-phase1.sh) | Phase 1 服务器端钩子 | Phase 0 + Phase 1，检查 verdict.json 存在性、commit_sha 匹配、三元组路径存在性 |
| [test_phase1_attacks.py](tools/ci/test_phase1_attacks.py) | Phase 1 攻击测试脚本 | 逻辑验证脚本，测试 verdict 合约验证机制 |

**Phase 2: Guard 集成**

| Path | What | Notes/Owner |
|------|------|-------------|
| [Phase 2 Guard 集成报告](docs/REPORT/control_plane/REPORT__PHASE2_GUARD_INTEGRATION__20260120__20260120.md) | Phase 2 完成报告 | Phase 2 引入"技能调用状态机 + guard"实施完成，包含所有漏洞类拦截和攻击验证 |
| [pre-receive-phase2.sh](tools/ci/pre-receive-phase2.sh) | Phase 2 服务器端钩子 | Phase 0-1 + Phase 2，检查 guard 状态为 PASS 和 guard_version |
| [test_phase2_attacks.py](tools/ci/test_phase2_attacks.py) | Phase 2 攻击测试脚本 | 逻辑验证脚本，测试 TOCTOU、缺失三元组、证据 symlink、大小写绕过、静默回滚等攻击 |

**Phase 3: 证据哈希绑定**

| Path | What | Notes/Owner |
|------|------|-------------|
| [Phase 3 证据哈希绑定报告](docs/REPORT/control_plane/REPORT__PHASE3_EVIDENCE_HASH__20260120__20260120.md) | Phase 3 完成报告 | Phase 3 证据哈希绑定与 server-side 重算复核实施完成，包含所有攻击验证 |
| [pre-receive-phase3.sh](tools/ci/pre-receive-phase3.sh) | Phase 3 服务器端钩子 | Phase 0-2 + Phase 3，检查 evidence_hashes、重算 SHA256、realpath 检查 |
| [test_phase3_attacks.py](tools/ci/test_phase3_attacks.py) | Phase 3 攻击测试脚本 | 逻辑验证脚本，测试内容修改、symlink、路径穿越等攻击 |

**Phase 4: 全系统 Checks 集成**

| Path | What | Notes/Owner |
|------|------|-------------|
| [Phase 4 Checks 集成报告](docs/REPORT/control_plane/REPORT__PHASE4_CHECKS_INTEGRATION__20260120__20260120.md) | Phase 4 完成报告 | Phase 4 全系统 checks 接入实施完成，包含所有必需 checks 和 server-side 强制校验 |
| [pre-receive-phase4.sh](tools/ci/pre-receive-phase4.sh) | Phase 4 服务器端钩子 | Phase 0-3 + Phase 4，检查所有 checks 为 PASS、artifacts_path 存在性 |
| [run_phase4_checks.py](tools/ci/run_phase4_checks.py) | Phase 4 Checks 运行器 | 运行所有必需的 checks（import-scan、manifest、docs-governance、unit-tests、ata、policy） |
| [test_phase4_attacks.py](tools/ci/test_phase4_attacks.py) | Phase 4 攻击测试脚本 | 逻辑验证脚本，测试 checks 状态伪造、缺失 checks 等攻击 |

**Phase 5: 运行时门禁**

| Path | What | Notes/Owner |
|------|------|-------------|
| [Phase 5 运行时门禁报告](docs/REPORT/control_plane/REPORT__PHASE5_RUNTIME_GATE__20260120__20260120.md) | Phase 5 完成报告 | Phase 5 运行时门禁闭环实施完成，包含运行时校验和产物追溯机制 |
| [runtime_gate.py](tools/ci/runtime_gate.py) | 运行时门禁脚本 | 运行时验证 commit 是否已放行，检查 mvm/pass/* tag、签名、verdict.json |
| [test_phase5_attacks.py](tools/ci/test_phase5_attacks.py) | Phase 5 攻击测试脚本 | 逻辑验证脚本，测试未放行 commit 运行、已放行 commit 追溯等场景 |

#### 4.3.5 CI 约束与强制集成

| Path | What | Notes/Owner |
|------|------|-------------|
| [沙盒 CI 约束强制集成报告](docs/REPORT/control_plane/REPORT__SANDBOX_CI_ENFORCEMENT__20260120__20260120.md) | 沙盒 CI 强制集成 | 在沙盒环境中模拟强制集成 CI 约束，所有测试通过，准备推广到实际环境 |
| [CI 约束强制集成报告](docs/REPORT/control_plane/REPORT__CI_ENFORCEMENT_INTEGRATION__20260120__20260120.md) | CI 强制集成完成 | 将沙盒中验证的 CI 约束强制集成机制推广到实际工作流（a2a_worker、ai_collaboration_manager） |
| [CI 约束测试报告](docs/REPORT/control_plane/REPORT__CI_ENFORCEMENT_TEST__20260120__20260120.md) | CI 约束测试 | CI 约束强制集成机制测试报告，所有测试通过（集成验证5/5，沙盒测试3/3） |
| [证据证明报告](docs/REPORT/control_plane/REPORT__EVIDENCE_PROOF__20260120__20260120.md) | 证据证明 | 证明系统会提供证据，并提供"提供了证据"这个事实本身的证据 |
| [沙盒 AI 任务包装器](tools/ci/sandbox_ai_task_wrapper.py) | 沙盒包装器 | 所有 AI 任务必须通过此包装器执行，强制调用 Guard 和 Verdict |
| [沙盒测试脚本](tools/ci/sandbox_test_ci_enforcement.py) | 沙盒测试 | 沙盒 CI 约束强制集成测试脚本，包含3个测试用例 |
| [集成测试脚本](tools/ci/test_integration.py) | 集成测试 | CI 约束强制集成验证测试脚本，验证所有集成点 |
| [沙盒集成计划](tools/ci/sandbox_integration_plan.md) | 沙盒集成计划 | 沙盒 CI 约束强制集成计划，包含实施步骤、使用示例、验证清单 |

#### 4.3.6 状态机与守卫系统

| Path | What | Notes/Owner |
|------|------|-------------|
| [技能调用状态机规范](docs/arch/prompt_blocks/SKILL_CALL_STATE_MACHINE.md) | 状态机规范 | 状态机定义、门禁规则、失败码规范、禁止回退规则 |
| [技能调用状态机守卫](tools/ci/skill_call_guard.py) | 状态机守卫脚本 | 在 SUBMIT 前自动拦截不合规归档与证据路径，确保 fail-closed 放行 |
| [技能调用状态机管理器](tools/ci/skill_call_state_machine.py) | 状态机管理器脚本 | 管理任务状态流转（PLAN → EDIT → SELFTEST → REPORT → SUBMIT → DONE），执行状态转换规则 |
| [技能调用状态机守卫任务总结](docs/REPORT/control_plane/artifacts/SKILL_CALL_SM_GUARD__20260120/TASK_SUMMARY.md) | 任务总结文档 | SKILL_CALL_SM_GUARD__20260120 任务完成总结，包含实现内容、测试验证、使用说明等 |
| [技能调用状态机守卫报告](docs/REPORT/control_plane/REPORT__SKILL_CALL_SM_GUARD__20260120__20260120.md) | 状态机守卫实施报告 | 技能调用状态机守卫机制实施完成报告 |

#### 4.3.7 核心工具与脚本

| Path | What | Notes/Owner |
|------|------|-------------|
| [MVM Verdict 脚本](tools/ci/mvm-verdict.py) | MVM 验证裁决脚本 | 机器验证模块，在签 mvm/pass/* tag 前必须通过 guard 校验，生成 verdict.json |
| [每日本地 CI 工作流](docs/arch/ops/daily_local_ci_workflow__v0.1.0.md) | 每日本地 CI 工作流 | 本地开发 + 本地 bare repo 门禁模式下的每日标准作业流程 |
| [导航文档更新报告](docs/REPORT/control_plane/REPORT__NAVIGATION_UPDATE__20260120__20260120.md) | 导航更新 | 本次对话生成的所有文档已记入导航，包含 Phase 4-5、CI 约束强制集成、测试报告等 |

#### 4.3.8 防守方专用文档

| Path | What | Notes/Owner |
|------|------|-------------|
| [防守端写权限与部署指南](docs/arch/control_plane/MVM_DEFENDER_WRITE_ACCESS__v0.1.0.md) | 防守端写权限与部署指南 | 防守端如何修改/部署防守端文件（hooks/pre-receive 与公钥验签 keyring） ⚠️ **防守方专用** |
| [CI远程系统访问文档（防守方专用）](docs/arch/control_plane/CI_REMOTE_SYSTEM_ACCESS__DEFENDER_ONLY__v0.1.0.md) | CI远程系统访问 | 如何访问和修改GitHub Actions CI系统，登录方式，权限控制（仅防守方可访问） ⚠️ **防守方专用** ⚠️ **访问前必须记录访问日志** |
| [防守方授权列表](docs/arch/control_plane/DEFENDER_AUTHORIZATION_LIST.md) | 防守方授权 | 防守方授权记录，授权流程，权限撤销 ⚠️ **防守方专用** |
| [CI远程系统访问日志](docs/arch/control_plane/CI_REMOTE_ACCESS_LOG.jsonl) | 访问日志 | CI远程系统访问日志（JSONL格式），记录所有访问者的ATA代码和信息 ⚠️ **防守方专用** |
| [访问日志工具](tools/ci/log_ci_remote_access.py) | 访问日志工具 | 记录CI远程系统访问日志的工具，要求访问者提供ATA代码和信息 ⚠️ **防守方专用** |

#### 4.3.9 Prompt Blocks 索引

| Path | What | Notes/Owner |
|------|------|-------------|
| docs/arch/prompt_blocks/INVARIANTS.md | 不变量常量块 | 系统核心不变量定义 |
| docs/arch/prompt_blocks/FORBIDDEN.md | 禁止项常量块 | 直接失败项定义 |
| docs/arch/prompt_blocks/REPORT_SCHEMA.md | 报告 schema 常量块 | 报告必填字段定义 |
| docs/arch/prompt_blocks/SUBMIT_TEMPLATE.md | SUBMIT 模板常量块 | SUBMIT 格式强制约束 |
| docs/arch/prompt_blocks/SKILL_CALL_RULES.md | SKILL 调用规则 | 技能调用的标准规范 |
| docs/arch/prompt_blocks/SKILL_CALL_STATE_MACHINE.md | 技能调用状态机规范 | 状态机定义、门禁规则、失败码规范、禁止回退规则 |
| docs/arch/prompt_blocks/CAPSULE__MCP_CONN_DIAG.md | MCP 连接诊断胶囊 | MCP 连接诊断的标准提示词模板 |
| docs/arch/prompt_blocks/QUANT_THRESHOLDS.md | 定量阈值常量块 | 系统各领域定量阈值标准 |
| docs/arch/prompt_blocks/CAPSULE__SUBMIT_VALIDATOR.md | SUBMIT 验证器常量块 | SUBMIT 非空校验与格式验证 |
| docs/arch/prompt_blocks/CAPSULE__EVIDENCE_VALIDATOR.md | 证据验证器常量块 | 证据路径存在性与目录合规校验 |
| docs/arch/prompt_blocks/CAPSULE__CHAIN_VALIDATOR.md | 技能链验证器常量块 | 技能调用顺序与合规性验证 |
| docs/arch/prompt_blocks/CAPSULE__ATA_COMM_TEMPLATES.md | ATA 通信模板胶囊 | 握手/发任务/回任务统一模板，回应强制包含三件套审计信息 ⭐ |
| docs/arch/prompt_blocks/CODE_IMPLEMENTATION_PRINCIPLES.md | 代码实现原则常量块 | 所有代码实现必须遵循成熟方案，不以最简单方式实现需求。包含必须遵循和禁止事项、实现示例、参考标准 ⭐ **强制原则** |

### 4.4 文档管理系统

| Path | What | Notes/Owner |
|------|------|-------------|
| [文档管理系统文档](docs/arch/DOCUMENTATION_MANAGEMENT__v0.1.0.md) | 文档管理系统完整文档 | 说明文档分类体系、命名规范、版本管理、状态管理、组织结构、查找使用指南和维护规范 ⭐ **文档管理元文档** |
| [文档双管理系统](docs/arch/DOCUMENTATION_DUAL_MANAGEMENT__v0.1.0.md) | 文档双管理系统 | 结合总导航文档和PostgreSQL的文档管理系统，实现文档索引管理、内容存储、版本控制、状态管理和快速查找。包含PostgreSQL表结构、同步脚本、一致性检查脚本和文档管理工具 ⭐ **文档管理核心** ⭐ **必读** |
| [文档双管理系统快速使用指南](docs/arch/DOCUMENTATION_DUAL_MANAGEMENT_QUICK_START__v0.1.0.md) | 快速使用指南 | 文档双管理系统的快速使用指南，包含初始化、同步、查询、维护等常用操作 ⭐ **使用指南** ⭐ **必读** |
| [近期文档生成总结](docs/arch/RECENT_DOCUMENTS_SUMMARY__v0.1.0.md) | 近期文档总结 | 总结自2026-01-20以来新生成的所有文档，按主题分类整理，说明文档的组织结构和查找方法 ⭐ **文档整理** |
| [未编写文档模块清单](docs/arch/UNDOCUMENTED_MODULES_LIST__v0.1.0.md) | 未编写文档模块清单 | 列出系统中尚未编写文档的重要模块和组件，按优先级分类，供决定是否编写文档时参考 ⭐ **文档规划** |
| [AI自检查系统业界对比](docs/arch/ops/AI_SELF_CHECKING_INDUSTRY_COMPARISON.md) | AI自检查对比分析 | 对比业界通行做法（LangChain/LangSmith、AutoGPT、EviBound等）与项目实现的差异，分析优势劣势，提出改进建议 ⭐ **技术对比** ⭐ **最佳实践** |
| [LangSmith集成指南](docs/arch/ops/LANGSMITH_INTEGRATION_GUIDE.md) | LangSmith集成指南 | LangSmith评估和场景测试集成完整指南，包含所需资源、基础设施、代码实现、成本控制和实施步骤 ⭐ **集成指南** ⭐ **实施计划** |
| [GitHub AI自驱动模式汇总](docs/arch/ops/GITHUB_AI_SELF_DRIVING_PATTERNS.md) | GitHub AI自驱动模式 | GitHub上AI自驱动实现模式汇总，包括Scheduler-Agent-Supervisor、轮询循环、Watchdog、自验证循环等，对比项目实现并提出改进建议 ⭐ **模式参考** ⭐ **最佳实践** |
| [ATA系统升级计划](docs/arch/ops/ATA_SYSTEM_UPGRADE_PLAN.md) | ATA系统升级计划 | ATA系统升级为Scheduler-Agent-Supervisor三层架构的完整计划，包含当前问题、目标架构、实施阶段、详细设计、代码实现 ⭐ **升级计划** ⭐ **实施指南** |
| [ATA升级与Agent集成总结](docs/arch/ops/ATA_UPGRADE_AND_AGENTS_SUMMARY.md) | ATA升级总结 | ATA系统升级与AI Agent集成总结文档，包含下载的Agent项目、升级计划、参考模式、实施优先级、成功标准 ⭐ **总结文档** ⭐ **执行摘要** |
| [Sleepless和Recursive下载指南](tools/ai-agents/DOWNLOAD_SLEEPLESS_RECURSIVE.md) | Agent下载指南 | Sleepless Agent和Recursive Agents的下载、安装、配置指南，包含GitHub地址、安装要求、配置步骤 ⭐ **下载指南** |
| [代码清理工具指南](docs/arch/ops/CODE_CLEANUP_TOOLS_GUIDE.md) | 代码清理工具 | 2025年最新开源免费代码清理工具指南，特别关注AI生成代码清理，包含Ruff、Autoflake、Vulture、Knip等工具 ⭐ **代码质量** ⭐ **AI代码清理** |
| [定期清理系统指南](docs/arch/ops/PERIODIC_CLEANUP_GUIDE.md) | 定期清理系统 | 定期清理长期未使用文件的自动化系统，支持每3天运行一次持续30天，智能识别临时文件、缓存、日志、产物、备份 ⭐ **文件清理** ⭐ **自动化维护** |
| [开源Agent通信系统指南](docs/arch/ops/OPEN_SOURCE_AGENT_COMMUNICATION_SYSTEMS.md) | Agent通信系统 | 2025年主要开源Agent通信系统和框架汇总，包含MCP、A2A、LangGraph、LangChain、CrewAI等协议和框架对比、集成方案 ⭐ **Agent通信** ⭐ **多Agent系统** |
| [LangGraph和LangChain集成指南](docs/arch/ops/LANGGRAPH_LANGCHAIN_INTEGRATION.md) | LangGraph集成 | LangGraph和LangChain与现有MCP系统的集成方案，包含适配分析、互补点、实施步骤、代码示例和迁移策略 ⭐ **系统集成** ⭐ **工作流编排** |
| [LangGraph和LangChain安装完成报告](docs/arch/ops/LANGGRAPH_LANGCHAIN_INSTALLATION_COMPLETE.md) | LangGraph安装报告 | LangGraph和LangChain安装完成报告，包含安装结果、适配结论、实施步骤和下一步操作 ⭐ **安装报告** |
| [LangGraph可视化界面指南](docs/arch/ops/LANGGRAPH_VISUAL_INTERFACES.md) | LangGraph可视化 | LangGraph Studio和LangSmith Dashboard可视化界面使用指南，包含安装、配置、功能特性和使用场景 ⭐ **可视化界面** ⭐ **调试工具** |

**工程导航与索引**
| Path | What | Notes/Owner |
|------|------|-------------|
| [本导航文档](docs/ARCH/project_navigation__v0.1.0__ACTIVE__20260115.md) | 项目导航唯一入口 | 后续提示词统一引用 |
| [架构审计索引](docs/arch/quantsys_arch_audit_index__v1.0.0__ACTIVE__20260114.md) | 架构审计索引 | 系统架构审计文档汇总 |
| [架构文档索引](docs/arch/00_index.md) | 架构文档索引 | 架构文档导航入口 |
| [规格文档索引](docs/SPEC/00_index.md) | 规格文档索引 | 规格文档导航入口 |
| [报告文档索引](docs/REPORT/00_index.md) | 报告文档索引 | 报告文档导航入口 |
| [日志文档索引](docs/LOG/00_index.md) | 日志文档索引 | 日志文档导航入口 |
| [文档模板目录](docs/templates/) | 文档模板 | 各类文档模板 |
| [变更日志目录](docs/LOG/change_log/) | 变更日志 | 系统变更历史 |
| [任务报告目录](docs/REPORT/tasks/) | 任务报告 | 各类任务报告 |
| [迁移日志](docs/migrations/MIGRATION_LOG.md) | 迁移日志 | 系统迁移历史 |
| [迁移登记总览](docs/LOG/migrations/MIGRATION_LEDGER.md) | 迁移登记总览 | 文件迁至 legacy/experiments/ 等操作记录 |
| [文档目录说明](docs/README.md) | 文档目录说明 | 文档目录总说明 |
| [系统概览](docs/SYSTEM_OVERVIEW.md) | 系统概览 | 系统整体架构与功能介绍 |
| [文档治理概览](docs/DOC_GOVERNANCE_OVERVIEW.md) | 文档治理概览 | 文档治理体系介绍 |
| [仓库考古报告](docs/quantsys_repo_archaeology_report.md) | 仓库考古报告 | 仓库历史与结构分析 |

### 4.5 数据库系统

**核心文档（概览、架构、覆盖、统计）**：
| Path | What | Notes/Owner |
|------|------|-------------|
| [数据库概览文档](docs/DATABASE/database_overview.md) | 数据库概览 | 数据库唯一性确认、文件清单、表结构、维护指南 ⭐ **数据库统一文档** |
| [PostgreSQL数据库完整文档](docs/DATABASE/postgresql_database_documentation.md) | PostgreSQL完整文档 | 完整架构、表结构、数据迁移方案、数据指针系统 ⭐ **核心数据库文档** |
| [数据覆盖情况总结](docs/DATABASE/data_coverage_summary.md) | 数据覆盖总结 | 对所有数据的覆盖情况，确认100%支持所列数据 ⭐ **数据覆盖确认** |
| [数据库数据报告](docs/DATABASE/database_data_report.md) | 数据库数据报告 | 所有表的结构、行数和样本数据 ⭐ **数据统计** |

**数据清单与下载（清单、脚本、配置）**：
| Path | What | Notes/Owner |
|------|------|-------------|
| [数据下载脚本概览](docs/DATABASE/data_download_scripts_overview.md) | 下载脚本概览 | 脚本唯一性确认、文件清单、使用建议 ⭐ **下载脚本统一文档** |
| [已有数据清单](docs/DATABASE/existing_data_inventory.md) | 数据清单 | PostgreSQL数据表、本地文件、数据目录结构 ⭐ **数据清单文档** |
| [数据迁移脚本](scripts/migrate_data_to_postgresql.py) | 数据迁移工具 | 文件系统→PostgreSQL，支持Feather/CSV/Parquet/JSON，自动注册文件指针 ⭐ **数据迁移工具** |
| [下载器配置示例](configs/market_data_downloader_config_example.json) | 下载器配置示例 | 代理与私有API配置示例 |
| [市场数据下载器测试脚本](scripts/test_unified_downloader.py) | 下载器测试 | 统一市场数据下载器快速测试 |

**契约与规则**：
| Path | What | Notes/Owner |
|------|------|-------------|
| [数据接口契约](docs/contracts/data_contract.md) | 数据契约 | 数据类型、存储位置、字段schema、时间戳标准 ⭐ |
| [数据源文档](docs/data_source_of_truth.md) | 数据源规则 | 数据来源优先级、禁止混读规则、迁移策略 ⭐ |

**核心代码与运维工具**：
| Path | What | Notes/Owner |
|------|------|-------------|
| [数据库管理器](src/quantsys/data/database_manager.py) | 数据库核心代码 | PostgreSQL连接与操作管理器 ⭐ **核心代码** |
| [数据库检查脚本](corefiles/check_database.py) | 检查工具 | 检查数据库中的交易数据 |
| [数据库验证脚本](corefiles/verify_db_data.py) | 验证工具 | 验证数据库数据完整性 |
| [数据库修复脚本](corefiles/fix_database.py) | 修复工具 | 修复数据库问题 |
| [数据库字段修复脚本](corefiles/fix_database_field_length.py) | 字段修复工具 | 修复数据库字段长度 |

**数据存储**：
| Path | What | Notes/Owner |
|------|------|-------------|
| [本地数据目录](data/local/) | 本地数据存储 | raw、processed、cache、exports 等子目录 ⭐ |
| [本地数据目录说明](data/local/README.md) | 目录说明 | 结构、命名规范、数据管理规则 ⭐ |

## 5. 使用约定

1. 任何提示词仅引用本导航文档 + law/QCC-README.md
2. 新增目录结构需先更新本导航文档
3. 导航文档更新后，再同步更新对应目录的 00_index.md
4. 所有工程入口类文档必须在此导航中注册
5. 避免在仓库根目录存放导航类文档
6. 历史文档需明确标注状态和使用限制
7. 定期清理过期或重复的导航文档
8. 导航文档版本变更需同步更新所有引用
# NOTE (SSOT migration):
# - This document is preserved here as legacy reference.
# - It MUST NOT be treated as an entrypoint/navigation root.
# - Authoritative navigation is `docs/START_HERE.md` -> `docs/ssot/` indices.
---
oid: <MINT_WITH_SCC_OID_GENERATOR>
layer: ARCH
primary_unit: A.PLANNER
tags: [S.NAV_UPDATE, V.GUARD]
status: active
---
