"""
Routes package for unified server core
"""
from fastapi import FastAPI

from . import memory


def register_routes(app: FastAPI, repo_root) -> None:
    """Register all routes to the FastAPI application"""
    # Memory ledger routes
    app.include_router(memory.create_router(repo_root))

    # TODO: Add more routers as they are split from app_factory.py
