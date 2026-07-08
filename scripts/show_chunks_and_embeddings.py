from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.embeddings.embedding_service import EmbeddingService
from app.embeddings.index_qdrant import resolve_embedding_source_dir
from app.ingestion.build_chunks import build_chunks
from app.ingestion.normalize import load_fiches_from_directory


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Show sample chunks and embedding vectors from the current indexing pipeline.",
    )
    parser.add_argument(
        "--source-dir",
        help="Optional source directory. Defaults to the resolved embedding source directory.",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=3,
        help="Number of chunks to preview. Default: 3.",
    )
    parser.add_argument(
        "--chunk-index",
        type=int,
        default=0,
        help="Zero-based chunk index to embed. Default: 0.",
    )
    parser.add_argument(
        "--backend",
        choices=("gemini", "local"),
        default="gemini",
        help="Embedding backend to use for the vector sample. Default: gemini.",
    )
    parser.add_argument(
        "--allow-fallback",
        action="store_true",
        help="Allow fallback to local embeddings when Gemini is selected but unavailable.",
    )
    parser.add_argument(
        "--task-type",
        choices=("RETRIEVAL_QUERY", "RETRIEVAL_DOCUMENT", "SEMANTIC_SIMILARITY"),
        default="RETRIEVAL_DOCUMENT",
        help="Embedding task type. Default: RETRIEVAL_DOCUMENT.",
    )
    parser.add_argument(
        "--preview-chars",
        type=int,
        default=700,
        help="Maximum characters to print for chunk content. Default: 700.",
    )
    parser.add_argument(
        "--vector-size",
        type=int,
        default=16,
        help="How many embedding values to print from the start of the vector. Default: 16.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print output as JSON.",
    )
    return parser


def l2_norm(vector: list[float]) -> float:
    return sum(value * value for value in vector) ** 0.5


def serialize_chunk(chunk, preview_chars: int) -> dict[str, object]:
    return {
        "chunk_id": chunk.chunk_id,
        "fiche_id": chunk.fiche_id,
        "chunk_type": getattr(chunk.chunk_type, "value", str(chunk.chunk_type)),
        "ordinal": chunk.ordinal,
        "source_file": chunk.source_file,
        "page_key": chunk.page_key,
        "content_preview": chunk.content[:preview_chars].replace("\n", " "),
        "metadata": chunk.metadata,
    }


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    source_dir = resolve_embedding_source_dir(args.source_dir)
    fiches = load_fiches_from_directory(source_dir)
    chunks = build_chunks(fiches)
    if not chunks:
        raise RuntimeError(f"No chunks were generated from `{source_dir}`.")

    if args.chunk_index < 0 or args.chunk_index >= len(chunks):
        raise IndexError(
            f"chunk-index {args.chunk_index} is out of range for {len(chunks)} generated chunks."
        )

    sample_chunks = chunks[: max(args.samples, 1)]
    target_chunk = chunks[args.chunk_index]
    embedding_service = EmbeddingService(
        backend=args.backend,
        allow_fallback=args.allow_fallback,
    )
    vector = embedding_service.embed_text(
        target_chunk.content,
        task_type=args.task_type,
    )

    payload = {
        "source_dir": source_dir,
        "fiche_count": len(fiches),
        "chunk_count": len(chunks),
        "sample_chunks": [serialize_chunk(chunk, args.preview_chars) for chunk in sample_chunks],
        "embedded_chunk_index": args.chunk_index,
        "embedded_chunk": serialize_chunk(target_chunk, args.preview_chars),
        "embedding": {
            "backend": embedding_service.backend,
            "model_name": embedding_service.model_name,
            "dimension": len(vector),
            "first_values": [round(value, 6) for value in vector[: max(args.vector_size, 1)]],
            "l2_norm": round(l2_norm(vector), 6),
            "fallback_allowed": embedding_service.allow_fallback,
        },
    }

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    print(f"SOURCE_DIR: {payload['source_dir']}")
    print(f"FICHES: {payload['fiche_count']}")
    print(f"CHUNKS: {payload['chunk_count']}")
    for index, chunk_payload in enumerate(payload["sample_chunks"], start=1):
        print(f"--- CHUNK {index} ---")
        print(f"chunk_id: {chunk_payload['chunk_id']}")
        print(f"fiche_id: {chunk_payload['fiche_id']}")
        print(f"chunk_type: {chunk_payload['chunk_type']}")
        print(f"source_file: {chunk_payload['source_file']}")
        print(f"content: {chunk_payload['content_preview']}")

    embedding_payload = payload["embedding"]
    print("--- EMBEDDING SAMPLE ---")
    print(f"embedded_chunk_index: {payload['embedded_chunk_index']}")
    print(f"embedded_chunk_id: {payload['embedded_chunk']['chunk_id']}")
    print(f"backend: {embedding_payload['backend']}")
    print(f"model: {embedding_payload['model_name']}")
    print(f"dimension: {embedding_payload['dimension']}")
    print(f"first_values: {embedding_payload['first_values']}")
    print(f"l2_norm: {embedding_payload['l2_norm']}")


if __name__ == "__main__":
    main()
