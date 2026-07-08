from __future__ import annotations

import re
from typing import Any

from app.config import settings
from app.db import Database, default_database
from schemas.retrieval_schema import RetrievalFilters, RetrievalHit


STOPWORDS = {
    "a", "au", "aux", "avec", "avant", "client", "comment", "dans", "de", "des", "du",
    "en", "est", "et", "hotel", "je", "la", "le", "les", "mais", "on", "ou", "pour",
    "que", "quel", "quelle", "quels", "quelles", "qui", "sa", "sur", "tu", "un", "une",
    "vocal", "vous",
}
SEARCHABLE_METADATA_FIELDS = (
    "produit",
    "client",
    "client_name",
    "emplacement",
    "address",
    "maintenance_number",
    "model_diffuseur",
    "reference_diffuseur",
    "nom_parfum",
    "parfum",
    "question",
    "knowledge_category",
    "issue",
    "solution",
    "problem_code",
)


class SQLRetriever:
    def __init__(self, database: Database | None = None) -> None:
        self.database = database or default_database

    def search(
        self,
        query: str,
        filters: RetrievalFilters,
        limit: int | None = None,
    ) -> list[RetrievalHit]:
        sql_limit = limit or settings.sql_limit
        requested_limit = sql_limit
        sql_limit = max(sql_limit * 3, sql_limit)
        search_terms = _extract_terms(query)
        filtered_query = " ".join(search_terms)
        clauses = []
        params: dict[str, Any] = {
            "limit": sql_limit,
            "query_like": f"%{query}%",
            "query_text": filtered_query or query,
        }
        if filters.maintenance_number:
            clauses.append("f.maintenance_number = %(maintenance_number)s")
            params["maintenance_number"] = filters.maintenance_number
        resolved_client_name = filters.client_name or filters.client
        if resolved_client_name:
            clauses.append("f.client ILIKE %(client)s")
            params["client"] = f"%{resolved_client_name}%"
        if filters.chunk_type:
            clauses.append("c.chunk_type = %(chunk_type)s")
            params["chunk_type"] = filters.chunk_type
        if filters.source_file:
            clauses.append("f.source_file ILIKE %(source_file)s")
            params["source_file"] = f"%{filters.source_file}%"

        if clauses:
            where_clause = " AND ".join(clauses)
            rank_expr = "1.0"
        else:
            token_clauses = []
            for index, term in enumerate(search_terms):
                key = f"term_{index}"
                params[key] = f"%{term}%"
                metadata_matches = " OR ".join(
                    f"COALESCE(c.metadata->>'{field}', '') ILIKE %({key})s"
                    for field in SEARCHABLE_METADATA_FIELDS
                )
                token_clauses.append(f"(c.content ILIKE %({key})s OR {metadata_matches})")
            if not search_terms:
                return []
            metadata_like_clause = " OR ".join(
                f"COALESCE(c.metadata->>'{field}', '') ILIKE %(query_like)s"
                for field in SEARCHABLE_METADATA_FIELDS
            )
            where_clause = (
                "to_tsvector('simple', c.content) @@ plainto_tsquery('simple', %(query_text)s) "
                f"OR {metadata_like_clause}"
            )
            if token_clauses:
                where_clause = f"({where_clause} OR {' OR '.join(token_clauses)})"
            rank_expr = (
                "ts_rank_cd(to_tsvector('simple', c.content), plainto_tsquery('simple', %(query_text)s))"
            )

        sql = f"""
            SELECT c.chunk_id, c.fiche_id, c.content, c.metadata, f.source_file, {rank_expr} AS rank_score
            FROM chunks c
            JOIN fiches f ON f.fiche_id = c.fiche_id
            WHERE {where_clause}
            ORDER BY rank_score DESC, c.fiche_id, c.ordinal
            LIMIT %(limit)s
        """
        hits: list[RetrievalHit] = []
        with self.database.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                for chunk_id, fiche_id, content, metadata, source_file, rank_score in cursor.fetchall():
                    hits.append(
                        RetrievalHit(
                            chunk_id=chunk_id,
                            fiche_id=fiche_id,
                            score=float(rank_score or 1.0),
                            content=content,
                            source=source_file,
                            metadata={
                                **(metadata or {}),
                                "retriever": "sql",
                                "retrieval_score_raw": float(rank_score or 1.0),
                            },
                        )
                    )
        return hits[:requested_limit]


def _extract_terms(query: str) -> list[str]:
    terms = []
    for term in re.findall(r"[A-Za-z0-9]{3,}", query.lower()):
        if term in STOPWORDS:
            continue
        if term not in terms:
            terms.append(term)
    return terms[:8]
