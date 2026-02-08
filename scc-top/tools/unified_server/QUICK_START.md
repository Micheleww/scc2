# 统一服务器快速开始

## 三步快速启动

### 1. 安装依赖

```bash
cd tools/unified_server
pip install -r requirements.txt
```

### 2. 启动服务器

```bash
python main.py
```

### 3. 测试服务器

```bash
# 简单测试
python test_unified_server.py

# 全面测试
python test_comprehensive.py
```

## 后台运行和开机自启动

### 后台运行

```powershell
.\run_as_background_service.ps1
```

### 开机自启动（推荐）

```powershell
# 以管理员身份运行
powershell -ExecutionPolicy Bypass -File create_startup_task.ps1
```

## 验证

访问以下地址验证服务器运行：

- http://localhost:18788/health
- http://localhost:18788/health/ready
- http://localhost:18788/health/live

## 更多信息

- [完整文档](README.md)
- [部署指南](DEPLOYMENT_GUIDE.md)
- [架构设计](ARCHITECTURE_DESIGN.md)
