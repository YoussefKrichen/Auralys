from __future__ import annotations

from app.db import Database, default_database
from app.ingestion.build_chunks import build_chunks
from app.ingestion.normalize import fiches_to_rows, load_fiches_from_directory
from app.config import settings


def ingest_raw_json(
    raw_data_dir: str | None = None,
    database: Database | None = None,
) -> dict[str, int]:
    data_dir = raw_data_dir or settings.raw_data_dir
    database = database or default_database
    fiches = load_fiches_from_directory(data_dir)
    chunks = build_chunks(fiches)
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
    return {"fiches": len(fiches), "chunks": len(chunks)}


if __name__ == "__main__":
    print(ingest_raw_json())
