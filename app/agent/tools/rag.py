from __future__ import annotations

from typing import Any

from app.agent.store import AgentStore
from app.agent.tools.base import LoggedTool
from app.retrieval.hybrid_retriever import HybridRetriever


class RAGTool(LoggedTool):
    def __init__(
        self,
        retriever: HybridRetriever | None = None,
        store: AgentStore | None = None,
    ) -> None:
        super().__init__(store=store)
        self.retriever = retriever or HybridRetriever()

    def search_maintenance_files(self, query: str, limit: int = 5) -> dict[str, Any]:
        return self._run_logged(
            "search_maintenance_files",
            {"query": query, "limit": limit},
            lambda: self._search(query, limit),
        )

    def search_client_documents(self, client_name: str, limit: int = 5) -> dict[str, Any]:
        return self._run_logged(
            "search_client_documents",
            {"client_name": client_name, "limit": limit},
            lambda: self._search(f"Client: {client_name}", limit),
        )

    def search_similar_cases(self, problem_description: str, limit: int = 5) -> dict[str, Any]:
        return self._run_logged(
            "search_similar_cases",
            {"problem_description": problem_description, "limit": limit},
            lambda: self._search(problem_description, limit),
        )

    def _search(self, query: str, limit: int) -> dict[str, Any]:
        result = self.retriever.search(query)
        hits = [hit.model_dump(mode="json") for hit in result.hits[:limit]]
        return {"query": result.query, "hits": hits}

