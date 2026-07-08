from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.rag.postgres_retriever import PostgresRetriever
from app.rag.qdrant_retriever import QdrantRetriever


class HybridContext(BaseModel):
    sql_context: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    vector_context: list[dict[str, Any]] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


class HybridRetriever:
    def __init__(
        self,
        postgres_retriever: PostgresRetriever,
        qdrant_retriever: QdrantRetriever,
    ) -> None:
        self.postgres_retriever = postgres_retriever
        self.qdrant_retriever = qdrant_retriever

    def decide_mode(self, *, request_type: str, query: str) -> str:
        normalized_query = query.casefold()
        if request_type in {"document_analysis", "report_learning"}:
            return "hybrid"
        if any(keyword in normalized_query for keyword in ("document", "email", "rapport", "fiche")):
            return "hybrid"
        if request_type in {"recommendation_analysis", "sav_analysis"}:
            return "hybrid"
        if request_type in {"client_analysis", "diffuseur_analysis", "technicien_analysis"}:
            return "postgres"
        return "hybrid"

    def retrieve(
        self,
        *,
        request_type: str,
        query: str,
        client_id: int | None = None,
        diffuseur_id: int | None = None,
        technicien_id: int | None = None,
    ) -> HybridContext:
        mode = self.decide_mode(request_type=request_type, query=query)
        sql_context: dict[str, list[dict[str, Any]]] = {}
        vector_context: list[dict[str, Any]] = []
        sources: list[str] = []

        if mode in {"postgres", "hybrid"}:
            sql_context = self.postgres_retriever.retrieve(
                request_type=request_type,
                client_id=client_id,
                diffuseur_id=diffuseur_id,
                technicien_id=technicien_id,
            )
            sources.append("postgres")

        if mode in {"qdrant", "hybrid"}:
            include_memory = request_type in {
                "document_analysis",
                "recommendation_analysis",
                "report_learning",
                "sav_analysis",
            }
            vector_context = [
                item.model_dump()
                for item in self.qdrant_retriever.retrieve(
                    query=query,
                    include_memory=include_memory,
                )
            ]
            sources.append("qdrant")

        return HybridContext(
            sql_context=sql_context,
            vector_context=vector_context,
            sources=sources,
        )
