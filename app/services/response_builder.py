from __future__ import annotations

from typing import Any

from app.graph.state import GraphState, InvokeResponse, Priority


PRIORITY_ORDER: dict[Priority, int] = {
    "low": 0,
    "medium": 1,
    "high": 2,
    "critical": 3,
}


def _unique_texts(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        cleaned = value.strip()
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique_values.append(cleaned)
    return unique_values


class ResponseBuilder:
    def build(self, state: GraphState) -> InvokeResponse:
        analyses = [
            state.get("sav_analysis", {}),
            state.get("client_analysis", {}),
            state.get("diffuseur_analysis", {}),
            state.get("technicien_analysis", {}),
            state.get("document_analysis", {}),
            state.get("recommendation_analysis", {}),
            state.get("report", {}),
        ]

        findings: list[str] = list(state.get("findings", []))
        recommendations: list[str] = list(state.get("recommendations", []))
        next_actions: list[str] = list(state.get("next_actions", []))
        summary_parts: list[str] = []
        priority = state.get("priority", "medium")
        requires_human_validation = state.get("requires_human_validation", False)

        for analysis in analyses:
            if not analysis:
                continue
            summary = analysis.get("summary")
            if summary:
                summary_parts.append(str(summary))
            findings.extend(str(item) for item in analysis.get("findings", []))
            recommendations.extend(str(item) for item in analysis.get("recommendations", []))
            next_actions.extend(str(item) for item in analysis.get("next_actions", []))
            analysis_priority = analysis.get("priority")
            if analysis_priority and PRIORITY_ORDER[analysis_priority] > PRIORITY_ORDER[priority]:
                priority = analysis_priority
            requires_human_validation = (
                requires_human_validation
                or bool(analysis.get("requires_human_validation"))
            )

        findings = _unique_texts(findings)
        recommendations = _unique_texts(recommendations)
        next_actions = _unique_texts(next_actions)
        summary = " ".join(_unique_texts(summary_parts)) or "Aucune analyse exploitable n'a ete produite."
        requires_human_validation = requires_human_validation or priority in {"high", "critical"}

        return InvokeResponse(
            request_type=state["request_type"],
            agents_used=state.get("agents_used", []),
            summary=summary,
            findings=findings,
            recommendations=recommendations,
            priority=priority,
            requires_human_validation=requires_human_validation,
            next_actions=next_actions,
            trace=state.get("trace", []),
        )


def merge_priority(current: Priority, candidate: Priority) -> Priority:
    return current if PRIORITY_ORDER[current] >= PRIORITY_ORDER[candidate] else candidate


def merge_analysis_lists(
    state: GraphState,
    *,
    findings: list[str],
    recommendations: list[str],
    next_actions: list[str],
) -> dict[str, Any]:
    return {
        "findings": _unique_texts([*state.get("findings", []), *findings]),
        "recommendations": _unique_texts([*state.get("recommendations", []), *recommendations]),
        "next_actions": _unique_texts([*state.get("next_actions", []), *next_actions]),
    }
