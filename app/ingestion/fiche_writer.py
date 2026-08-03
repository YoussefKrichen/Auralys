from __future__ import annotations

from typing import Any

from app.db import Database, default_database
from app.embeddings.index_qdrant import upsert_chunks_incremental
from app.ingestion.build_chunks import build_chunks_for_fiche
from app.ingestion.normalize import fiches_to_rows
from schemas.chunk_schema import ChunkSchema, ChunkType
from schemas.fiche_schema import FicheSchema


def commit_agent_captured_fiche(
    fiche_payload: dict[str, Any],
    database: Database | None = None,
) -> dict[str, Any]:
    """Write a single agent-captured fiche (and its chunks) to Postgres and Qdrant
    incrementally -- unlike reindex_all()/index_chunks(), this never recreates the
    Qdrant collection or touches any other fiche/point."""
    database = database or default_database
    fiche = FicheSchema(**fiche_payload)
    chunks = build_chunks_for_fiche(fiche)

    database.init_schema()
    with database.connection() as connection:
        for fiche_row in fiches_to_rows([fiche]):
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

    qdrant_stats = upsert_chunks_incremental(chunks)
    return {
        "fiche_id": fiche.fiche_id,
        "postgres_chunks": len(chunks),
        **qdrant_stats,
    }


def commit_ceo_correction(memory_row: dict[str, Any]) -> dict[str, Any]:
    """Upsert a CEO-approved correction (a `memories` row of type KNOWLEDGE_CORRECTION)
    into Qdrant as a retrievable chunk, so it surfaces for related future questions.
    Chunk id is derived from the memory id so re-approving an edited correction updates
    the same Qdrant point instead of creating a duplicate. Postgres-side, the `memories`
    row is the source of truth -- this only ever touches Qdrant."""
    memory_id = memory_row["id"]
    metadata = memory_row.get("metadata") or {}
    topic = metadata.get("topic") or "general"
    chunk = ChunkSchema(
        chunk_id=f"ceo_correction:{memory_id}",
        fiche_id=f"ceo_correction:{memory_id}",
        source_file="ceo_correction",
        page_key=str(topic),
        chunk_type=ChunkType.information,
        content=memory_row["content"],
        metadata={
            "is_correction": True,
            "memory_id": memory_id,
            "topic": topic,
            "original_query": metadata.get("original_query"),
        },
    )
    return upsert_chunks_incremental([chunk])
