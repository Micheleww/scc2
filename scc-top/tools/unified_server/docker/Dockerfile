FROM mcr.microsoft.com/devcontainers/python:3.12

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# The devcontainers base image already includes common system deps.
# Avoid apt-get here to prevent repo signature/key issues in locked-down networks.

# Optional mirrors (helpful in CN networks).
ARG PIP_INDEX_URL
ARG PIP_EXTRA_INDEX_URL
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_EXTRA_INDEX_URL=${PIP_EXTRA_INDEX_URL}

# Copy minimal dependency manifests first (for layer caching)
COPY tools/unified_server/requirements.txt /app/tools/unified_server/requirements.txt
COPY tools/mcp_bus/requirements.txt /app/tools/mcp_bus/requirements.txt
COPY tools/a2a_hub/requirements.txt /app/tools/a2a_hub/requirements.txt
COPY tools/exchange_server/requirements.txt /app/tools/exchange_server/requirements.txt
COPY requirements-langgraph.txt /app/requirements-langgraph.txt

# Offline wheelhouse (prepared on host at d:\quantsys\_wheelhouse).
COPY _wheelhouse /app/_wheelhouse

# Install deps (prefer offline wheelhouse; allow index as fallback if wheels are missing).
RUN python -m pip install --find-links=/app/_wheelhouse -r /app/tools/unified_server/requirements.txt \
 && python -m pip install --find-links=/app/_wheelhouse -r /app/tools/mcp_bus/requirements.txt \
 && python -m pip install --find-links=/app/_wheelhouse -r /app/tools/a2a_hub/requirements.txt \
 && python -m pip install --find-links=/app/_wheelhouse -r /app/tools/exchange_server/requirements.txt \
 && python -m pip install --find-links=/app/_wheelhouse -r /app/requirements-langgraph.txt

# Copy runtime code (only the subset needed for SCC unified server)
COPY tools/unified_server /app/tools/unified_server
COPY tools/scc /app/tools/scc
COPY tools/mcp_bus /app/tools/mcp_bus
COPY tools/a2a_hub /app/tools/a2a_hub
COPY tools/exchange_server /app/tools/exchange_server
COPY tools/yme /app/tools/yme
COPY tools/chatgpt_chat_archive_mvp /app/tools/chatgpt_chat_archive_mvp
COPY tools/scc_ui /app/tools/scc_ui
COPY src /app/src
COPY configs /app/configs
COPY contracts /app/contracts

# Default runtime config (can be overridden by compose env)
ENV REPO_ROOT=/app \
    UNIFIED_SERVER_HOST=0.0.0.0 \
    UNIFIED_SERVER_PORT=18788 \
    LOG_LEVEL=info \
    RELOAD=false \
    WATCHDOG_AUTO_RUN_AUTOMATION=false

EXPOSE 18788

HEALTHCHECK --interval=5s --timeout=3s --retries=30 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:18788/health/ready', timeout=2).read()"

CMD ["python", "tools/unified_server/start_unified_server.py"]
