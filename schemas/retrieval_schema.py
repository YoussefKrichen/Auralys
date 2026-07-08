from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class QueryIntent(str, Enum):
    semantic = "semantic"
    exact_lookup = "exact_lookup"
    client_lookup = "client_lookup"
    mixed = "mixed"


class RetrievalRoute(str, Enum):
    postgres = "postgres"
    qdrant = "qdrant"
    hybrid = "hybrid"


class RetrievalFilters(BaseModel):
    client: str | None = None
    client_name: str | None = None
    fiche_id: str | None = None
    maintenance_number: str | None = None
    service_type: str | None = None
    chunk_type: str | None = None
    source_file: str | None = None


class RoutedQuery(BaseModel):
    original_query: str
    normalized_query: str
    intent: QueryIntent
    route: RetrievalRoute
    filters: RetrievalFilters = Field(default_factory=RetrievalFilters)


class RetrievalHit(BaseModel):
    chunk_id: str
    fiche_id: str
    score: float
    content: str
    source: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalResult(BaseModel):
    intent: QueryIntent
    query: str
    filters: RetrievalFilters = Field(default_factory=RetrievalFilters)
    hits: list[RetrievalHit] = Field(default_factory=list)


class BuiltContext(BaseModel):
    query: str
    snippets: list[str] = Field(default_factory=list)
    context_text: str = ""
