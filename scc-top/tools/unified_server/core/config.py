"""
配置管理模块

基于Pydantic的配置管理，支持：
- 环境变量覆盖
- 配置验证
- 多环境支持
"""

import os
from typing import Optional, List
from pydantic import Field, validator
try:
    from pydantic_settings import BaseSettings
except ImportError:
    # 兼容旧版本pydantic
    from pydantic import BaseSettings


def _get_env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None:
        return default
    value = str(value).strip()
    return value if value else default


def _get_env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    raw = str(raw).strip()
    if not raw:
        return default
    try:
        return int(raw, 10)
    except Exception:
        return default


def _get_env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    raw = str(raw).strip().lower()
    if raw in {"1", "true", "yes", "y", "on"}:
        return True
    if raw in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _get_env_list(name: str, default: List[str]) -> List[str]:
    raw = os.getenv(name)
    if raw is None:
        return default
    raw = str(raw).strip()
    if not raw:
        return default
    return [part.strip() for part in raw.split(",") if part.strip()]


class ServerConfig(BaseSettings):
    """服务器配置"""
    
    # 服务器基本配置
    host: str = Field(default="127.0.0.1", env="UNIFIED_SERVER_HOST")
    # NOTE: unified server is standardized to 18788 in this repo (single-port access).
    port: int = Field(default=18788, env="UNIFIED_SERVER_PORT")
    workers: int = Field(default=1, env="UNIFIED_SERVER_WORKERS")
    log_level: str = Field(default="debug", env="LOG_LEVEL")
    reload: bool = Field(default=False, env="RELOAD")
    
    # 应用配置
    app_name: str = Field(default="QuantSys Unified Server", env="APP_NAME")
    app_version: str = Field(default="1.0.0", env="APP_VERSION")
    debug: bool = Field(default=False, env="DEBUG")
    
    # CORS配置
    cors_origins: List[str] = Field(
        # Include dev UI origins (Vite/Electron) + "null" origin (file://) for local desktop usage.
        default=[
            "http://localhost:18788",
            "http://127.0.0.1:18788",
            "http://localhost:8040",
            "http://127.0.0.1:8040",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
            "null",
        ],
        env="CORS_ORIGINS"
    )
    cors_allow_credentials: bool = Field(default=True, env="CORS_ALLOW_CREDENTIALS")
    
    # 健康检查配置
    health_check_enabled: bool = Field(default=True, env="HEALTH_CHECK_ENABLED")
    health_check_interval: int = Field(default=30, env="HEALTH_CHECK_INTERVAL")
    
    # 优雅关闭配置
    graceful_shutdown_timeout: int = Field(default=30, env="GRACEFUL_SHUTDOWN_TIMEOUT")
    
    # 项目路径
    repo_root: Optional[str] = Field(default=None, env="REPO_ROOT")
    
    @validator("cors_origins", pre=True)
    def parse_cors_origins(cls, v):
        """解析CORS origins字符串"""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v
    
    @validator("log_level")
    def validate_log_level(cls, v):
        """验证日志级别"""
        valid_levels = ["debug", "info", "warning", "error", "critical"]
        if v.lower() not in valid_levels:
            raise ValueError(f"Log level must be one of {valid_levels}")
        return v.lower()
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


class ServiceConfig(BaseSettings):
    """服务配置"""
    
    # MCP总线配置
    mcp_bus_enabled: bool = Field(default=True, env="MCP_BUS_ENABLED")
    mcp_bus_path: str = Field(default="/mcp", env="MCP_BUS_PATH")
    
    # A2A Hub配置
    a2a_hub_enabled: bool = Field(default=True, env="A2A_HUB_ENABLED")
    a2a_hub_path: str = Field(default="/api", env="A2A_HUB_PATH")
    a2a_hub_secret_key: Optional[str] = Field(default=None, env="A2A_HUB_SECRET_KEY")
    
    # Exchange Server配置
    # NOTE: Quant app services are separable from SCC platform.
    quant_app_enabled: bool = Field(default=True, env="QUANT_APP_ENABLED")
    exchange_server_enabled: bool = Field(default=True, env="EXCHANGE_SERVER_ENABLED")
    exchange_server_path: str = Field(default="/exchange", env="EXCHANGE_SERVER_PATH")
    exchange_auth_mode: str = Field(default="none", env="EXCHANGE_AUTH_MODE")
    
    # LangGraph服务配置
    langgraph_enabled: bool = Field(default=True, env="LANGGRAPH_ENABLED")
    langgraph_path: str = Field(default="/langgraph", env="LANGGRAPH_PATH")
    
    # Clawdbot服务配置
    clawdbot_enabled: bool = Field(default=True, env="CLAWDBOT_ENABLED")
    clawdbot_path: str = Field(default="/clawdbot", env="CLAWDBOT_PATH")
    clawdbot_gateway_port: int = Field(default=19001, env="CLAWDBOT_GATEWAY_PORT")
    # Optional full upstream base URL (useful in Docker where gateway runs on the host)
    # Example: http://host.docker.internal:19001
    clawdbot_upstream: str = Field(default="", env="CLAWDBOT_UPSTREAM")
    clawdbot_secret_key: Optional[str] = Field(default=None, env="CLAWDBOT_SECRET_KEY")

    # OpenCode (UI/API) proxy service config
    opencode_enabled: bool = Field(default=False, env="OPENCODE_ENABLED")
    opencode_path: str = Field(default="/opencode", env="OPENCODE_PATH")
    # Example: http://host.docker.internal:18790 (when OpenCode runs on Windows host)
    opencode_upstream: str = Field(default="http://127.0.0.1:18790", env="OPENCODE_UPSTREAM")

    # ModelHub（远端算力模型库）代理服务
    modelhub_enabled: bool = Field(default=False, env="MODELHUB_ENABLED")
    modelhub_path: str = Field(default="/modelhub", env="MODELHUB_PATH")

    # YME 报表 Demo 服务
    # NOTE: YME is a separate app; SCC core should not depend on it.
    yme_reports_enabled: bool = Field(default=False, env="YME_REPORTS_ENABLED")
    yme_reports_path: str = Field(default="/yme", env="YME_REPORTS_PATH")
    yme_data_path: Optional[str] = Field(default=None, env="YME_DATA_PATH")
    yme_metrics_path: Optional[str] = Field(default=None, env="YME_METRICS_PATH")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


