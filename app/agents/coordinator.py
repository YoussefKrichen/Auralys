from __future__ import annotations

from app.agents.base import LLMClient, MockLLMClient
from app.graph.router import IntentRouter
from app.graph.state import GraphState
from app.services.context_builder import ContextBuilder


class CoordinatorAgent:
    def __init__(
        self,
        router: IntentRouter,
        context_builder: ContextBuilder,
        llm: LLMClient | None = None,
    ) -> None:
        self.router = router
        self.context_builder = context_builder
        self.llm = llm or MockLLMClient()

    def __call__(self, state: GraphState) -> dict[str, object]:
        request_type = self.router.classify(
            query=state["user_query"],
            requested_type=state.get("request_type") or None,
        )
        agents_used = self.router.select_agents(
            request_type=request_type,
            document_id=state.get("document_id"),
        )
        context = self.context_builder.build({**state, "request_type": request_type})
        priority = self.router.infer_priority(state["user_query"])
        summary = self.llm.summarize(
            agent_name="Coordinator Agent",
            prompt="Classification, contextualisation et routage termines.",
            context={
                "request_type": request_type,
                "sources": context.sources,
                "agents_used": agents_used,
            },
        )

        trace = list(state.get("trace", []))
        trace.append(f"Coordinator Agent: request_type={request_type}")
        trace.append(f"Coordinator Agent: sources={','.join(context.sources) or 'none'}")
        trace.append(f"Coordinator Agent: agents={','.join(agents_used)}")

        return {
            "request_type": request_type,
            "agents_used": agents_used,
            "sql_context": context.sql_context,
            "vector_context": context.vector_context,
            "priority": priority,
            "summary": summary,
            "trace": trace,
        }
