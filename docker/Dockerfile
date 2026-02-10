# SCC Backend Dockerfile - 唯一正式版本
# 17层分层架构 - 唯一真本
# 版本: 1.1.0 - 集成 opencode 和 codex CLI

# 使用 Microsoft Container Registry 镜像（国内可访问）
FROM mcr.microsoft.com/mirror/docker/library/node:18-alpine

# 安装必要依赖
RUN apk add --no-cache \
    python3 \
    py3-pip \
    curl \
    ca-certificates \
    git \
    bash \
    jq \
    libc6-compat

# 验证安装
RUN node --version && python3 --version

WORKDIR /app

# 环境变量配置
ENV NODE_ENV=production \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# 配置国内镜像源
ARG NPM_REGISTRY=https://registry.npmmirror.com
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

# ============================================
# 阶段 1: 安装 CLI 工具 (opencode & codex)
# ============================================

# 安装 codex CLI (OpenAI Codex)
RUN npm install -g @openai/codex@latest --registry "$NPM_REGISTRY"

# 验证 CLI 安装
RUN codex --version

# ============================================
# 阶段 2: 安装 Node.js 依赖
# ============================================

# Copy package files from L1_code_layer
COPY scc-bd/L1_code_layer/package.json /app/package.json

# Install Node dependencies
RUN npm config set registry "$NPM_REGISTRY"
RUN if [ -f package-lock.json ]; then npm ci --production; else npm install --production; fi

# ============================================
# 阶段 3: 安装 Python 依赖
# ============================================

# Install essential Python packages for SCC tools
RUN pip3 install --break-system-packages \
    pyyaml \
    jsonschema \
    requests \
    || true

# ============================================
# 阶段 4: 复制应用代码（按17层结构）
# ============================================

# Copy 17层分层代码
COPY scc-bd/L1_code_layer /app/L1_code_layer
COPY scc-bd/L2_task_layer /app/L2_task_layer
COPY scc-bd/L4_prompt_layer /app/L4_prompt_layer
COPY scc-bd/L5_model_layer /app/L5_model_layer
COPY scc-bd/L6_agent_layer /app/L6_agent_layer
COPY scc-bd/L6_execution_layer /app/L6_execution_layer
COPY scc-bd/L7_tool_layer /app/L7_tool_layer
COPY scc-bd/L9_state_layer /app/L9_state_layer
COPY scc-bd/L11_routing_layer /app/L11_routing_layer
COPY scc-bd/L13_security_layer /app/L13_security_layer
COPY scc-bd/L14_quality_layer /app/L14_quality_layer
COPY scc-bd/L15_change_layer /app/L15_change_layer
COPY scc-bd/L16_observability_layer /app/L16_observability_layer
COPY scc-bd/L17_ontology_layer /app/L17_ontology_layer

# Copy scripts
COPY scc-bd/scripts /app/scripts

# Copy entrypoint and service manager from L1_code_layer/docker
COPY scc-bd/L1_code_layer/docker/entrypoint.sh /app/entrypoint.sh
COPY scc-bd/L1_code_layer/docker/service-manager.mjs /app/L1_code_layer/docker/service-manager.mjs

# ============================================
# 阶段 5: 创建必要目录
# ============================================

RUN mkdir -p /app/artifacts/scc_state \
    /app/data \
    /app/logs \
    /app/state

# ============================================
# 阶段 6: 运行时配置
# ============================================

ENV REPO_ROOT=/app \
    SCC_REPO_ROOT=/app \
    GATEWAY_PORT=18788 \
    LOG_LEVEL=info \
    # CLI 工具路径
    CODEX_BIN=/usr/local/bin/codex \
    # Default upstreams (plugins)
    OPENCODE_UPSTREAM=http://host.docker.internal:18790 \
    CLAWDBOT_UPSTREAM=http://host.docker.internal:19001 \
    SCC_UPSTREAM=http://127.0.0.1:18789 \
    # Automation settings
    SCC_PARENT_INBOX=/app/artifacts/scc_state/parent_inbox.jsonl \
    SCC_AUTOMATION_MAX_OUTSTANDING=3 \
    # Role system
    ROLE_SYSTEM_STRICT=false \
    # Map settings
    AUTO_SPLIT_ON_PARENT_CREATE=true

# Expose main port
EXPOSE 18788

# Health check
HEALTHCHECK --interval=10s --timeout=5s --retries=5 --start-period=30s \
    CMD curl -f http://127.0.0.1:18788/health || exit 1

# Entrypoint
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["node", "L1_code_layer/gateway/gateway.mjs"]
