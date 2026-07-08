from __future__ import annotations

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PayloadSchemaType, PointStruct, VectorParams

from app.config import settings
from app.embeddings.embedding_service import EmbeddingService
from app.ingestion.build_chunks import build_chunks
from app.ingestion.normalize import load_fiches_from_directory
from pathlib import Path


def get_qdrant_client(url: str | None = None) -> QdrantClient:
    return QdrantClient(url=url or settings.qdrant_url, check_compatibility=False)


def recreate_collection(client: QdrantClient, vector_size: int) -> None:
    client.recreate_collection(
        collection_name=settings.qdrant_collection,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )
    for key in ("client_name", "chunk_type", "source_file"):
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


if __name__ == "__main__":
    print(index_chunks())
