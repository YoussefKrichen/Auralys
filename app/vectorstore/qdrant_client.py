from __future__ import annotations

from typing import Any
from uuid import NAMESPACE_DNS, uuid5

from qdrant_client import QdrantClient
from qdrant_client.http import models


class QdrantGateway:
    def __init__(self, url: str) -> None:
        self.client = QdrantClient(url=url, check_compatibility=False)

    def ensure_collection(self, name: str, vector_size: int) -> None:
        try:
            self.client.get_collection(name)
        except Exception:
            self.client.create_collection(
                collection_name=name,
                vectors_config=models.VectorParams(
                    size=vector_size,
                    distance=models.Distance.COSINE,
                ),
            )

    def upsert_documents(
        self,
        *,
        collection_name: str,
        documents: list[dict[str, Any]],
        vectors: list[list[float]],
    ) -> None:
        points = []
        for document, vector in zip(documents, vectors, strict=False):
            point_id = str(uuid5(NAMESPACE_DNS, f"{collection_name}:{document['document_id']}"))
            payload = {
                "document_id": document["document_id"],
                "title": document["title"],
                "text": document["text"],
                "source_type": document.get("source_type", "document"),
                "metadata": document.get("metadata", {}),
            }
            points.append(models.PointStruct(id=point_id, vector=vector, payload=payload))
        if points:
            self.client.upsert(collection_name=collection_name, points=points, wait=True)

    def search(
        self,
        *,
        collection_name: str,
        query_vector: list[float],
        limit: int,
    ) -> list[dict[str, Any]]:
        results = self.client.search(
            collection_name=collection_name,
            query_vector=query_vector,
            limit=max(limit, 1),
        )
        payloads: list[dict[str, Any]] = []
        for item in results:
            payload = item.payload or {}
            payloads.append(
                {
                    "document_id": payload.get("document_id", str(item.id)),
                    "title": payload.get("title", ""),
                    "content": payload.get("text", ""),
                    "source_type": payload.get("source_type", "document"),
                    "metadata": payload.get("metadata", {}),
                    "collection": collection_name,
                    "score": float(item.score),
                }
            )
        return payloads

    def healthcheck(self) -> dict[str, Any]:
        collections = self.client.get_collections()
        return {
            "status": "ok",
            "collections": [item.name for item in collections.collections],
        }
