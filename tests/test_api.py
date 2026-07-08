import pytest
from fastapi.testclient import TestClient

from app.graph.state import InvokeRequest, InvokeResponse
from app.main import create_app
from app.services.validation_service import ValidationService
from app.db.postgres import PostgresDatabase
from app.vectorstore.qdrant_client import QdrantGateway


class _FakeGraphService:
    def invoke(self, request: InvokeRequest) -> InvokeResponse:
        return InvokeResponse(
            request_type=request.request_type or "sav_analysis",
            agents_used=["Coordinator Agent", "SAV Agent", "Recommendation Agent"],
            summary="Resume de test.",
            findings=["Une reclamation ouverte a ete detectee."],
            recommendations=["Planifier une verification sur site."],
            priority="high",
            requires_human_validation=True,
            next_actions=["Contacter le technicien de garde."],
            trace=["Coordinator Agent: request_type=sav_analysis"],
        )


class _FakeContainer:
    def __init__(self) -> None:
        self.graph_service = _FakeGraphService()
        self.validation_service = ValidationService()

    def healthcheck(self) -> dict:
        return {"status": "ok", "postgres": {"status": "ok"}, "qdrant": {"status": "ok"}}

    def index_documents(self, request):
        return {"collection": request.collection, "indexed_count": len(request.documents)}


def test_invoke_endpoint_returns_expected_shape():
    client = TestClient(create_app(container=_FakeContainer()))

    response = client.post(
        "/api/auralys/invoke",
        json={
            "user_query": "Client en panne",
            "client_id": 1,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["request_type"] == "sav_analysis"
    assert payload["agents_used"]
    assert payload["priority"] == "high"
    assert payload["requires_human_validation"] is True


def test_documents_index_and_validation_endpoints():
    client = TestClient(create_app(container=_FakeContainer()))

    index_response = client.post(
        "/api/auralys/documents/index",
        json={
            "collection": "auralys_documents",
            "documents": [
                {
                    "document_id": "doc-1",
                    "title": "Rapport",
                    "text": "Contenu",
                    "source_type": "report",
                    "metadata": {"client_id": 1},
                }
            ],
        },
    )
    validate_response = client.post(
        "/api/auralys/recommendations/validate",
        json={
            "recommendations": ["Verifier la pompe"],
            "priority": "high",
            "findings": ["verifier le debit"],
        },
    )

    assert index_response.status_code == 200
    assert index_response.json()["indexed_count"] == 1
    assert validate_response.status_code == 200
    assert validate_response.json()["requires_human_validation"] is True


def test_postgres_connection():
    database = PostgresDatabase()
    try:
        payload = database.healthcheck()
    except Exception as exc:  # pragma: no cover - depends on local services
        pytest.skip(f"PostgreSQL non disponible: {exc}")
    assert payload["status"] == "ok"


def test_qdrant_connection():
    gateway = QdrantGateway(url="http://localhost:6333")
    try:
        payload = gateway.healthcheck()
    except Exception as exc:  # pragma: no cover - depends on local services
        pytest.skip(f"Qdrant non disponible: {exc}")
    assert payload["status"] == "ok"
