from __future__ import annotations

import uuid
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PayloadSchemaType, PointStruct, VectorParams

from app.config import settings
from app.embeddings.embedding_service import EmbeddingService
from app.ingestion.build_chunks import build_chunks
from app.ingestion.normalize import load_fiches_from_directory
from pathlib import Path
from schemas.chunk_schema import ChunkSchema


def get_qdrant_client(url: str | None = None) -> QdrantClient:
    return QdrantClient(url=url or settings.qdrant_url, check_compatibility=False)


def recreate_collection(client: QdrantClient, vector_size: int) -> None:
    client.recreate_collection(
        collection_name=settings.qdrant_collection,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )
    # client_name/source_file are queried with MatchText (substring/full-text), which needs
    # a TEXT index; chunk_type/maintenance_number are queried with MatchValue (exact match).
    for key in ("client_name", "source_file"):
        client.create_payload_index(
            collection_name=settings.qdrant_collection,
            field_name=key,
            field_schema=PayloadSchemaType.TEXT,
        )
    for key in ("chunk_type", "maintenance_number"):
        client.create_payload_index(
            collection_name=settings.qdrant_collection,
            field_name=key,
            field_schema=PayloadSchemaType.KEYWORD,
        )


def resolve_embedding_source_dir(raw_data_dir: str | None = None) -> str:
    if raw_data_dir:
        return raw_data_dir
    processed_dir = Path(settings.processed_data_dir)
    if processed_dir.exists() and any(processed_dir.rglob("*.json")):
        return str(processed_dir)
    return settings.raw_data_dir


def index_chunks(raw_data_dir: str | None = None) -> dict[str, int]:
    """Qdrant-only indexing. Prefer `app.ingestion.reindex.reindex_all` for
    routine use so Postgres and Qdrant stay in sync."""
    source_dir = resolve_embedding_source_dir(raw_data_dir)
    fiches = load_fiches_from_directory(source_dir)
    chunks = build_chunks(fiches)
    embedding_service = EmbeddingService(backend="gemini", allow_fallback=False)
    client = get_qdrant_client()
    recreate_collection(client, embedding_service.dimension)
    points = []
    for offset, chunk in enumerate(chunks, start=1):
        points.append(
            PointStruct(
                id=offset,
                vector=embedding_service.embed_text(chunk.content, task_type="RETRIEVAL_DOCUMENT"),
                payload=chunk.qdrant_payload(),
            )
        )
    client.upsert(collection_name=settings.qdrant_collection, points=points)
    return {
        "indexed_chunks": len(points),
        "source_dir": source_dir,
        "embedding_backend": embedding_service.backend,
        "embedding_model": embedding_service.model_name,
    }


def upsert_chunks_incremental(chunks: list[ChunkSchema]) -> dict[str, Any]:
    """Embed and upsert a small set of chunks into the existing collection without
    touching any other point (unlike index_chunks/reindex_all, which call
    recreate_collection and wipe the whole collection every time). Point IDs are
    derived deterministically from chunk_id (uuid5) instead of position, so this
    is safe to call repeatedly for the same chunk (updates in place) and cannot
    collide with the positional integer IDs used by the full-reindex path."""
    if not chunks:
        return {"qdrant_points": 0}
    embedding_service = EmbeddingService(backend="gemini", allow_fallback=False)
    client = get_qdrant_client()
    points = [
        PointStruct(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, chunk.chunk_id)),
            vector=embedding_service.embed_text(chunk.content, task_type="RETRIEVAL_DOCUMENT"),
            payload=chunk.qdrant_payload(),
        )
        for chunk in chunks
    ]
    client.upsert(collection_name=settings.qdrant_collection, points=points)
    return {
        "qdrant_points": len(points),
        "embedding_backend": embedding_service.backend,
        "embedding_model": embedding_service.model_name,
    }


if __name__ == "__main__":
    print(index_chunks())
