# Runbook（本地运行）

## 一键启动

```powershell
cd C:\scc\oc-scc-local
.\scripts\start-all.ps1
```

## 一键停止

```powershell
cd C:\scc\oc-scc-local
.\scripts\stop-all.ps1
```

## 冒烟检查

```powershell
cd C:\scc\oc-scc-local
npm run smoke
```

或直接访问：
- `http://127.0.0.1:18788/status`
- `http://127.0.0.1:18788/mcp/health`（SCC）
- `http://127.0.0.1:18788/opencode/global/health`（OpenCode）

## 常用排障

- 查看 18788/18789/18790 是否被占用：
  ```powershell
  Get-NetTCPConnection -LocalPort 18788,18789,18790 -State Listen | Select-Object LocalPort,OwningProcess
  ```
- 强制停止占用端口进程（示例：18788）：
  ```powershell
  Get-NetTCPConnection -LocalPort 18788 -State Listen | Select-Object -ExpandProperty OwningProcess -Unique |
    ForEach-Object { Stop-Process -Id $_ -Force }
  ```

