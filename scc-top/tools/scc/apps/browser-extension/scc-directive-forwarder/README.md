# SCC Directive Forwarder (Chrome Extension, MV3)

Chrome 扩展（Manifest V3），运行于 `https://chatgpt.com/*`，从**最新一条 assistant 消息**中提取指令块（以固定前缀开头的 JSON），并 POST 到本机 SCC Intake API。

## 支持的前缀

- `SCC_DIRECTIVE_JSON:`
- `SCC_APPROVAL_JSON:`
- `SCC_STATUS_REQUEST_JSON:`

指令块格式示例（必须是严格 JSON；支持多行）：

```text
SCC_DIRECTIVE_JSON:
{
  "task_code": "SCC_EXT_CHROME_DIRECTIVE_FORWARDER_V0",
  "action": "selftest"
}
```

## 安装（Load unpacked）

1. 打开 `chrome://extensions`
2. 开启「开发者模式」
3. 点击「Load unpacked」
4. 选择目录：`tools/scc/apps/browser-extension/scc-directive-forwarder/`

## 配置（Options）

在扩展 Popup 点击 `Options`：

- `endpoint`（默认）：`http://localhost:8787/intake/directive`（也可使用 Unified Server：`http://127.0.0.1:18788/intake/directive`）
- `auth_token`（可空）：若设置，将以 `Authorization: Bearer <token>` 发送
- `autosend`（默认 false）：开启后，新 assistant 消息出现且检测到指令时自动投递（失败最多重试 2 次）

## 使用（Popup）

- **Detected N**：显示从最新 assistant 消息中检测到的指令数量（解析失败的会显示错误信息）
- **Send**：将检测到的指令批量投递到 SCC Intake
- **Copy**：复制投递 payload 到剪贴板
- **Auto-send**：开关自动投递

投递 payload 结构：

```json
{
  "source": "chatgpt_extension",
  "page_url": "https://chatgpt.com/...",
  "captured_at": "2026-01-29T00:00:00.000Z",
  "directives": [{}, {}]
}
```

## 提取策略（稳健性）

- 只处理最新一条 assistant 消息（优先使用 `data-message-author-role="assistant"`，否则回退到 `main article` 的最后一条）
- 通过 `MutationObserver` 监听对话更新
- 通过括号/方括号计数抓取紧随前缀之后的 JSON（忽略字符串内括号）
- `JSON.parse` 失败会提示，但不会中断其它块的解析/投递

## 自测（Mock SCC Intake）

1. 启动 mock intake server：
   - `node tools/scc/tools/mock/mock_intake_server.js`
2. 确认 Options 的 endpoint 为 `http://localhost:8787/intake/directive`
3. 打开一个 `https://chatgpt.com/` 对话，让 assistant 输出包含上述前缀的块
4. 打开扩展 Popup：
   - 显示 Detected N
   - 点击 Send 后，mock server stdout 应打印收到的 payload
   - 开启 Auto-send 后，新消息出现会自动投递（失败最多重试 2 次）

## 已知限制

- ChatGPT 页面 DOM 可能变化；虽然做了 selector 回退，但仍可能需要调整 `content_script.js`
- 出于权限最小化，扩展的 host 权限仅包含：
  - `https://chatgpt.com/*`
  - `http://localhost/*`、`http://127.0.0.1/*`
  如果你将 endpoint 指向其它域名，Chrome 可能阻止请求（需要在 `manifest.json` 扩展 host 权限）
