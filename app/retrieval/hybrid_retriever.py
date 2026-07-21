from __future__ import annotations

import logging
import re
import unicodedata

from app.retrieval.local_retriever import LocalRetriever
from app.retrieval.qdrant_retriever import QdrantRetriever
from app.retrieval.query_router import route_query
from app.retrieval.sql_retriever import SQLRetriever
from schemas.retrieval_schema import RetrievalHit, RetrievalResult, RetrievalRoute

logger = logging.getLogger(__name__)


class HybridRetriever:
    def __init__(
        self,
        sql_retriever: SQLRetriever | None = None,
        qdrant_retriever: QdrantRetriever | None = None,
        local_retriever: LocalRetriever | None = None,
    ) -> None:
        self.sql_retriever = sql_retriever or SQLRetriever()
        self.qdrant_retriever = qdrant_retriever or QdrantRetriever()
        self.local_retriever = local_retriever or LocalRetriever()

    def search(self, query: str) -> RetrievalResult:
        routed_query = route_query(query)
        ranked: dict[str, RetrievalHit] = {}
        query_terms = _extract_query_terms(routed_query.normalized_query)
        maintenance_like = _is_maintenance_like_query(query_terms)

        def merge_hits(hits: list[RetrievalHit], retriever: str) -> None:
            total_hits = max(len(hits), 1)
            for rank, hit in enumerate(hits, start=1):
                score, breakdown = _score_hit(
                    hit=hit,
                    query_terms=query_terms,
                    rank=rank,
                    total_hits=total_hits,
                    maintenance_like=maintenance_like,
                    retriever=retriever,
                )
                existing = ranked.get(hit.chunk_id)
                if existing is None or score > existing.score:
                    ranked[hit.chunk_id] = hit.model_copy(
                        update={
                            "score": score,
                            "metadata": {
                                **(hit.metadata or {}),
                                "score_breakdown": breakdown,
                            },
                        }
                    )

        if routed_query.route in {RetrievalRoute.postgres, RetrievalRoute.hybrid}:
            try:
                sql_hits = self.sql_retriever.search(routed_query.normalized_query, routed_query.filters)
            except Exception:
                logger.exception("SQL retriever failed for query %r", routed_query.normalized_query)
                sql_hits = []
            merge_hits(sql_hits, "sql")
        if routed_query.route in {RetrievalRoute.qdrant, RetrievalRoute.hybrid}:
            try:
                semantic_hits = self.qdrant_retriever.search(
                    routed_query.normalized_query,
                    routed_query.filters,
                )
            except Exception:
                logger.exception("Qdrant retriever failed for query %r", routed_query.normalized_query)
                semantic_hits = []
            merge_hits(semantic_hits, "qdrant")
        if not ranked:
            try:
                local_hits = self.local_retriever.search(
                    routed_query.normalized_query,
                    routed_query.filters,
                )
            except Exception:
                logger.exception("Local retriever failed for query %r", routed_query.normalized_query)
                local_hits = []
            merge_hits(local_hits, "local")
        hits = sorted(ranked.values(), key=lambda item: item.score, reverse=True)
        return RetrievalResult(
            intent=routed_query.intent,
            query=routed_query.normalized_query,
            filters=routed_query.filters,
            hits=hits,
        )


