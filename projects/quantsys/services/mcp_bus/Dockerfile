FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制requirements.txt并安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY server server/
COPY config config/
COPY docs docs/

# 创建logs目录
RUN mkdir -p logs

# 设置环境变量
ENV REPO_ROOT=/app
ENV MCP_BUS_HOST=0.0.0.0
ENV MCP_BUS_PORT=8000
ENV AUTH_MODE=none

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 运行应用
CMD python -m uvicorn server.main:app --host 0.0.0.0 --port 8000 --log-level info --workers 4
