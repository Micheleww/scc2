"""
Unified server service registry.

Keep this file ASCII-clean to avoid BOM/encoding issues when building/running in Docker.
"""

from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Any

from .service_wrappers import MCPService, A2AHubService, ExchangeServerService
from .clawdbot_service import ClawdbotService
from .opencode_proxy_service import OpenCodeProxyService
from .langgraph_service import LangGraphService
from .executor_service import ExecutorService
from .modelhub_service import ModelHubService
from .files_service import FilesService

logger = logging.getLogger(__name__)


def register_all_services(registry: Any, service_config: Any, repo_root: Path) -> None:
    """Register enabled services into the unified server registry."""

    if getattr(service_config, "mcp_bus_enabled", False):
        registry.register(
            "mcp_bus",
            MCPService(name="mcp_bus", path=service_config.mcp_bus_path, enabled=True, repo_root=repo_root),
        )

    if getattr(service_config, "a2a_hub_enabled", False):
        registry.register(
            "a2a_hub",
            A2AHubService(
                name="a2a_hub",
                path=service_config.a2a_hub_path,
                enabled=True,
                repo_root=repo_root,
                secret_key=service_config.a2a_hub_secret_key,
            ),
        )

    if getattr(service_config, "exchange_server_enabled", False) and getattr(service_config, "quant_app_enabled", True):
        registry.register(
            "exchange_server",
            ExchangeServerService(
                name="exchange_server",
                path=service_config.exchange_server_path,
                enabled=True,
                repo_root=repo_root,
                auth_mode=service_config.exchange_auth_mode,
            ),
        )

    if getattr(service_config, "langgraph_enabled", False):
        registry.register(
            "langgraph",
            LangGraphService(name="langgraph", path=service_config.langgraph_path, enabled=True, repo_root=repo_root),
        )

    if getattr(service_config, "clawdbot_enabled", False):
        use_auto_allocate = getattr(service_config, "clawdbot_gateway_port", 19001) == 19001
        primary_provider = os.getenv("CLAWDBOT_PRIMARY_PROVIDER", "opencode-zen")

        clawdbot_service = ClawdbotService(
            name="clawdbot",
            path=service_config.clawdbot_path,
            enabled=True,
            repo_root=repo_root,
            secret_key=service_config.clawdbot_secret_key,
            gateway_port=service_config.clawdbot_gateway_port if not use_auto_allocate else None,
            auto_allocate_port=use_auto_allocate,
            upstream=getattr(service_config, "clawdbot_upstream", ""),
            profile="kimi",
            auto_start_openclaw=True,
            primary_provider=primary_provider,
        )
        registry.register("clawdbot", clawdbot_service)

    if getattr(service_config, "opencode_enabled", False):
        registry.register(
            "opencode",
            OpenCodeProxyService(
                name="opencode",
                path=getattr(service_config, "opencode_path", "/opencode"),
                enabled=True,
                upstream=getattr(service_config, "opencode_upstream", "http://127.0.0.1:18790"),
            ),
        )

    registry.register(
        "executor",
        ExecutorService(name="executor", path="/executor", enabled=True, repo_root=repo_root),
    )

    registry.register(
        "files",
        FilesService(name="files", path="/files", enabled=True, repo_root=repo_root),
    )

    if getattr(service_config, "modelhub_enabled", False):
        registry.register(
            "modelhub",
            ModelHubService(
                name="modelhub",
                path=getattr(service_config, "modelhub_path", "/modelhub"),
                enabled=True,
                repo_root=repo_root,
            ),
        )

    if getattr(service_config, "yme_reports_enabled", False):
        from tools.yme.yme_report_service import YMEReportService

        registry.register(
            "yme_reports",
            YMEReportService(
                name="yme_reports",
                enabled=True,
                repo_root=repo_root,
                path=getattr(service_config, "yme_reports_path", "/yme"),
                data_path=getattr(service_config, "yme_data_path", None),
                metrics_path=getattr(service_config, "yme_metrics_path", None),
            ),
        )

