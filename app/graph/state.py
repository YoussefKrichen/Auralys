from __future__ import annotations

from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field


Priority = Literal["low", "medium", "high", "critical"]


class ContextDocument(BaseModel):
    document_id: str
    collection: str
    score: float | None = None
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class InvokeRequest(BaseModel):
    user_query: str
    request_type: str | None = None
    client_id: int | None = None
    diffuseur_id: int | None = None
    technicien_id: int | None = None
    document_id: str | None = None


class InvokeResponse(BaseModel):
    request_type: str
    agents_used: list[str] = Field(default_factory=list)
    summary: str
    findings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    priority: Priority
    requires_human_validation: bool
    next_actions: list[str] = Field(default_factory=list)
    trace: list[str] = Field(default_factory=list)


class DocumentIndexItem(BaseModel):
    document_id: str
    title: str
    text: str
    source_type: str = "document"
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentsIndexRequest(BaseModel):
    documents: list[DocumentIndexItem]
    collection: Literal["auralys_documents", "auralys_memory"] = "auralys_documents"


class DocumentsIndexResponse(BaseModel):
    collection: str
    indexed_count: int


class RecommendationValidationRequest(BaseModel):
    recommendations: list[str]
    priority: Priority = "medium"
    findings: list[str] = Field(default_factory=list)
    trace: list[str] = Field(default_factory=list)


class RecommendationValidationResponse(BaseModel):
    validated_recommendations: list[str]
    requires_human_validation: bool
    trace: list[str] = Field(default_factory=list)


class GraphState(TypedDict, total=False):
    user_query: str
    request_type: str
    client_id: int | None
    diffuseur_id: int | None
    technicien_id: int | None
    document_id: str | None
    sql_context: dict[str, Any]
    vector_context: list[dict[str, Any]]
    agents_used: list[str]
    sav_analysis: dict[str, Any]
    client_analysis: dict[str, Any]
    diffuseur_analysis: dict[str, Any]
    technicien_analysis: dict[str, Any]
    document_analysis: dict[str, Any]
    recommendation_analysis: dict[str, Any]
    recommendations: list[str]
    report: dict[str, Any]
    priority: Priority
    requires_human_validation: bool
    next_actions: list[str]
    final_answer: dict[str, Any]
    trace: list[str]
    findings: list[str]
    summary: str


def initial_state(request: InvokeRequest) -> GraphState:
    return {
        "user_query": request.user_query,
        "request_type": request.request_type or "",
        "client_id": request.client_id,
        "diffuseur_id": request.diffuseur_id,
        "technicien_id": request.technicien_id,
        "document_id": request.document_id,
        "sql_context": {},
        "vector_context": [],
        "agents_used": [],
        "sav_analysis": {},
        "client_analysis": {},
        "diffuseur_analysis": {},
        "technicien_analysis": {},
        "document_analysis": {},
        "recommendation_analysis": {},
        "recommendations": [],
        "report": {},
        "priority": "medium",
        "requires_human_validation": False,
        "next_actions": [],
        "final_answer": {},
        "trace": [],
        "findings": [],
        "summary": "",
    }
