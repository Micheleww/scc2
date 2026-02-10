# 端口冲突修复指南

## 问题
MCP服务器启动失败，错误：`WinError 10013` - 端口8000被占用

## 快速修复

### 方法1：使用修复脚本（推荐）
```powershell
cd d:\quantsys\tools\mcp_bus
.\fix_port_conflict.ps1
```

### 方法2：手动停止占用端口的进程

1. **查找占用端口的进程**
   ```powershell
   netstat -ano | findstr ":8000"
   ```
   找到 LISTENING 状态的行，记下最后一列的PID

2. **停止进程**
   ```powershell
   taskkill /F /PID <PID>
   ```
   例如：`taskkill /F /PID 1572`

3. **验证端口已释放**
   ```powershell
   netstat -ano | findstr ":8000"
   ```
   应该没有 LISTENING 状态的连接

4. **重新启动服务器**
   ```powershell
   .\start_mcp_server.ps1
   ```

## 预防措施

1. **优雅关闭服务器**
   - 使用 Ctrl+C 停止服务器
   - 不要直接关闭窗口

2. **启动前检查**
   - `start_mcp_server.ps1` 会自动检查端口
   - 如果端口被占用，会提示用户

3. **使用修复脚本**
   - 运行 `fix_port_conflict.ps1` 自动处理

## 常见问题

**Q: 为什么端口会被占用？**
A: 可能是之前启动的MCP服务器实例未正确关闭，或者有其他程序在使用8000端口。

**Q: 如何更改端口？**
A: 修改 `.env` 文件或启动脚本中的 `MCP_BUS_PORT` 环境变量。

**Q: 如何防止端口冲突？**
A: 使用进程锁文件或端口检查机制，确保只有一个实例运行。
