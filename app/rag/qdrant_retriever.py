from __future__ import annotations

from app.core.config import Settings
from app.graph.state import ContextDocument
from app.rag.embeddings import EmbeddingProvider
from app.vectorstore.qdrant_client import QdrantGateway


class QdrantRetriever:
    def __init__(
        self,
        gateway: QdrantGateway,
        settings: Settings,
        embeddings: EmbeddingProvider,
    ) -> None:
        self.gateway = gateway
        self.settings = settings
        self.embeddings = embeddings

    def retrieve(
        self,
        *,
        query: str,
        include_memory: bool,
    ) -> list[ContextDocument]:
        query_vector = self.embeddings.embed_query(query)
        collections = [self.settings.qdrant_documents_collection]
        if include_memory:
            collections.append(self.settings.qdrant_memory_collection)

        results: list[ContextDocument] = []
        for collection_name in collections:
            for item in self.gateway.search(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=self.settings.qdrant_search_limit,
            ):
                results.append(
                    ContextDocument(
                        document_id=item["document_id"],
                        collection=item["collection"],
                        score=item["score"],
                        content=item["content"],
                        metadata={
                            "title": item["title"],
                            "source_type": item["source_type"],
                            **item["metadata"],
                        },
                    )
                )
        results.sort(key=lambda item: item.score or 0.0, reverse=True)
        return results[: self.settings.qdrant_search_limit]