def get_config() -> ServerConfig:
    """获取服务器配置"""
    # NOTE:
    # 在 pydantic-settings v2 中，Field(env=...) 可能不会按预期生效（取决于版本差异）。
    # 为保证 Windows/CI 环境稳定，这里显式从环境变量读取并注入，确保端口等配置可控。
    default = ServerConfig()
    return ServerConfig(
        host=_get_env_str("UNIFIED_SERVER_HOST", default.host),
        port=_get_env_int("UNIFIED_SERVER_PORT", default.port),
        workers=_get_env_int("UNIFIED_SERVER_WORKERS", default.workers),
        log_level=_get_env_str("LOG_LEVEL", default.log_level),
        reload=_get_env_bool("RELOAD", default.reload),
        app_name=_get_env_str("APP_NAME", default.app_name),
        app_version=_get_env_str("APP_VERSION", default.app_version),
        debug=_get_env_bool("DEBUG", default.debug),
        cors_origins=_get_env_list("CORS_ORIGINS", default.cors_origins),
        cors_allow_credentials=_get_env_bool(
            "CORS_ALLOW_CREDENTIALS", default.cors_allow_credentials
        ),
        health_check_enabled=_get_env_bool(
            "HEALTH_CHECK_ENABLED", default.health_check_enabled
        ),
        health_check_interval=_get_env_int(
            "HEALTH_CHECK_INTERVAL", default.health_check_interval
        ),
        graceful_shutdown_timeout=_get_env_int(
            "GRACEFUL_SHUTDOWN_TIMEOUT", default.graceful_shutdown_timeout
        ),
        repo_root=os.getenv("REPO_ROOT", default.repo_root),
    )


def get_service_config() -> ServiceConfig:
    """获取服务配置"""
    default = ServiceConfig()
    return ServiceConfig(
        mcp_bus_enabled=_get_env_bool("MCP_BUS_ENABLED", default.mcp_bus_enabled),
        mcp_bus_path=_get_env_str("MCP_BUS_PATH", default.mcp_bus_path),
        a2a_hub_enabled=_get_env_bool("A2A_HUB_ENABLED", default.a2a_hub_enabled),
        a2a_hub_path=_get_env_str("A2A_HUB_PATH", default.a2a_hub_path),
        a2a_hub_secret_key=os.getenv("A2A_HUB_SECRET_KEY", default.a2a_hub_secret_key),
        quant_app_enabled=_get_env_bool("QUANT_APP_ENABLED", default.quant_app_enabled),
        exchange_server_enabled=_get_env_bool(
            "EXCHANGE_SERVER_ENABLED", default.exchange_server_enabled
        ),
        exchange_server_path=_get_env_str(
            "EXCHANGE_SERVER_PATH", default.exchange_server_path
        ),
        exchange_auth_mode=_get_env_str("EXCHANGE_AUTH_MODE", default.exchange_auth_mode),
        langgraph_enabled=_get_env_bool("LANGGRAPH_ENABLED", default.langgraph_enabled),
        langgraph_path=_get_env_str("LANGGRAPH_PATH", default.langgraph_path),
        clawdbot_enabled=_get_env_bool("CLAWDBOT_ENABLED", default.clawdbot_enabled),
        clawdbot_path=_get_env_str("CLAWDBOT_PATH", default.clawdbot_path),
        clawdbot_gateway_port=_get_env_int(
            "CLAWDBOT_GATEWAY_PORT", default.clawdbot_gateway_port
        ),
        clawdbot_upstream=_get_env_str("CLAWDBOT_UPSTREAM", default.clawdbot_upstream),
        clawdbot_secret_key=os.getenv("CLAWDBOT_SECRET_KEY", default.clawdbot_secret_key),
        opencode_enabled=_get_env_bool("OPENCODE_ENABLED", default.opencode_enabled),
        opencode_path=_get_env_str("OPENCODE_PATH", default.opencode_path),
        opencode_upstream=_get_env_str("OPENCODE_UPSTREAM", default.opencode_upstream),
        modelhub_enabled=_get_env_bool("MODELHUB_ENABLED", default.modelhub_enabled),
        modelhub_path=_get_env_str("MODELHUB_PATH", default.modelhub_path),
        yme_reports_enabled=_get_env_bool("YME_REPORTS_ENABLED", default.yme_reports_enabled),
        yme_reports_path=_get_env_str("YME_REPORTS_PATH", default.yme_reports_path),
        yme_data_path=os.getenv("YME_DATA_PATH", default.yme_data_path),
        yme_metrics_path=os.getenv("YME_METRICS_PATH", default.yme_metrics_path),
    )
