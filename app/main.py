from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import uvicorn
from fastapi import FastAPI

from app.agents import (
    ClientAgent,
    CoordinatorAgent,
    DiffuseurAgent,
    DocumentsAgent,
    RecommendationAgent,
    ReportLearningAgent,
    SAVAgent,
    TechnicienAgent,
)
from app.agents.base import MockLLMClient
from app.api.routes import router as auralys_router
from app.core.config import Settings, get_settings
from app.db.postgres import PostgresDatabase
from app.db.seed import seed_postgres
from app.graph.graph_builder import AuralysGraphService, GraphNodes
from app.graph.router import IntentRouter
from app.graph.state import DocumentsIndexRequest, DocumentsIndexResponse
from app.rag.embeddings import FakeEmbeddingProvider
from app.rag.hybrid_retriever import HybridRetriever
from app.rag.postgres_retriever import PostgresRetriever
from app.rag.qdrant_retriever import QdrantRetriever
from app.services.context_builder import ContextBuilder
from app.services.response_builder import ResponseBuilder
from app.services.validation_service import ValidationService
from app.vectorstore.collections import CollectionManager
from app.vectorstore.qdrant_client import QdrantGateway


@dataclass
class AuralysContainer:
    settings: Settings
    database: PostgresDatabase
    qdrant_gateway: QdrantGateway
    collection_manager: CollectionManager
    graph_service: AuralysGraphService
    validation_service: ValidationService
    initialized: bool = False

    def initialize(self) -> None:
        if self.initialized:
            return
        self.database.initialize_schema()
        self.collection_manager.ensure_core_collections()
        if self.settings.auto_seed:
            seed_postgres(self.database)
            self.collection_manager.seed_demo_collections()
        self.initialized = True

    def healthcheck(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "postgres": self.database.healthcheck(),
            "qdrant": self.qdrant_gateway.healthcheck(),
        }

    def index_documents(self, request: DocumentsIndexRequest) -> DocumentsIndexResponse:
        collection_name = (
            self.settings.qdrant_documents_collection
            if request.collection == "auralys_documents"
            else self.settings.qdrant_memory_collection
        )
        self.collection_manager.index_documents(
            collection_name=collection_name,
            documents=[document.model_dump() for document in request.documents],
        )
        return DocumentsIndexResponse(
            collection=request.collection,
            indexed_count=len(request.documents),
        )


def build_container(settings: Settings | None = None) -> AuralysContainer:
    settings = settings or get_settings()
    database = PostgresDatabase(dsn=settings.postgres_dsn)
    embeddings = FakeEmbeddingProvider(dimension=settings.embedding_dimension)
    qdrant_gateway = QdrantGateway(url=settings.qdrant_url)
    collection_manager = CollectionManager(
        gateway=qdrant_gateway,
        settings=settings,
        embeddings=embeddings,
    )
    postgres_retriever = PostgresRetriever(database=database)
    qdrant_retriever = QdrantRetriever(
        gateway=qdrant_gateway,
        settings=settings,
        embeddings=embeddings,
    )
    hybrid_retriever = HybridRetriever(
        postgres_retriever=postgres_retriever,
        qdrant_retriever=qdrant_retriever,
    )
    llm = MockLLMClient()
    context_builder = ContextBuilder(retriever=hybrid_retriever)
    router = IntentRouter()
    response_builder = ResponseBuilder()
    graph_nodes = GraphNodes(
        coordinator=CoordinatorAgent(router=router, context_builder=context_builder, llm=llm),
        sav_agent=SAVAgent(llm=llm),
        client_agent=ClientAgent(llm=llm),
        diffuseur_agent=DiffuseurAgent(llm=llm),
        technicien_agent=TechnicienAgent(llm=llm),
        documents_agent=DocumentsAgent(llm=llm),
        recommendation_agent=RecommendationAgent(llm=llm),
        report_learning_agent=ReportLearningAgent(llm=llm),
        response_builder=response_builder,
    )
    graph_service = AuralysGraphService(nodes=graph_nodes)
    validation_service = ValidationService()
    return AuralysContainer(
        settings=settings,
        database=database,
        qdrant_gateway=qdrant_gateway,
        collection_manager=collection_manager,
        graph_service=graph_service,
        validation_service=validation_service,
    )


def create_app(container: AuralysContainer | None = None) -> FastAPI:
    owns_container = container is None
    container = container or build_container()
    settings = getattr(container, "settings", get_settings())

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if owns_container:
            container.initialize()
        app.state.container = container
        yield

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Auralys backend with FastAPI, LangGraph, PostgreSQL and Qdrant.",
        lifespan=lifespan,
    )
    app.state.container = container
    app.include_router(auralys_router)

    @app.get("/")
    def root() -> dict[str, str]:
        return {
            "name": settings.app_name,
            "status": "ok",
            "health": f"{settings.api_prefix}/health",
            "invoke": f"{settings.api_prefix}/invoke",
        }

    return app


# `create_app` above builds the legacy mock-stack app (kept for reference/tests,
# see AURALYS_TASKS.md for the stack-consolidation decision). The server that is
# actually served wires the real stack (AppContainer, agent orchestrator, RAG
# pipeline, history/review) so the frontend has something to talk to.
from app.api import create_app as _create_real_app  # noqa: E402

app = _create_real_app()


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
