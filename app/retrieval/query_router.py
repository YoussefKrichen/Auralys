from __future__ import annotations

import re

from schemas.retrieval_schema import QueryIntent, RetrievalFilters, RetrievalRoute, RoutedQuery


MAINTENANCE_NUMBER_RE = re.compile(r"\b0?\d{5,6}\b")
CLIENT_FILTER_RE = re.compile(r"\bclient\s*[:#-]\s*(?P<client>[^,;.\n]+)", re.IGNORECASE)
SOURCE_FILE_FILTER_RE = re.compile(r"\bsource_file\s*[:#-]\s*(?P<source_file>[^,;\n]+)", re.IGNORECASE)
CHUNK_TYPE_FILTER_RE = re.compile(r"\bchunk_type\s*[:#-]\s*(?P<chunk_type>overview|diffuser|recharge|issue)\b", re.IGNORECASE)
QUERY_STOPWORDS = {
    "a",
    "au",
    "aux",
    "avec",
    "bonjour",
    "bonsoir",
    "ce",
    "ces",
    "client",
    "comment",
    "dans",
    "de",
    "des",
    "du",
    "en",
    "est",
    "et",
    "fiche",
    "il",
    "je",
    "la",
    "le",
    "les",
    "mon",
    "pour",
    "que",
    "quel",
    "quelle",
    "quelles",
    "quels",
    "sa",
    "ses",
    "son",
    "sur",
    "un",
    "une",
    "vos",
    "vous",
}


def normalize_query(query: str) -> str:
    return " ".join(query.strip().split())


def route_query(query: str) -> RoutedQuery:
    normalized_query = normalize_query(query)
    filters = RetrievalFilters()
    if match := MAINTENANCE_NUMBER_RE.search(normalized_query):
        filters.maintenance_number = match.group(0)
    if match := CLIENT_FILTER_RE.search(normalized_query):
        filters.client = match.group("client").strip()
        filters.client_name = filters.client
    if match := SOURCE_FILE_FILTER_RE.search(normalized_query):
        filters.source_file = match.group("source_file").strip()
    if match := CHUNK_TYPE_FILTER_RE.search(normalized_query):
        filters.chunk_type = match.group("chunk_type").strip().lower()
    semantic_terms = _extract_semantic_terms(normalized_query, filters)
    has_semantic_need = bool(semantic_terms)

    if filters.maintenance_number and filters.client:
        intent = QueryIntent.mixed
        route = RetrievalRoute.hybrid
    elif filters.maintenance_number and has_semantic_need:
        intent = QueryIntent.mixed
        route = RetrievalRoute.hybrid
    elif filters.maintenance_number:
        intent = QueryIntent.exact_lookup
        route = RetrievalRoute.postgres
    elif filters.client and has_semantic_need:
        intent = QueryIntent.mixed
        route = RetrievalRoute.hybrid
    elif filters.client:
        intent = QueryIntent.client_lookup
        route = RetrievalRoute.postgres
    else:
        intent = QueryIntent.semantic
        route = RetrievalRoute.hybrid
    return RoutedQuery(
        original_query=query,
        normalized_query=normalized_query,
        intent=intent,
        route=route,
        filters=filters,
    )


def _extract_semantic_terms(query: str, filters: RetrievalFilters) -> list[str]:
    query_without_filters = query
    if filters.client:
        query_without_filters = CLIENT_FILTER_RE.sub(" ", query_without_filters)
        for token in re.findall(r"[a-z0-9]{3,}", filters.client.lower()):
            query_without_filters = re.sub(rf"\b{re.escape(token)}\b", " ", query_without_filters, flags=re.IGNORECASE)
    if filters.source_file:
        query_without_filters = SOURCE_FILE_FILTER_RE.sub(" ", query_without_filters)
    if filters.chunk_type:
        query_without_filters = CHUNK_TYPE_FILTER_RE.sub(" ", query_without_filters)
    if filters.maintenance_number:
        query_without_filters = query_without_filters.replace(filters.maintenance_number, " ")

    terms: list[str] = []
    for term in re.findall(r"[a-z0-9]{3,}", query_without_filters.lower()):
        if term in QUERY_STOPWORDS:
            continue
        if term not in terms:
            terms.append(term)
    return terms
