from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from schemas.agent_schema import AgentChatRequest, AgentIntent, ProposedAction, SkillResult


def build_internal_reasoning_protocol(*, mode: str) -> str:
    base_steps = [
        "1. Identifie d'abord les faits fiables disponibles dans les entrees, les outils et le contexte.",
        "2. Separe clairement les faits observes, les deductions prudentes et les informations manquantes.",
        "3. Verifie que chaque recommandation importante repose sur au moins un element concret.",
        "4. Si plusieurs interpretations existent, choisis la plus prudente et signale la limite.",
        "5. Fournis seulement une conclusion utile et concise; ne devoile jamais la chaine de pensee complete.",
    ]
    mode_specific = {
        "rag": [
            "6. Utilise uniquement le contexte de retrieval pour les affirmations factuelles sur les clients, interventions, produits et services.",
            "7. Si le contexte est faible ou incomplet, privilegie une demande de precision plutot qu'une hypothese forte.",
        ],
        "agent": [
            "6. Priorise les resultats d'outils, les sources explicites et les actions verifiees avant toute reformulation.",
            "7. Si une action est bloquee, en attente d'approbation ou incertaine, precise-le sans inventer d'execution reussie.",
        ],
    }
    steps = base_steps + mode_specific.get(mode, [])
    return "Protocole de raisonnement interne:\n" + "\n".join(steps)


def build_agent_reasoning_signals(
    *,
    request: AgentChatRequest,
    intent: AgentIntent,
    skill_result: SkillResult,
    checked_actions: Sequence[ProposedAction],
    response_source: str | None,
) -> dict[str, Any]:
    hits = _extract_hit_count(skill_result.payload)
    sources = _unique_strings(skill_result.sources)
    missing_information = _extract_missing_information(skill_result.payload)
    grounded = bool(sources or hits or skill_result.payload)
    approval_required_count = sum(1 for action in checked_actions if action.requires_approval and action.allowed)
    blocked_action_count = sum(1 for action in checked_actions if not action.allowed)
    allowed_action_count = sum(1 for action in checked_actions if action.allowed)
    return {
        "query": request.message,
        "intent": intent.value,
        "role": request.role,
        "response_source": response_source,
        "reasoning_mode": "tool_augmented_agent",
        "grounding_status": "grounded" if grounded else "ungrounded",
        "source_count": len(sources),
        "sources": sources,
        "evidence_hit_count": hits,
        "context_keys": sorted(str(key) for key in request.context.keys()),
        "image_count": len(request.images),
        "proposed_action_count": len(checked_actions),
        "allowed_action_count": allowed_action_count,
        "approval_required_count": approval_required_count,
        "blocked_action_count": blocked_action_count,
        "skill_confidence": round(max(0.0, min(skill_result.confidence, 1.0)), 2),
        "missing_information": missing_information,
        "payload_keys": sorted(str(key) for key in skill_result.payload.keys()),
    }


def build_agent_reasoning_summary(reasoning_signals: dict[str, Any]) -> str:
    grounding_status = reasoning_signals.get("grounding_status") or "unknown"
    source_count = reasoning_signals.get("source_count", 0)
    evidence_hit_count = reasoning_signals.get("evidence_hit_count", 0)
    proposed_action_count = reasoning_signals.get("proposed_action_count", 0)
    approval_required_count = reasoning_signals.get("approval_required_count", 0)
    skill_confidence = reasoning_signals.get("skill_confidence")
    missing_information = reasoning_signals.get("missing_information") or []
    missing_info_text = ", ".join(str(item) for item in missing_information[:3]) if missing_information else "aucune"
    return (
        f"grounding={grounding_status}; "
        f"sources={source_count}; "
        f"evidence_hits={evidence_hit_count}; "
        f"actions={proposed_action_count}; "
        f"approval_required={approval_required_count}; "
        f"confidence={skill_confidence if skill_confidence is not None else 'n/a'}; "
        f"missing_information={missing_info_text}"
    )


def _extract_hit_count(payload: dict[str, Any]) -> int:
    candidates = (
        payload.get("hits"),
        payload.get("documents"),
        payload.get("similar_cases"),
        payload.get("ranked_destinations"),
        payload.get("history"),
        payload.get("alerts"),
        payload.get("interventions"),
        payload.get("reclamations"),
    )
    for value in candidates:
        if isinstance(value, list):
            return len(value)
    return 0


def _extract_missing_information(payload: dict[str, Any]) -> list[str]:
    value = payload.get("missing_information")
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]


def _unique_strings(values: Sequence[Any]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered
