# 单实例检查实现说明

## 实现方法

本实现使用了**Windows命名互斥体（Named Mutex）**，这是Windows平台最成熟和通用的单实例检查方法。

## 为什么选择命名互斥体？

### 1. **行业标准**
- Windows API的标准方法
- 被大多数Windows应用程序使用（如Visual Studio、Chrome等）
- 内核级对象，系统保证唯一性

### 2. **可靠性高**
- **端口检查**：可能被其他程序占用，误判
- **进程检查**：进程名可能相同，命令行解析可能失败
- **互斥体**：系统级对象，100%可靠

### 3. **性能优秀**
- 内核级检查，速度极快（微秒级）
- 不依赖网络请求或进程枚举
- 系统自动管理，无需手动清理

### 4. **自动清理**
- 进程退出时，系统自动释放互斥体
- 即使程序崩溃，系统也会清理
- 无需担心资源泄漏

## 实现原理

```python
# 1. 创建命名互斥体
mutex = win32event.CreateMutex(None, True, "Global\\MCP_Bus_Server_Tray_Instance")

# 2. 检查错误码
if GetLastError() == ERROR_ALREADY_EXISTS:
    # 互斥体已存在 = 另一个实例正在运行
    exit()
else:
    # 成功创建 = 我们是第一个实例
    continue
```

## 技术细节

### 命名空间
- **`Global\\`**：跨用户会话，整个系统只有一个实例
- **`Local\\`** 或无前缀：仅当前用户会话，不同用户可以同时运行

### 错误处理
- 如果互斥体创建失败（权限不足等），自动降级到备用方法：
  1. 端口检查
  2. 进程检查（如果psutil可用）

### 资源管理
- 使用上下文管理器（`with`语句）确保自动清理
- 程序退出时自动释放互斥体

## 依赖要求

### 必需
- Python 3.x
- Windows操作系统

### 可选（推荐）
- `pywin32`：用于Windows API访问
  ```bash
  pip install pywin32
  ```

### 备用依赖
- `psutil`：如果互斥体不可用，用于进程检查
  ```bash
  pip install psutil
  ```

## 与其他方法对比

| 方法 | 可靠性 | 性能 | 复杂度 | 推荐度 |
|------|--------|------|--------|--------|
| **命名互斥体** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ✅ **推荐** |
| 端口检查 | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⚠️ 备用 |
| 进程检查 | ⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⚠️ 备用 |
| 文件锁 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ✅ 跨平台 |

## 参考资源

- [Windows Mutex Objects (Microsoft Docs)](https://learn.microsoft.com/en-us/windows/win32/sync/using-mutex-objects)
- [PyWin32 Documentation](https://timgolden.me.uk/pywin32-docs/win32event.html)
- [Single Instance Best Practices](https://www.coretechnologies.com/blog/alwaysup/python-script-single-instance/)

## 代码位置

- 实现文件：`server_tray_enhanced.py`
- 类名：`SingleInstance`
- 互斥体名称：`Global\\MCP_Bus_Server_Tray_Instance`

## 使用示例

```python
# 在main()函数中
instance_mutex = SingleInstance()
if instance_mutex.already_running:
    print("另一个实例正在运行")
    sys.exit(0)

# 程序退出时自动清理
# 使用上下文管理器或手动调用 release()
```

## 总结

本实现采用了**Windows平台最成熟和通用的单实例检查方法**，符合编程界的最佳实践，确保了：
- ✅ 高可靠性（内核级检查）
- ✅ 优秀性能（微秒级响应）
- ✅ 自动清理（系统管理）
- ✅ 向后兼容（备用方法）
