from __future__ import annotations

from typing import Any

from qdrant_client.models import PointStruct

from app.config import settings
from app.db import Database, default_database
from app.embeddings.embedding_service import EmbeddingService
from app.embeddings.index_qdrant import (
    get_qdrant_client,
    recreate_collection,
    resolve_embedding_source_dir,
)
from app.ingestion.build_chunks import build_chunks
from app.ingestion.normalize import fiches_to_rows, load_fiches_from_directory
from schemas.chunk_schema import ChunkSchema
from schemas.fiche_schema import FicheSchema


def reindex_all(
    raw_data_dir: str | None = None,
    database: Database | None = None,
) -> dict[str, Any]:
    """Single entrypoint for ingestion: loads fiches/chunks from disk once and
    writes that exact set to both Postgres and Qdrant in the same run, so the two
    stores cannot silently diverge (they used to be populated by two independent
    scripts, each reloading the source directory on its own)."""
    source_dir = resolve_embedding_source_dir(raw_data_dir)
    database = database or default_database

    fiches = load_fiches_from_directory(source_dir)
    chunks = build_chunks(fiches)

    postgres_stats = _write_postgres(fiches, chunks, database)
    qdrant_stats = _write_qdrant(chunks)

    return {
        "source_dir": source_dir,
        "fiches": len(fiches),
        "chunks": len(chunks),
        **postgres_stats,
        **qdrant_stats,
    }


def _write_postgres(
    fiches: list[FicheSchema],
    chunks: list[ChunkSchema],
    database: Database,
) -> dict[str, int]:
    database.init_schema()
    with database.connection() as connection:
        for fiche_row in fiches_to_rows(fiches):
            database.upsert_fiche(connection, fiche_row)
        for chunk in chunks:
            database.upsert_chunk(
                connection,
                {
                    "chunk_id": chunk.chunk_id,
                    "fiche_id": chunk.fiche_id,
                    "source_file": chunk.source_file,
                    "page_key": chunk.page_key,
                    "chunk_type": chunk.chunk_type.value,
                    "ordinal": chunk.ordinal,
                    "content": chunk.content,
                    "metadata": chunk.metadata,
                },
            )
        orphan_chunks_deleted = database.delete_orphan_chunks(
            connection,
            fiche_ids=[fiche.fiche_id for fiche in fiches],
            keep_chunk_ids=[chunk.chunk_id for chunk in chunks],
        )
        orphan_fiches_deleted = database.delete_orphan_fiches(
            connection,
            keep_fiche_ids=[fiche.fiche_id for fiche in fiches],
        )
    return {
        "postgres_fiches": len(fiches),
        "postgres_chunks": len(chunks),
        "postgres_orphan_chunks_deleted": orphan_chunks_deleted,
        "postgres_orphan_fiches_deleted": orphan_fiches_deleted,
    }


def _write_qdrant(chunks: list[ChunkSchema]) -> dict[str, Any]:
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
        "qdrant_points": len(points),
        "embedding_backend": embedding_service.backend,
        "embedding_model": embedding_service.model_name,
    }


if __name__ == "__main__":
    print(reindex_all())
