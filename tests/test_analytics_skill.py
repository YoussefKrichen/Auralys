from __future__ import annotations

from app.agent.skills.analytics import AnalyticsSkill
from schemas.agent_schema import AgentChatRequest


class _FakeOperationsDataTool:
    def __init__(self, *, client: dict | None, diffuser_result: dict, recent_clients: dict):
        self._client = client
        self._diffuser_result = diffuser_result
        self._recent_clients = recent_clients
        self.calls: list[str] = []

    def get_client_by_name(self, name: str) -> dict:
        self.calls.append(f"get_client_by_name:{name}")
        if self._client is None:
            raise ValueError(f"Client not found for lookup: {name}")
        return self._client

    def find_client_mentioned_in_text(self, text: str) -> dict | None:
        self.calls.append("find_client_mentioned_in_text")
        return self._client

    def count_client_diffusers(self, client_id: str) -> dict:
        self.calls.append(f"count_client_diffusers:{client_id}")
        return self._diffuser_result

    def list_recent_clients(self, limit: int = 10) -> dict:
        self.calls.append(f"list_recent_clients:{limit}")
        return self._recent_clients


def test_answers_diffuser_count_when_client_resolved():
    tool = _FakeOperationsDataTool(
        client={"client_id": "asteel-flash", "client_name": "Asteel Flash", "address": "Soukra"},
        diffuser_result={
            "client_id": "asteel-flash",
            "diffuser_count": 20,
            "locations": [],
            "raw_visit_count": 67,
            "history": [],
        },
        recent_clients={"clients": []},
    )
    skill = AnalyticsSkill(operations_data_tool=tool)
    request = AgentChatRequest(
        user_id=1, role="sav", message="combien de diffuseurs a le client: Asteel Flash"
    )

    result = skill.run(request)

    assert "20 diffuseur" in result.answer
    assert result.confidence > 0.5
    assert "count_client_diffusers:asteel-flash" in tool.calls


def test_answers_zero_diffusers_with_low_confidence():
    tool = _FakeOperationsDataTool(
        client={"client_id": "finopti", "client_name": "Finopti", "address": "Charguia"},
        diffuser_result={
            "client_id": "finopti",
            "diffuser_count": 0,
            "locations": [],
            "raw_visit_count": 0,
            "history": [],
        },
        recent_clients={"clients": []},
    )
    skill = AnalyticsSkill(operations_data_tool=tool)
    request = AgentChatRequest(user_id=1, role="sav", message="combien de diffuseur a le client: Finopti")

    result = skill.run(request)

    assert "Aucun diffuseur" in result.answer
    assert result.confidence < 0.5


def test_falls_back_to_recent_clients_when_no_client_resolved():
    tool = _FakeOperationsDataTool(
        client=None,
        diffuser_result={},
        recent_clients={
            "clients": [
                {"client_id": "finopti", "client_name": "Finopti", "last_service_date": "2026-06-20", "visit_count": 2},
                {"client_id": "asteel-flash", "client_name": "Asteel Flash", "last_service_date": "2026-03-12", "visit_count": 2},
            ]
        },
    )
    skill = AnalyticsSkill(operations_data_tool=tool)
    request = AgentChatRequest(user_id=1, role="sav", message="quels sont les derniers clients servis ?")

    result = skill.run(request)

    assert "Finopti" in result.answer
    assert "list_recent_clients:10" in tool.calls


def test_recent_clients_list_requested_even_when_a_client_name_is_present():
    tool = _FakeOperationsDataTool(
        client={"client_id": "finopti", "client_name": "Finopti", "address": "Charguia"},
        diffuser_result={"client_id": "finopti", "diffuser_count": 13, "locations": [], "raw_visit_count": 19, "history": []},
        recent_clients={"clients": [{"client_id": "finopti", "client_name": "Finopti", "last_service_date": "2026-06-20", "visit_count": 2}]},
    )
    skill = AnalyticsSkill(operations_data_tool=tool)
    request = AgentChatRequest(user_id=1, role="sav", message="liste des clients servis recemment chez Finopti")

    result = skill.run(request)

    assert "Derniers clients servis" in result.answer


def test_answers_recent_clients_when_no_dated_clients_exist():
    tool = _FakeOperationsDataTool(
        client=None,
        diffuser_result={},
        recent_clients={"clients": []},
    )
    skill = AnalyticsSkill(operations_data_tool=tool)
    request = AgentChatRequest(user_id=1, role="sav", message="liste des clients servis")

    result = skill.run(request)

    assert "Aucun client" in result.answer
    assert result.confidence < 0.5
