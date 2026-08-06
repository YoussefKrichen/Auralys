from __future__ import annotations

import re
from datetime import date

from app.agent.skills.base import Skill
from app.agent.store import AgentStore
from app.agent.tools.kpi_aggregator import (
    compute_kpis,
    format_period_label,
    parse_period_from_text,
    resolve_period_range,
)
from app.agent.tools.operations_data import OperationsDataTool
from app.config import settings
from app.reporting.report_files import generate_report_excel, generate_report_pdf
from schemas.agent_schema import AgentChatRequest, ProposedAction, SkillResult

_FORMAT_RE = {
    "pdf": re.compile(r"\bpdf\b", re.IGNORECASE),
    "excel": re.compile(r"\b(excel|xlsx|xls|tableur)\b", re.IGNORECASE),
}


def parse_format_from_text(text: str) -> str | None:
    for fmt, pattern in _FORMAT_RE.items():
        if pattern.search(text):
            return fmt
    return None


class CEOReportingSkill(Skill):
    def __init__(self, operations_data_tool: OperationsDataTool, store: AgentStore | None = None) -> None:
        self.operations_data_tool = operations_data_tool
        self.store = store or AgentStore()

    def run(self, request: AgentChatRequest) -> SkillResult:
        conversation_key = (
            request.conversation_id
            or str(request.context.get("conversation_id") or "").strip()
            or f"anon:{request.user_id}:{request.role}"
        )
        today = date.today()
        period_match = parse_period_from_text(request.message, today=today)
        report_format = parse_format_from_text(request.message)

        pending = None
        try:
            pending = self.store.get_pending_report(conversation_key)
        except Exception:
            pending = None

        if period_match is not None:
            period, anchor = period_match
        elif pending is not None:
            period, anchor = pending["period"], pending["anchor_date"]
        else:
            period, anchor = "day", today

        if report_format is None:
            return self._ask_for_format(conversation_key, period=period, anchor=anchor)
        return self._generate_report(conversation_key, period=period, anchor=anchor, report_format=report_format)

    def _ask_for_format(self, conversation_key: str, *, period: str, anchor: date) -> SkillResult:
        try:
            self.store.save_pending_report(conversation_key, period=period, anchor_date=anchor)
        except Exception:
            pass
        start, end = resolve_period_range(period, anchor)
        label = format_period_label(period, start, end)
        return SkillResult(
            answer=(
                f"Je peux preparer le rapport pour la periode suivante : {label}. "
                "Voulez-vous ce rapport en PDF ou en Excel ?"
            ),
            sources=["OPERATIONS_INTERVENTIONS"],
            confidence=0.7,
            justification="En attente du format souhaite par l'utilisateur avant de generer le fichier.",
            payload={"period": period, "anchor_date": anchor.isoformat(), "awaiting_format": True},
        )

    def _generate_report(
        self, conversation_key: str, *, period: str, anchor: date, report_format: str
    ) -> SkillResult:
        try:
            self.store.clear_pending_report(conversation_key)
        except Exception:
            pass
        start, end = resolve_period_range(period, anchor)
        try:
            kpis = compute_kpis(settings.gold_data_csv_path, start=start, end=end)
        except FileNotFoundError:
            return SkillResult(
                answer="Je n'arrive pas a acceder aux donnees pour generer ce rapport pour le moment.",
                sources=[],
                confidence=0.2,
                justification="La source de donnees gold est indisponible.",
            )
        label = format_period_label(period, start, end)
        report_meta = {
            "period": period,
            "label": label,
            "range_start": start.isoformat(),
            "range_end": end.isoformat(),
        }
        if report_format == "pdf":
            file_path = generate_report_pdf(kpis, report_meta)
            format_label = "PDF"
        else:
            file_path = generate_report_excel(kpis, report_meta)
            format_label = "Excel"

        download_url = f"/reports/download/{file_path.name}"
        totals = kpis["totals"]
        answer = (
            f"Voici le rapport {format_label} pour {label} : {totals['interventions']} intervention(s) "
            f"chez {totals['clients']} client(s).\n\n"
            f"[Telecharger le rapport {format_label}]({download_url})"
        )
        return SkillResult(
            answer=answer,
            proposed_actions=[
                ProposedAction(
                    action_type="GENERATE_REPORT_DRAFT",
                    input_json={"period": period, "anchor_date": anchor.isoformat(), "format": report_format},
                    output_json={"download_url": download_url, "interventions": totals["interventions"]},
                )
            ],
            sources=["OPERATIONS_INTERVENTIONS", "OPERATIONS_ALERTS"],
            confidence=0.85,
            justification="Rapport genere a partir des KPIs calcules sur la periode demandee.",
            payload={"download_url": download_url, "report": report_meta},
            skip_llm_polish=True,
        )
