from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import agent_routes
from app.bootstrap import AppContainer
from app.config import settings


def create_app(container: AppContainer | None = None) -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.2.0",
        description="Auralys backend: agent orchestrator, RAG pipeline, history and review API.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_public_url],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(agent_routes.router)
    if container is not None:
        app.dependency_overrides[agent_routes.get_container] = lambda: container
    return app


__all__ = ["create_app", "agent_routes"]
