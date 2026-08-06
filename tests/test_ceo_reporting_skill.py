from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

from app.agent.skills import ceo_reporting as ceo_reporting_module
from app.agent.skills.ceo_reporting import CEOReportingSkill, parse_format_from_text
from schemas.agent_schema import AgentChatRequest

_HEADER = (
    "maintenance_number,client,address,full_name,reference_year,service_date,month,"
    "source,model_diffuseur,emplacement,parfum,qte_restante,qte_livree,commentaire,technician_name"
)

_ROWS = [
    "100,Client A,Lac1,Client A Lac1,2026,2026-06-29,6,Controle,Astree,Salon,RG,10,50,,",
    "101,Client B,Lac2,Client B Lac2,2026,2026-08-04,8,Controle,Astree,Salon,RG,10,50,,",
]


class _FakeOperationsDataTool:
    def get_today_interventions(self) -> dict:
        return {"interventions": [{"client_name": "Client B"}]}

    def get_open_reclamations(self) -> dict:
        return {"reclamations": []}


class _FakePendingReportStore:
    """In-memory stand-in for AgentStore's pending-report methods -- keeps
    these tests independent of a real Postgres connection."""

    def __init__(self) -> None:
        self._rows: dict[str, dict] = {}

    def get_pending_report(self, conversation_key: str):
        return self._rows.get(conversation_key)

    def save_pending_report(self, conversation_key: str, *, period: str, anchor_date) -> None:
        self._rows[conversation_key] = {"period": period, "anchor_date": anchor_date}

    def clear_pending_report(self, conversation_key: str) -> None:
        self._rows.pop(conversation_key, None)


def _write_csv(monkeypatch) -> None:
    csv_path = Path(tempfile.mkdtemp()) / "gold.csv"
    csv_path.write_text(_HEADER + "\n" + "\n".join(_ROWS) + "\n", encoding="utf-8-sig")
    monkeypatch.setattr(
        ceo_reporting_module, "settings", SimpleNamespace(gold_data_csv_path=str(csv_path))
    )


def _skill(store: _FakePendingReportStore | None = None) -> CEOReportingSkill:
    return CEOReportingSkill(operations_data_tool=_FakeOperationsDataTool(), store=store or _FakePendingReportStore())


def test_parse_format_from_text_recognizes_pdf_and_excel_variants():
    assert parse_format_from_text("en PDF stp") == "pdf"
    assert parse_format_from_text("plutot en excel") == "excel"
    assert parse_format_from_text("format xlsx") == "excel"
    assert parse_format_from_text("le rapport de la semaine") is None


def test_period_only_request_asks_for_format_instead_of_generating(monkeypatch):
    _write_csv(monkeypatch)
    store = _FakePendingReportStore()
    skill = _skill(store)
    request = AgentChatRequest(
        user_id=1, role="ceo", message="give me the report of the last week of june 2026", conversation_id="conv-1"
    )

    result = skill.run(request)

    assert "pdf" in result.answer.lower()
    assert "excel" in result.answer.lower()
    assert "juin" in result.answer.lower()
    assert result.payload["awaiting_format"] is True
    assert result.skip_llm_polish is False
    # The period parsed from this message must be remembered for the next turn.
    # parse_period_from_text anchors "last week of june" to june's last day (30th);
    # resolve_period_range then walks that back to the week's Monday (the 29th).
    assert store.get_pending_report("conv-1") == {"period": "week", "anchor_date": ceo_reporting_module.date(2026, 6, 30)}


def test_format_only_followup_generates_the_pending_report(monkeypatch):
    _write_csv(monkeypatch)
    store = _FakePendingReportStore()
    store.save_pending_report("conv-1", period="week", anchor_date=ceo_reporting_module.date(2026, 6, 29))
    skill = _skill(store)
    request = AgentChatRequest(user_id=1, role="ceo", message="pdf", conversation_id="conv-1")

    result = skill.run(request)

    assert result.skip_llm_polish is True
    assert "[Telecharger le rapport PDF]" in result.answer
    assert "1 intervention(s)" in result.answer
    assert result.payload["report"]["period"] == "week"
    assert result.payload["report"]["range_start"] == "2026-06-29"
    assert result.proposed_actions[0].action_type == "GENERATE_REPORT_DRAFT"
    assert result.proposed_actions[0].output_json["download_url"].startswith("/reports/download/")
    # The pending state must be cleared once the report is actually generated.
    assert store.get_pending_report("conv-1") is None


def test_one_shot_message_with_period_and_format_skips_the_question(monkeypatch):
    _write_csv(monkeypatch)
    store = _FakePendingReportStore()
    skill = _skill(store)
    request = AgentChatRequest(
        user_id=1, role="ceo", message="rapport de la semaine du 29/06/2026 en excel", conversation_id="conv-2"
    )

    result = skill.run(request)

    assert result.skip_llm_polish is True
    assert "[Telecharger le rapport Excel]" in result.answer
    assert store.get_pending_report("conv-2") is None


def test_unscoped_message_with_no_pending_state_defaults_to_today_and_still_asks_format(monkeypatch):
    _write_csv(monkeypatch)
    skill = _skill()
    request = AgentChatRequest(user_id=1, role="ceo", message="bonjour, qui es-tu ?", conversation_id="conv-3")

    result = skill.run(request)

    assert result.payload["awaiting_format"] is True
    assert result.payload["period"] == "day"
