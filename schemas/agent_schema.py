from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AgentIntent(str, Enum):
    ASK_CLIENT_HISTORY = "ASK_CLIENT_HISTORY"
    ASK_NEXT_SAV_DESTINATION = "ASK_NEXT_SAV_DESTINATION"
    ASK_ROUTE_OPTIMIZATION = "ASK_ROUTE_OPTIMIZATION"
    ASK_ALERTS = "ASK_ALERTS"
    ASK_MAINTENANCE_PROBLEM = "ASK_MAINTENANCE_PROBLEM"
    ASK_DAILY_REPORT = "ASK_DAILY_REPORT"
    ASK_STOCK_STATUS = "ASK_STOCK_STATUS"
    SUBMIT_MAINTENANCE_FICHE = "SUBMIT_MAINTENANCE_FICHE"
    GENERAL_QUESTION = "GENERAL_QUESTION"


class AgentActionStatus(str, Enum):
    ALLOWED = "ALLOWED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"


class ImageAttachment(BaseModel):
    name: str
    media_type: str
    data_url: str


class AgentChatRequest(BaseModel):
    user_id: int
    role: str
    message: str
    conversation_id: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    images: list[ImageAttachment] = Field(default_factory=list)


class AgentFeedbackRequest(BaseModel):
    conversation_key: str
    user_id: int | None = None
    rating: str
    correction: str | None = None
    should_remember: bool = False


class AgentActionDecisionRequest(BaseModel):
    approved_by: int | None = None
    review_note: str | None = None


class ActionPolicyDecision(BaseModel):
    allowed: bool
    requires_approval: bool
    reason: str


class ProposedAction(BaseModel):
    id: int | None = None
    action_type: str
    status: AgentActionStatus = AgentActionStatus.ALLOWED
    requires_approval: bool = False
    allowed: bool = True
    reason: str | None = None
    input_json: dict[str, Any] = Field(default_factory=dict)
    output_json: dict[str, Any] = Field(default_factory=dict)


class Citation(BaseModel):
    index: int
    fiche_id: str | None = None
    maintenance_number: str | None = None
    client: str | None = None
    chunk_type: str | None = None


class SkillResult(BaseModel):
    answer: str
    proposed_actions: list[ProposedAction] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    justification: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class AgentChatResponse(BaseModel):
    conversation_id: str | None = None
    intent: AgentIntent
    answer: str
    spoken_text: str | None = None
    requires_approval: bool
    proposed_actions: list[ProposedAction] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    confidence: float
    justification: str | None = None
    reasoning_signals: dict[str, Any] = Field(default_factory=dict)
    reasoning_summary: str | None = None
