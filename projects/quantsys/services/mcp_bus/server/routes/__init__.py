"""
Routes package for MCP Bus server
"""
from fastapi import FastAPI

from . import system, auth, performance, risk, alerts


def register_routes(app: FastAPI) -> None:
    """Register all routes to the FastAPI application"""
    # System and monitoring routes
    app.include_router(system.router)

    # Authentication routes
    app.include_router(auth.router)

    # Performance analysis routes
    app.include_router(performance.router)

    # Risk analysis routes
    app.include_router(risk.router)

    # Alerts management routes
    app.include_router(alerts.router)

    # TODO: Add more routers as they are split from main.py
    # from . import portfolio, agents, configs, reports, viewer, etc.
