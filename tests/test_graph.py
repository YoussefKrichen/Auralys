from app.agents import (
    ClientAgent,
    CoordinatorAgent,
    DocumentsAgent,
    RecommendationAgent,
    ReportLearningAgent,
    SAVAgent,
)
from app.agents.base import MockLLMClient
from app.graph.graph_builder import AuralysGraphService, GraphNodes
from app.graph.router import IntentRouter
from app.graph.state import InvokeRequest
from app.services.context_builder import ContextBuilder
from app.services.response_builder import ResponseBuilder


class _FakeHybridRetriever:
    def retrieve(self, *, request_type, query, client_id=None, diffuseur_id=None, technicien_id=None):
        return type(
            "HybridContext",
            (),
            {
                "sql_context": {
                    "clients": [
                        {
                            "id": client_id or 1,
                            "name": "Pharmacie du Centre",
                            "segment": "pharmacie",
                            "city": "Paris",
                            "status": "active",
                            "notes": "demo",
                        }
                    ],
                    "diffuseurs": [],
                    "techniciens": [],
                    "interventions": [
                        {
                            "id": 1,
                            "client_id": client_id or 1,
                            "diffuseur_id": diffuseur_id or 1,
                            "technicien_id": technicien_id,
                            "status": "open",
                            "priority": "high",
                            "scheduled_at": None,
                            "summary": "Verifier la pompe",
                        }
                    ],
                    "reclamations": [
                        {
                            "id": 1,
                            "client_id": client_id or 1,
                            "intervention_id": 1,
                            "status": "open",
                            "severity": "critical",
                            "description": "Arret du diffuseur",
                        }
                    ],
                    "recommendations": [],
                },
                "vector_context": [
                    {
                        "document_id": "doc-1",
                        "collection": "auralys_documents",
                        "score": 0.98,
                        "content": "Fiche maintenance avec symptomes de pompe.",
                        "metadata": {"title": "Fiche maintenance demo"},
                    }
                ],
                "sources": ["postgres", "qdrant"],
            },
        )()


def _build_graph_service() -> AuralysGraphService:
    llm = MockLLMClient()
    router = IntentRouter()
    context_builder = ContextBuilder(retriever=_FakeHybridRetriever())
    return AuralysGraphService(
        nodes=GraphNodes(
            coordinator=CoordinatorAgent(router=router, context_builder=context_builder, llm=llm),
            sav_agent=SAVAgent(llm=llm),
            client_agent=ClientAgent(llm=llm),
            diffuseur_agent=DocumentsAgent(llm=llm),
            technicien_agent=DocumentsAgent(llm=llm),
            documents_agent=DocumentsAgent(llm=llm),
            recommendation_agent=RecommendationAgent(llm=llm),
            report_learning_agent=ReportLearningAgent(llm=llm),
            response_builder=ResponseBuilder(),
        )
    )


def test_router_classifies_and_selects_agents():
    router = IntentRouter()

    request_type = router.classify(query="Analyse le document de maintenance du diffuseur", requested_type=None)

    assert request_type == "document_analysis"
    assert "Documents Agent" in router.select_agents(request_type=request_type, document_id="doc-1")


def test_langgraph_returns_structured_response():
    graph_service = _build_graph_service()

    response = graph_service.invoke(
        InvokeRequest(
            user_query="Le client 1 a une reclamation urgente sur son diffuseur",
            client_id=1,
            diffuseur_id=1,
        )
    )

    assert response.request_type == "sav_analysis"
    assert "SAV Agent" in response.agents_used
    assert response.priority in {"high", "critical"}
    assert response.trace
