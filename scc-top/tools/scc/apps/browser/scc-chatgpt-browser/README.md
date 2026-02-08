# SCC ChatGPT Browser (internal)

一个 SCC 内部的最小“内置浏览器”应用（Electron）。用于：

1. 打开 `https://chatgpt.com/`（你手动登录）
2. 在同一会话中用 DOM 注入抓取最新 assistant 消息里的 `SCC_*_JSON:` 指令块（非视觉识别）
3. 将解析后的 payload POST 到本机 SCC Intake（默认 `http://127.0.0.1:18788/intake/directive`）

## 运行

在此目录执行：

```bash
npm install
npm start
```

首次启动会打开 `https://chatgpt.com/`。请在窗口内手动登录（必要时完成验证码/2FA）。登录态会保留在本机 profile（`persist:scc-chatgpt`），后续启动通常无需重复登录。

如果你运行时遇到 `ipcMain` 相关报错，请检查环境变量 `ELECTRON_RUN_AS_NODE` 是否被设置为 `1`；该变量会让 Electron 以 Node 模式运行，导致 Electron API 不可用。本项目在 Unified Server 拉起时会自动清除此变量。

## DEV 桌面快捷方式（无脚本框/无控制台）

1. 先在本目录完成依赖安装：`npm install`
2. 生成桌面快捷方式：
   - `powershell -ExecutionPolicy Bypass -File .\\create_desktop_shortcut.ps1`
3. 双击桌面 `SCC ChatGPT Browser (DEV)` 即可启动（通过 `dev_launch.vbs` 隐藏控制台窗口）

## 配置

应用内可设置：

- `Endpoint`（默认）：`http://127.0.0.1:18788/intake/directive`（Unified Server）
- `WebGPT Intake`（默认）：`http://127.0.0.1:18788/scc/webgpt/intake`
- `WebGPT Export`（默认）：`http://127.0.0.1:18788/scc/webgpt/export`
- `Auth token`（可空）：设置后以 `Authorization: Bearer <token>` 发送
- `Auto-send`：新 assistant 消息出现且检测到指令时自动投递（失败最多重试 2 次）

配置会保存在系统 `userData` 目录（不写入仓库）。

## WebGPT（对话落盘）

工具栏提供：

- `Sync`：抓取当前会话可见消息 → POST `/scc/webgpt/intake`
- `Export`：导出当前会话到 `docs/INPUTS/WEBGPT/`
- `Backfill`：尽力从侧边栏枚举会话并批量抓取+入库+导出（可设 limit/scroll）

默认行为：

- 当你打开 `https://chatgpt.com/c/<id>` 会自动触发一次 `Sync`（以及成功后 `Export`）
- 如通过 Unified Server 启动时传入 `webgpt_backfill_autostart=true`，Backfill 会在你登录后自动启动（不会在 `/auth/*` 页面误触发）

## 支持的前缀

- `SCC_DIRECTIVE_JSON:`
- `SCC_APPROVAL_JSON:`
- `SCC_STATUS_REQUEST_JSON:`

## 输出 payload

```json
{
  "source": "chatgpt_embedded_browser",
  "page_url": "https://chatgpt.com/...",
  "captured_at": "2026-01-29T00:00:00.000Z",
  "directives": [{}, {}]
}
```

## 已知限制

- ChatGPT DOM 可能变化；提取逻辑做了 selector 回退，但仍可能需要调整 `preload_chatgpt.js`
- 登录过程完全由你手动完成（可能存在验证码/2FA/风控），本应用不尝试自动绕过

## 和 Chrome 扩展的关系

仓库里仍保留 Chrome 扩展版本（`tools/scc/apps/browser-extension/scc-directive-forwarder/`）。本应用适用于你希望“在 SCC 内部提供一个可登录/可抓取 DOM 的浏览器窗口”的场景。