def _score_hit(
    hit: RetrievalHit,
    query_terms: list[str],
    rank: int,
    total_hits: int,
    maintenance_like: bool,
    retriever: str,
) -> tuple[float, dict[str, float | str]]:
    raw_score = _normalize_raw_score(float(hit.metadata.get("retrieval_score_raw", hit.score)), retriever)
    rank_score = max(0.0, 1.0 - ((rank - 1) / total_hits))

    content_terms = set(_extract_query_terms(hit.content))
    metadata = hit.metadata or {}
    metadata_blob = " ".join(
        str(metadata.get(key) or "")
        for key in (
            "client",
            "maintenance_number",
            "emplacement",
            "address",
            "model_diffuseur",
            "nom_parfum",
            "question",
            "knowledge_category",
        )
    )
    metadata_terms = set(_extract_query_terms(metadata_blob))

    term_overlap = _coverage_score(query_terms, content_terms)
    metadata_overlap = _coverage_score(query_terms, metadata_terms)
    phrase_bonus = 0.0
    normalized_query = " ".join(query_terms)
    normalized_content = _normalize_text(hit.content)
    if normalized_query and normalized_query in normalized_content:
        phrase_bonus += 0.12

    document_type = str(metadata.get("document_type") or "").strip().lower()
    chunk_type = str(metadata.get("chunk_type") or "").strip().lower()

    prior = 0.0
    if document_type == "client_maintenance_form":
        prior += 0.10
    if chunk_type in {"diffuser", "issue", "recharge", "action", "information"}:
        prior += 0.08
    if chunk_type == "overview":
        prior -= 0.06
    if maintenance_like and document_type == "knowledge_base_entry" and metadata_overlap < 0.34:
        prior -= 0.30

    final_score = (
        (raw_score * 0.30)
        + (rank_score * 0.18)
        + (term_overlap * 0.24)
        + (metadata_overlap * 0.20)
        + phrase_bonus
        + prior
    )
    final_score = max(0.0, min(1.0, final_score))
    return final_score, {
        "retriever": retriever,
        "raw_score": round(raw_score, 4),
        "rank_score": round(rank_score, 4),
        "term_overlap": round(term_overlap, 4),
        "metadata_overlap": round(metadata_overlap, 4),
        "phrase_bonus": round(phrase_bonus, 4),
        "prior": round(prior, 4),
        "final_score": round(final_score, 4),
    }


def _normalize_raw_score(score: float, retriever: str) -> float:
    if score <= 0:
        return 0.0
    if retriever in {"sql", "local"}:
        return max(0.0, min(score, 1.0))
    return max(0.0, min((score + 1.0) / 2.0, 1.0))


def _coverage_score(query_terms: list[str], candidate_terms: set[str]) -> float:
    if not query_terms or not candidate_terms:
        return 0.0
    matches = 0.0
    for term in query_terms:
        if term in candidate_terms:
            matches += 1.0
            continue
        if any(term in candidate or candidate in term for candidate in candidate_terms):
            matches += 0.72
    return max(0.0, min(matches / len(query_terms), 1.0))


def _is_maintenance_like_query(query_terms: list[str]) -> bool:
    keywords = {
        "diffuseur",
        "diffusion",
        "fuite",
        "entree",
        "vitrine",
        "recharge",
        "parfum",
        "pompe",
        "bouteille",
        "client",
        "pharmacie",
        "maintenance",
    }
    return any(term in keywords for term in query_terms)


def _normalize_text(text: str) -> str:
    lowered = text.lower()
    ascii_text = unicodedata.normalize("NFKD", lowered).encode("ascii", "ignore").decode("ascii")
    ascii_text = re.sub(r"[^a-z0-9]+", " ", ascii_text)
    return re.sub(r"\s+", " ", ascii_text).strip()


def _extract_query_terms(text: str) -> list[str]:
    stopwords = {
        "a",
        "alors",
        "au",
        "aux",
        "avec",
        "ce",
        "cet",
        "cette",
        "comment",
        "dans",
        "de",
        "des",
        "du",
        "elle",
        "est",
        "et",
        "faire",
        "fonctionne",
        "il",
        "je",
        "la",
        "le",
        "les",
        "mal",
        "plus",
        "pour",
        "que",
        "quoi",
        "qui",
        "sur",
        "un",
        "une",
        "va",
        "veut",
    }
    terms: list[str] = []
    for term in re.findall(r"[a-z0-9]{3,}", _normalize_text(text)):
        if term in stopwords:
            continue
        if term not in terms:
            terms.append(term)
    return terms[:12]
