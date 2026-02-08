---
oid: 01KGDT0GZC9ETD0DWW2CVZE6J7
layer: DOCOPS
primary_unit: X.WORKSPACE_ADAPTER
tags: [S.NAV_UPDATE]
status: active
---

# Unified Server Restart (18788) — v0.1.0

## Purpose
Provide a single, reliable way to restart the SCC unified server on port `18788` (Windows-first).

## Normative rule
- Do **not** use `cmd /c start ...` for background launch; quoting/UNC edge cases may produce errors like “Windows 无法访问 \\\\\"\\\\\\\"”.
- Use the canonical restart script below.

## Canonical restart command
```powershell
python tools/unified_server/restart_unified_server.py --port 18788
```

## PowerShell (optional)
Some environments disable running `*.ps1` by default. If you must use PowerShell:
```powershell
powershell -ExecutionPolicy Bypass -File tools/unified_server/restart_unified_server.ps1 -Port 18788
```

## Health check
```powershell
Invoke-RestMethod http://127.0.0.1:18788/api/health
```

## Notes
- If port `18788` is already in use, the script will stop the listener PID and restart.
- Logs: `artifacts/unified_server_18788__<timestamp>.log`
- Latest log pointer: `artifacts/unified_server_18788__LATEST.logpath.txt`
- PID file: `artifacts/unified_server_18788.pid`

