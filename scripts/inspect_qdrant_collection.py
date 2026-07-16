from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.embeddings.index_qdrant import get_qdrant_client


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect what is actually stored in the live Qdrant collection "
        "(as opposed to what would be generated from source files).",
    )
    parser.add_argument(
        "--url",
        default=settings.qdrant_url,
        help=f"Qdrant URL. Default: {settings.qdrant_url} (from QDRANT_URL env var).",
    )
    parser.add_argument(
        "--collection",
        default=settings.qdrant_collection,
        help=f"Collection name. Default: {settings.qdrant_collection} (from QDRANT_COLLECTION env var).",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=5,
        help="Number of points to preview. Default: 5.",
    )
    parser.add_argument(
        "--client-name",
        help="Only show points whose client_name payload field contains this substring.",
    )
    parser.add_argument(
        "--preview-chars",
        type=int,
        default=300,
        help="Maximum characters to print for each point's content field. Default: 300.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print output as JSON.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    client = get_qdrant_client(args.url)

    collection_info = client.get_collection(args.collection)

    scroll_filter = None
    if args.client_name:
        from qdrant_client.models import FieldCondition, Filter, MatchText

        scroll_filter = Filter(
            must=[FieldCondition(key="client_name", match=MatchText(text=args.client_name))]
        )

    points, _next_offset = client.scroll(
        collection_name=args.collection,
        scroll_filter=scroll_filter,
        limit=max(args.samples, 1),
        with_payload=True,
        with_vectors=False,
    )

    payload = {
        "url": args.url,
        "collection": args.collection,
        "points_count": collection_info.points_count,
        "vectors_count": collection_info.vectors_count,
        "status": str(collection_info.status),
        "sample_points": [
            {
                "id": point.id,
                "chunk_id": point.payload.get("chunk_id"),
                "fiche_id": point.payload.get("fiche_id"),
                "chunk_type": point.payload.get("chunk_type"),
                "client_name": point.payload.get("client_name"),
                "source_file": point.payload.get("source_file"),
                "content_preview": (point.payload.get("content") or "")[: args.preview_chars].replace("\n", " "),
            }
            for point in points
        ],
    }

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    print(f"URL: {payload['url']}")
    print(f"COLLECTION: {payload['collection']}")
    print(f"POINTS_COUNT: {payload['points_count']}")
    print(f"VECTORS_COUNT: {payload['vectors_count']}")
    print(f"STATUS: {payload['status']}")
    for index, point in enumerate(payload["sample_points"], start=1):
        print(f"--- POINT {index} ---")
        print(f"id: {point['id']}")
        print(f"chunk_id: {point['chunk_id']}")
        print(f"fiche_id: {point['fiche_id']}")
        print(f"chunk_type: {point['chunk_type']}")
        print(f"client_name: {point['client_name']}")
        print(f"source_file: {point['source_file']}")
        print(f"content: {point['content_preview']}")


if __name__ == "__main__":
    main()
