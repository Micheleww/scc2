---
oid: 01KGEJFSGMH8GB147AC809CNDZ
layer: DOCOPS
primary_unit: V.GUARD
tags: [S.NAV_UPDATE]
status: active
---

# Clawdbot / Lobster 端口与 TimQuant 错开说明

## 端口分配

| 用途 | 端口 | 说明 |
|------|------|------|
| **TimQuant** 反向代理 / MCP_BUS | 8000 | 统一入口 |
| **TimQuant** ATA / FREQTRADE | 8080 | API |
| **TimQuant** MCP 总线 | 8001 | MCP |
| **TimQuant** 主应用 | 8002 | 主应用 |
| **TimQuant** Frequi | 8040 | 交易界面 |
| **ui-tars** Electron 渲染进程 dev | 8041 | `tools/ui-tars-desktop` |
| **ui-tars** A2A_HUB | 5001 | A2A |
| **ui-tars** Dashboard | 8051 | Dashboard |
| **ui-tars** LangGraph | 2024 | LangGraph |
| **Clawdbot Gateway** | 18789 | WS+HTTP，默认 |
| **Clawdbot Bridge** | 18790 | 衍生 |
| **Clawdbot UI (dev)** | 5173 | Vite 开发 |

Clawdbot（含 Lobster 插件）与 TimQuant / ui-tars **端口无冲突**，可同机运行。

## 运行 Clawdbot + Lobster

1. 进入 `clawdbot` 目录，安装依赖并构建：
   ```bash
   cd clawdbot && pnpm install && pnpm build
   ```
2. 可选：显式指定 Gateway 端口（默认 18789）：
   ```bash
   set CLAWDBOT_GATEWAY_PORT=18789
   pnpm run gateway:dev
   ```
3. 在 agent 配置中启用 Lobster 插件（`tools.allow` 包含 `"lobster"`）。  
   详见 `clawdbot/extensions/lobster/README.md` 与 `clawdbot/docs/tools/lobster.md`。

## 仅停止 TimQuant

不杀 Cursor 等其它应用，只释放 TimQuant 占用端口：

```bash
python stop_all_services.py --timquant-only
```

详见 `PORT_CONFIG_README.md`。

## 测试 Lobster 是否上线应用内

```bash
node tools/test_lobster_plugin_online.mjs           # 静态 + 运行时检查
node tools/test_lobster_plugin_online.mjs --static-only  # 仅静态检查（无需 install/build）
```

- **静态检查**：插件目录、`clawdbot.plugin.json`、`lobster-tool` 中 `name: 'lobster'` 等。
- **运行时检查**：`clawdbot plugins list --json`，要求 lobster 已发现、已加载、已暴露 `lobster` 工具。  
  需在 `clawdbot` 下完成 `pnpm install` 与 `pnpm build`；若缺失依赖或构建失败，会跳过运行时并退出码 2。
- **退出码**：0 已上线；1 未上线或静态失败；2 静态通过、运行时跳过。

## Lobster 插件调试

- **代码**：`clawdbot/extensions/lobster/`。插件通过子进程调用 `lobster` CLI，无独立端口。
- **Windows**：已在 `lobster-tool` 中处理 `spawn` 的 `EINVAL`，失败时回退到 `shell: true`。
- **单元测试**：`pnpm run test` 会跑 `extensions/**/*.test.ts`（含 Lobster）。需在 `clawdbot` 下先完成 `pnpm install`；若出现 `@matrix-org/matrix-sdk-crypto-nodejs` 权限错误，可尝试以管理员运行或 `pnpm install --no-optional` 后重试。
- **Lobster CLI**：使用 `lobster` 工具前需在本机安装 [Lobster CLI](https://github.com/clawdbot/lobster)，并保证 `lobster` 在 `PATH` 中。
