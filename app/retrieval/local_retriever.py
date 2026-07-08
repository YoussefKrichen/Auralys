from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

from app.config import settings
from app.ingestion.build_chunks import build_chunks
from app.ingestion.normalize import load_fiches_from_directory
from schemas.chunk_schema import ChunkSchema
from schemas.retrieval_schema import RetrievalFilters, RetrievalHit


class LocalRetriever:
    def search(
        self,
        query: str,
        filters: RetrievalFilters,
        limit: int = 8,
    ) -> list[RetrievalHit]:
        query_terms = _extract_terms(query)
        hits: list[tuple[float, ChunkSchema]] = []

        for chunk in _load_cached_chunks():
            metadata = chunk.metadata or {}
            if filters.client:
                client = str(metadata.get("client") or "").casefold()
                if filters.client.casefold() not in client:
                    continue
            if filters.maintenance_number:
                maintenance_number = str(metadata.get("maintenance_number") or "")
                if maintenance_number != filters.maintenance_number:
                    continue

            score = _score_chunk(query_terms, query, chunk)
            if score <= 0:
                continue
            hits.append((score, chunk))

        hits.sort(key=lambda item: item[0], reverse=True)
        output: list[RetrievalHit] = []
        for score, chunk in hits[:limit]:
            output.append(
                RetrievalHit(
                    chunk_id=chunk.chunk_id,
                    fiche_id=chunk.fiche_id,
                    score=score,
                    content=chunk.content,
                    source=chunk.source_file,
                    metadata={
                        "chunk_type": chunk.chunk_type.value,
                        **(chunk.metadata or {}),
                        "retriever": "local",
                        "retrieval_score_raw": score,
                    },
                )
            )
        return output


@lru_cache(maxsize=1)
def _load_cached_chunks() -> tuple[ChunkSchema, ...]:
    fiches = load_fiches_from_directory(settings.processed_data_dir)
    return tuple(build_chunks(fiches))


def _score_chunk(query_terms: list[str], raw_query: str, chunk: ChunkSchema) -> float:
    content_terms = set(_extract_terms(chunk.content))
    metadata_blob = " ".join(str(value) for value in (chunk.metadata or {}).values() if value not in (None, ""))
    metadata_terms = set(_extract_terms(metadata_blob))
    combined_terms = content_terms | metadata_terms
    if not query_terms:
        return 0.0

    matched = 0.0
    for term in query_terms:
        if term in combined_terms:
            matched += 1.0
        elif any(term in candidate or candidate in term for candidate in combined_terms):
            matched += 0.6

    score = matched / len(query_terms)
    normalized_query = _normalize_text(raw_query)
    normalized_content = _normalize_text(chunk.content)
    if normalized_query and normalized_query in normalized_content:
        score += 0.15
    if chunk.chunk_type.value in {"diffuser", "issue", "recharge"}:
        score += 0.08
    return min(score, 1.0)


def _extract_terms(text: str) -> list[str]:
    stopwords = {
        "a",
        "au",
        "aux",
        "avec",
        "client",
        "comment",
        "dans",
        "de",
        "des",
        "du",
        "en",
        "est",
        "et",
        "il",
        "la",
        "le",
        "les",
        "pour",
        "que",
        "qui",
        "sur",
        "une",
        "un",
    }
    terms: list[str] = []
    for term in re.findall(r"[a-z0-9]{3,}", _normalize_text(text)):
        if term in stopwords or term in terms:
            continue
        terms.append(term)
    return terms[:16]


def _normalize_text(text: str) -> str:
    lowered = text.lower()
    ascii_text = unicodedata.normalize("NFKD", lowered).encode("ascii", "ignore").decode("ascii")
    ascii_text = re.sub(r"[^a-z0-9]+", " ", ascii_text)
    return re.sub(r"\s+", " ", ascii_text).strip()
