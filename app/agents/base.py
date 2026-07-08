from __future__ import annotations

from typing import Any, Protocol

from app.graph.state import GraphState, Priority
from app.services.response_builder import merge_analysis_lists, merge_priority


class LLMClient(Protocol):
    def summarize(self, *, agent_name: str, prompt: str, context: dict[str, Any]) -> str:
        ...


class MockLLMClient:
    def summarize(self, *, agent_name: str, prompt: str, context: dict[str, Any]) -> str:
        context_keys = ", ".join(sorted(context.keys()))
        return f"{agent_name}: {prompt} Contexte={context_keys or 'aucun'}."


class BaseAgent:
    agent_name: str = "Base Agent"
    state_key: str = "analysis"

    def __init__(self, llm: LLMClient | None = None) -> None:
        self.llm = llm or MockLLMClient()

    def __call__(self, state: GraphState) -> dict[str, Any]:
        trace = list(state.get("trace", []))
        if self.agent_name not in state.get("agents_used", []):
            trace.append(f"{self.agent_name}: skipped")
            return {"trace": trace}

        payload = self.analyze(state)
        findings = [str(item) for item in payload.get("findings", [])]
        recommendations = [str(item) for item in payload.get("recommendations", [])]
        next_actions = [str(item) for item in payload.get("next_actions", [])]
        priority: Priority = payload.get("priority", state.get("priority", "medium"))
        requires_human_validation = bool(payload.get("requires_human_validation", False))

        trace.append(f"{self.agent_name}: completed")
        merged = merge_analysis_lists(
            state,
            findings=findings,
            recommendations=recommendations,
            next_actions=next_actions,
        )

        return {
            self.state_key: payload,
            "priority": merge_priority(state.get("priority", "medium"), priority),
            "requires_human_validation": (
                state.get("requires_human_validation", False) or requires_human_validation
            ),
            "trace": trace,
            **merged,
        }

    def analyze(self, state: GraphState) -> dict[str, Any]:
        raise NotImplementedError
