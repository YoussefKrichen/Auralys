from __future__ import annotations

from app.graph.state import GraphState
from app.rag.hybrid_retriever import HybridContext, HybridRetriever


class ContextBuilder:
    def __init__(self, retriever: HybridRetriever) -> None:
        self.retriever = retriever

    def build(self, state: GraphState) -> HybridContext:
        return self.retriever.retrieve(
            request_type=state["request_type"],
            query=state["user_query"],
            client_id=state.get("client_id"),
            diffuseur_id=state.get("diffuseur_id"),
            technicien_id=state.get("technicien_id"),
        )
