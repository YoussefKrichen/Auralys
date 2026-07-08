from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from schemas.retrieval_schema import RetrievalFilters, RetrievalRoute


class PipelineResponse(BaseModel):
    history_id: int | None = None
    conversation_id: str | None = None
    input_type: str
    original_query: str
    normalized_query: str
    route: RetrievalRoute
    intent: str
    filters: RetrievalFilters
    answer: str
    response_source: str | None = None
    model_output: str | None = None
    llm_error: str | None = None
    token_usage: dict[str, int] = Field(default_factory=dict)
    timings: dict[str, float] = Field(default_factory=dict)
    spoken_text: str | None = None
    hits: list[dict[str, Any]] = Field(default_factory=list)
    relevance_metrics: dict[str, Any] = Field(default_factory=dict)
    reasoning_signals: dict[str, Any] = Field(default_factory=dict)
    reasoning_summary: str | None = None
    sav_admin_analysis: dict[str, Any] = Field(default_factory=dict)
    admin_alert: dict[str, Any] | None = None
    admin_alert_log_path: str | None = None
    transcript: str | None = None
    output_audio_path: str | None = None
