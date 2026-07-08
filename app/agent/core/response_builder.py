from __future__ import annotations

import re
import unicodedata

from app.config import settings
from schemas.agent_schema import AgentChatResponse, AgentIntent, ProposedAction, SkillResult


def build_agent_response(
    *,
    conversation_id: str | None,
    request_message: str,
    intent: AgentIntent,
    skill_result: SkillResult,
    checked_actions: list[ProposedAction],
    reasoning_signals: dict | None = None,
    reasoning_summary: str | None = None,
) -> AgentChatResponse:
    sources: list[str] = []
    for source in skill_result.sources:
        if source not in sources:
            sources.append(source)
    answer = _enforce_agent_identity(request_message, skill_result.answer)
    return AgentChatResponse(
        conversation_id=conversation_id,
        intent=intent,
        answer=answer,
        spoken_text=answer,
        requires_approval=any(action.requires_approval and action.allowed for action in checked_actions),
        proposed_actions=checked_actions,
        sources=sources,
        confidence=max(0.0, min(skill_result.confidence, 1.0)),
        justification=skill_result.justification,
        reasoning_signals=reasoning_signals or {},
        reasoning_summary=reasoning_summary,
    )


def _enforce_agent_identity(request_message: str, fallback_answer: str) -> str:
    normalized = _normalize(request_message)
    identity_markers = (
        "comment tu t appelles",
        "quel est ton nom",
        "c est quoi ton nom",
        "tu t appelles comment",
        "qui es tu",
        "qui est tu",
        "ton nom",
        "your name",
        "who are you",
    )
    if any(marker in normalized for marker in identity_markers):
        return f"Je m'appelle {settings.agent_name}."
    return fallback_answer


def _normalize(value: str) -> str:
    lowered = value.strip().lower()
    ascii_text = unicodedata.normalize("NFKD", lowered).encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^a-z0-9]+", " ", ascii_text)
    return " ".join(cleaned.split())
