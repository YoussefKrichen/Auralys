from __future__ import annotations

import time
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
from app.ingestion.gold_fiche_adapter import load_gold_fiches
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

    fiches = load_fiches_from_directory(source_dir) + load_gold_fiches()
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


_QDRANT_UPSERT_BATCH_SIZE = 200
_EMBED_MAX_ATTEMPTS = 4
_EMBED_RETRY_BASE_SECONDS = 5.0


def _embed_with_retry(content: str, *, dimension: int) -> list[float]:
    """Retry a single embedding call across transient Gemini failures.

    Observed live on 2026-08-05: reindexing ~4800 chunks hit a 503
    UNAVAILABLE from Gemini twice in a row, at a different chunk each time
    (not a fixed quota wall). EmbeddingService.embed_text has no retry of
    its own, and worse, permanently sets `_gemini_disabled = True` on its
    instance after the *first* failure -- so reusing one EmbeddingService
    across the whole loop means one flaky call poisons every chunk after
    it. Building a fresh instance per attempt avoids that trap without
    touching the service's fail-fast behavior, which is the right default
    for the interactive query path.
    """
    last_error: Exception | None = None
    for attempt in range(_EMBED_MAX_ATTEMPTS):
        service = EmbeddingService(backend="gemini", dimension=dimension, allow_fallback=False)
        try:
            return service.embed_text(content, task_type="RETRIEVAL_DOCUMENT")
        except RuntimeError as exc:
            last_error = exc
            if attempt < _EMBED_MAX_ATTEMPTS - 1:
                time.sleep(_EMBED_RETRY_BASE_SECONDS * (2**attempt))
    assert last_error is not None
    raise last_error


def _write_qdrant(chunks: list[ChunkSchema]) -> dict[str, Any]:
    """Embed and upload in batches, not one request for every chunk.

    Bug found 2026-08-05: with ~4800 chunks x 768-dim vectors, a single
    upsert() call for the whole set is a large enough HTTP request that it
    reliably hit a write timeout -- and since recreate_collection() had
    already dropped the old collection first, that failure left Qdrant
    completely empty rather than merely stale.
    """
    embedding_service = EmbeddingService(backend="gemini", allow_fallback=False)
    client = get_qdrant_client()
    recreate_collection(client, embedding_service.dimension)
    batch: list[PointStruct] = []
    total_written = 0
    for offset, chunk in enumerate(chunks, start=1):
        batch.append(
            PointStruct(
                id=offset,
                vector=_embed_with_retry(chunk.content, dimension=embedding_service.dimension),
                payload=chunk.qdrant_payload(),
            )
        )
        if len(batch) >= _QDRANT_UPSERT_BATCH_SIZE:
            client.upsert(collection_name=settings.qdrant_collection, points=batch)
            total_written += len(batch)
            batch = []
    if batch:
        client.upsert(collection_name=settings.qdrant_collection, points=batch)
        total_written += len(batch)
    return {
        "qdrant_points": total_written,
        "embedding_backend": embedding_service.backend,
        "embedding_model": embedding_service.model_name,
    }


if __name__ == "__main__":
    print(reindex_all())
