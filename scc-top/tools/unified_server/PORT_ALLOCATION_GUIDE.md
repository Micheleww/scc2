# 端口分配系统使用指南

## 概述

统一服务器内置了智能端口分配系统，自动为新服务分配不常用的端口（18000-19999范围），避免与业界常用端口冲突。

## 特性

- ✅ **自动分配**：新服务注册时自动分配端口
- ✅ **避免冲突**：自动排除常用端口（80, 443, 8080, 3000等）
- ✅ **持久化**：端口分配保存到 `.allocated_ports.json`
- ✅ **端口检查**：自动检查端口是否被占用
- ✅ **灵活配置**：支持首选端口、端口保留等功能

## 端口范围

- **分配范围**：18000 - 19999
- **排除端口**：业界常用端口（80, 443, 8080, 3000, 5000等）
- **统一服务器主端口**：18788（固定，不参与自动分配）

## 使用方法

### 1. 在服务中使用自动端口分配

在创建服务时，启用自动端口分配：

```python
from core.service_registry import Service

class MyService(Service):
    def __init__(self, name: str, enabled: bool = True):
        # 启用自动端口分配
        super().__init__(
            name=name,
            enabled=enabled,
            auto_allocate_port=True,  # 启用自动分配
            preferred_port=18123  # 可选：指定首选端口
        )
        # 分配的端口可通过 self.allocated_port 访问
```

### 2. 使用管理工具

#### 查看端口分配

```bash
python manage_ports.py list
```

输出示例：
```
=== 端口分配列表 ===

已分配端口 (3 个):
  clawdbot                    -> 19001
  new_service                 -> 18123
  another_service             -> 18234

=== 统计信息 ===
端口范围: 18000-19999
总端口数: 2000
已分配: 3
已保留: 0
可用: 1997
利用率: 0.15%
```

#### 为服务分配端口

```bash
# 自动分配
python manage_ports.py allocate my_service

# 指定首选端口
python manage_ports.py allocate my_service --port 18123
```

#### 释放端口

```bash
python manage_ports.py release my_service
```

#### 保留端口（防止被自动分配）

```bash
python manage_ports.py reserve 18500 --reason "预留给特殊服务"
```

#### 检查端口是否可用

```bash
python manage_ports.py check 18123
```

#### 导出端口分配

```bash
python manage_ports.py export ports.json
```

### 3. 通过API查看端口分配

```bash
# 获取端口分配信息
curl http://localhost:18788/health/ports
```

响应示例：
```json
{
  "allocated_ports": {
    "clawdbot": 19001,
    "new_service": 18123
  },
  "statistics": {
    "port_range": "18000-19999",
    "total_ports": 2000,
    "allocated": 2,
    "reserved": 0,
    "available": 1998,
    "utilization": "0.10%"
  },
  "all_allocations": {
    "clawdbot": 19001,
    "new_service": 18123
  }
}
```

## 配置

### 环境变量

可以通过环境变量配置端口分配范围：

```bash
# 设置端口范围起始（默认18000）
export PORT_ALLOCATOR_START=18000

# 设置端口范围结束（默认19999）
export PORT_ALLOCATOR_END=19999
```

### 配置文件

端口分配保存在 `tools/unified_server/.allocated_ports.json`：

```json
{
  "allocated": {
    "clawdbot": 19001,
    "new_service": 18123
  },
  "reserved": [18500]
}
```

## 最佳实践

1. **使用自动分配**：新服务启用 `auto_allocate_port=True`，让系统自动分配端口

2. **避免硬编码端口**：不要在新服务中硬编码端口号，使用自动分配

3. **保留特殊端口**：如果某个端口需要保留给特定用途，使用 `reserve` 命令

4. **定期检查**：使用 `list` 命令定期查看端口使用情况

5. **导出备份**：定期导出端口分配，作为备份

## 常见问题

### Q: 端口分配失败怎么办？

A: 检查：
1. 端口范围是否足够（默认2000个端口）
2. 是否有太多端口被保留
3. 端口是否被其他进程占用

### Q: 如何手动指定端口？

A: 使用 `preferred_port` 参数，如果该端口可用，系统会使用它。

### Q: 端口分配会持久化吗？

A: 是的，端口分配保存在 `.allocated_ports.json` 文件中，服务器重启后仍然有效。

### Q: 如何重置所有端口分配？

A: 删除 `.allocated_ports.json` 文件，然后重新启动服务器。

## 技术细节

### 端口分配算法

1. 检查服务是否已有分配的端口（从持久化文件加载）
2. 如果指定了首选端口，先尝试使用
3. 使用质数步进策略（步进7）在端口范围内查找可用端口
4. 如果步进策略失败，使用顺序查找
5. 检查端口是否：
   - 在范围内
   - 不是常用端口
   - 未被分配
   - 未被保留
   - 未被占用

### 端口检查

系统会检查：
- 端口是否在分配范围内
- 是否为业界常用端口
- 是否已被分配
- 是否被保留
- 是否被其他进程占用（通过socket连接测试）

## 相关文件

- `core/port_allocator.py` - 端口分配器实现
- `core/service_registry.py` - 服务注册表（集成端口分配）
- `manage_ports.py` - 端口管理工具
- `.allocated_ports.json` - 端口分配持久化文件
