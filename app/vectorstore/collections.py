from __future__ import annotations

from app.core.config import Settings
from app.db.seed import DEMO_MEMORY_DOCUMENTS, DEMO_VECTOR_DOCUMENTS
from app.rag.embeddings import EmbeddingProvider
from app.vectorstore.qdrant_client import QdrantGateway


class CollectionManager:
    def __init__(
        self,
        gateway: QdrantGateway,
        settings: Settings,
        embeddings: EmbeddingProvider,
    ) -> None:
        self.gateway = gateway
        self.settings = settings
        self.embeddings = embeddings

    def ensure_core_collections(self) -> None:
        self.gateway.ensure_collection(
            self.settings.qdrant_documents_collection,
            self.embeddings.dimension,
        )
        self.gateway.ensure_collection(
            self.settings.qdrant_memory_collection,
            self.embeddings.dimension,
        )

    def seed_demo_collections(self) -> None:
        self.index_documents(
            collection_name=self.settings.qdrant_documents_collection,
            documents=DEMO_VECTOR_DOCUMENTS,
        )
        self.index_documents(
            collection_name=self.settings.qdrant_memory_collection,
            documents=DEMO_MEMORY_DOCUMENTS,
        )

    def index_documents(self, *, collection_name: str, documents: list[dict]) -> None:
        vectors = self.embeddings.embed_documents([document["text"] for document in documents])
        self.gateway.upsert_documents(
            collection_name=collection_name,
            documents=documents,
            vectors=vectors,
        )
