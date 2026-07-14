from __future__ import annotations

from app.db import Database, default_database
from app.embeddings.index_qdrant import resolve_embedding_source_dir


def ingest_raw_json(
    raw_data_dir: str | None = None,
    database: Database | None = None,
) -> dict[str, int]:
    """Postgres-only ingestion. Prefer `app.ingestion.reindex.reindex_all` for
    routine use so Postgres and Qdrant stay in sync — this is kept for
    Postgres-only maintenance runs, and reuses the same directory-resolution
    rule as Qdrant indexing so a standalone run can't silently target a
    different source directory than the vector store."""
    from app.ingestion.reindex import _write_postgres
    from app.ingestion.build_chunks import build_chunks
    from app.ingestion.normalize import load_fiches_from_directory

    data_dir = resolve_embedding_source_dir(raw_data_dir)
    database = database or default_database
    fiches = load_fiches_from_directory(data_dir)
    chunks = build_chunks(fiches)
    stats = _write_postgres(fiches, chunks, database)
    return {"fiches": len(fiches), "chunks": len(chunks), **stats}


if __name__ == "__main__":
    print(ingest_raw_json())
