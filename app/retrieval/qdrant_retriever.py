from __future__ import annotations

from qdrant_client import QdrantClient
from qdrant_client.http import models as rest

from app.config import settings
from app.embeddings.embedding_service import EmbeddingService
from schemas.retrieval_schema import RetrievalFilters, RetrievalHit


class QdrantRetriever:
    def __init__(
        self,
        client: QdrantClient | None = None,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        self.client = client or QdrantClient(url=settings.qdrant_url, check_compatibility=False)
        self.embedding_service = embedding_service or EmbeddingService()

    def _build_filter(self, filters: RetrievalFilters) -> rest.Filter | None:
        conditions = []
        resolved_client_name = filters.client_name or filters.client
        if resolved_client_name:
            conditions.append(
                rest.FieldCondition(
                    key="client_name",
                    match=rest.MatchText(text=resolved_client_name),
                )
            )
        if filters.maintenance_number:
            conditions.append(
                rest.FieldCondition(
                    key="maintenance_number",
                    match=rest.MatchValue(value=filters.maintenance_number),
                )
            )
        if filters.chunk_type:
            conditions.append(
                rest.FieldCondition(
                    key="chunk_type",
                    match=rest.MatchValue(value=filters.chunk_type),
                )
            )
        if filters.source_file:
            conditions.append(
                rest.FieldCondition(
                    key="source_file",
                    match=rest.MatchText(text=filters.source_file),
                )
            )
        if not conditions:
            return None
        return rest.Filter(must=conditions)

    def search(
        self,
        query: str,
        filters: RetrievalFilters,
        limit: int | None = None,
    ) -> list[RetrievalHit]:
        requested_limit = limit or settings.semantic_limit
        response = self.client.query_points(
            collection_name=settings.qdrant_collection,
            query=self.embedding_service.embed_text(query, task_type="RETRIEVAL_QUERY"),
            query_filter=self._build_filter(filters),
            limit=max(requested_limit * 3, requested_limit),
        )
        results = response.points
        hits: list[RetrievalHit] = []
        for result in results:
            payload = result.payload or {}
            hits.append(
                RetrievalHit(
                    chunk_id=payload["chunk_id"],
                    fiche_id=payload["fiche_id"],
                    score=float(result.score),
                    content=payload["content"],
                    source=payload.get("source_file", "qdrant"),
                    metadata={
                        **payload,
                        "retriever": "qdrant",
                        "retrieval_score_raw": float(result.score),
                    },
                )
            )
        return hits[:requested_limit]
