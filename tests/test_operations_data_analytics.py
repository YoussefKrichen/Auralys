from __future__ import annotations

from datetime import date

import app.agent.tools.operations_data as operations_data_module
from app.agent.tools.gold_data_source import GoldVisit
from app.agent.tools.operations_data import OperationsDataTool


def _visit(
    *,
    maintenance_number: str,
    client: str,
    address: str | None = "Soukra",
    service_date: date | None = None,
    diffusers: list[dict] | None = None,
) -> GoldVisit:
    return GoldVisit(
        maintenance_number=maintenance_number,
        client=client,
        address=address,
        service_date=service_date,
        diffusers=diffusers or [],
    )


ASTEEL_VISITS = [
    _visit(
        maintenance_number="1",
        client="Asteel Flash",
        service_date=date(2026, 1, 6),
        diffusers=[
            {"model": "Aromair100", "emplacement": "B1 RDC", "quantity_ml": 50},
            {"model": "Aromair100", "emplacement": "B2 couloir", "quantity_ml": 30},
        ],
    ),
    _visit(
        maintenance_number="2",
        client="Asteel flash",  # inconsistent casing across visits, same client
        service_date=date(2026, 3, 12),
        diffusers=[
            {"model": "Aromair100", "emplacement": "BL1RDC", "quantity_ml": 40},  # same as "B1 RDC"
            {"model": "Aromair500", "emplacement": "Bloc 1 RDC", "quantity_ml": 20},  # same again
            {"model": None, "emplacement": None, "quantity_ml": None},
        ],
    ),
]

OTHER_VISITS = [
    _visit(maintenance_number="3", client="Finopti", service_date=date(2026, 5, 1)),
    _visit(maintenance_number="4", client="Finopti", service_date=date(2026, 6, 20)),
    _visit(maintenance_number="5", client="Magro", service_date=None),  # never dated -- must be excluded from ranking
]


def _tool(monkeypatch, visits: list[GoldVisit]) -> OperationsDataTool:
    monkeypatch.setattr(operations_data_module, "load_gold_visits", lambda csv_path: visits)
    return OperationsDataTool(store=None)


def test_count_client_diffusers_dedupes_block_notation_variants(monkeypatch):
    tool = _tool(monkeypatch, ASTEEL_VISITS)

    result = tool.count_client_diffusers("asteel-flash")

    assert result["raw_visit_count"] == 2
    # "B1 RDC" / "BL1RDC" / "Bloc 1 RDC" collapse into one location; "B2 couloir" is separate;
    # the None/None diffuser row contributes nothing countable.
    assert result["diffuser_count"] == 2
    emplacements = {loc["emplacement"] for loc in result["locations"]}
    assert "B2 couloir" in emplacements


def test_count_client_diffusers_returns_zero_for_client_with_no_diffusers(monkeypatch):
    tool = _tool(monkeypatch, OTHER_VISITS)

    result = tool.count_client_diffusers("finopti")

    assert result["diffuser_count"] == 0
    assert result["raw_visit_count"] == 2


def test_list_recent_clients_sorts_by_last_service_date_desc(monkeypatch):
    tool = _tool(monkeypatch, ASTEEL_VISITS + OTHER_VISITS)

    result = tool.list_recent_clients(limit=10)

    names = [row["client_name"] for row in result["clients"]]
    # Finopti's latest visit (2026-06-20) is more recent than Asteel Flash's (2026-03-12).
    assert names[0] == "Finopti"
    assert "Asteel flash" in names or "Asteel Flash" in names


def test_list_recent_clients_excludes_clients_with_no_dated_visits(monkeypatch):
    tool = _tool(monkeypatch, OTHER_VISITS)

    result = tool.list_recent_clients(limit=10)

    names = [row["client_name"] for row in result["clients"]]
    assert "Magro" not in names


def test_list_recent_clients_respects_limit(monkeypatch):
    tool = _tool(monkeypatch, ASTEEL_VISITS + OTHER_VISITS)

    result = tool.list_recent_clients(limit=1)

    assert len(result["clients"]) == 1


def test_find_client_mentioned_in_text_matches_longest_name(monkeypatch):
    tool = _tool(monkeypatch, ASTEEL_VISITS)

    found = tool.find_client_mentioned_in_text("combien de diffuseurs a le client Asteel Flash ?")

    assert found is not None
    assert found["client_id"] == "asteel-flash"


def test_find_client_mentioned_in_text_returns_none_when_no_match(monkeypatch):
    tool = _tool(monkeypatch, ASTEEL_VISITS)

    found = tool.find_client_mentioned_in_text("quel temps fait-il aujourd'hui ?")

    assert found is None


def test_client_id_normalization_merges_accent_and_case_variants(monkeypatch):
    tool = _tool(
        monkeypatch,
        [
            _visit(maintenance_number="10", client="HG Ykone", service_date=date(2026, 1, 1)),
            _visit(maintenance_number="11", client="HG YKONE", service_date=date(2026, 2, 1)),
        ],
    )

    result = tool.list_recent_clients(limit=10)

    assert len(result["clients"]) == 1
    assert result["clients"][0]["visit_count"] == 2
