from __future__ import annotations

from datetime import date

from app.agent.core.orchestrator import AgentOrchestrator
from schemas.agent_schema import AgentChatRequest, AgentIntent


class _ExplodingIntentRouter:
    """Raises if ever called -- proves the pending-report override short-circuits
    the normal intent router instead of relying on it to classify a bare "pdf"."""

    def detect_intent(self, message: str) -> AgentIntent:
        raise AssertionError("intent_router.detect_intent should not be called when a pending report exists")


class _KeywordIntentRouter:
    def detect_intent(self, message: str) -> AgentIntent:
        return AgentIntent.GENERAL_QUESTION


class _FakeStoreWithPending:
    def __init__(self, pending: dict | None) -> None:
        self._pending = pending

    def get_pending_report(self, conversation_key: str):
        return self._pending


def _make_orchestrator(intent_router, store) -> AgentOrchestrator:
    # _resolve_intent only touches self.store / self.intent_router; every other
    # constructor argument is unused by the method under test here.
    return AgentOrchestrator(
        intent_router=intent_router,
        session_manager=None,
        store=store,
        memory_tool=None,
        llm_service=None,
        client_history_skill=None,
        sav_planning_skill=None,
        route_optimization_skill=None,
        alert_management_skill=None,
        maintenance_diagnosis_skill=None,
        ceo_reporting_skill=None,
        general_question_skill=None,
        maintenance_fiche_intake_skill=None,
        analytics_skill=None,
    )


def test_bare_format_reply_routes_to_daily_report_when_a_pending_report_exists():
    orchestrator = _make_orchestrator(
        _ExplodingIntentRouter(),
        _FakeStoreWithPending({"period": "week", "anchor_date": date(2026, 6, 30)}),
    )
    request = AgentChatRequest(user_id=1, role="ceo", message="pdf", conversation_id="conv-1")

    intent = orchestrator._resolve_intent(request, "conv-1")

    assert intent == AgentIntent.ASK_DAILY_REPORT


def test_format_reply_falls_back_to_normal_router_without_a_pending_report():
    orchestrator = _make_orchestrator(_KeywordIntentRouter(), _FakeStoreWithPending(None))
    request = AgentChatRequest(user_id=1, role="ceo", message="pdf", conversation_id="conv-1")

    intent = orchestrator._resolve_intent(request, "conv-1")

    assert intent == AgentIntent.GENERAL_QUESTION


def test_non_format_message_never_triggers_the_override_even_with_a_pending_report():
    orchestrator = _make_orchestrator(
        _KeywordIntentRouter(),
        _FakeStoreWithPending({"period": "week", "anchor_date": date(2026, 6, 30)}),
    )
    request = AgentChatRequest(user_id=1, role="ceo", message="merci beaucoup", conversation_id="conv-1")

    intent = orchestrator._resolve_intent(request, "conv-1")

    assert intent == AgentIntent.GENERAL_QUESTION


def test_conversation_key_is_resolved_and_stamped_before_intent_routing():
    """Regression test for the bug where a brand new conversation's
    pending-report lookup silently missed the state a skill had just saved,
    because the key checked by _resolve_intent was recomputed independently
    from (and could diverge from) the key later persisted for the
    conversation. _resolve_conversation_key must now produce a single stable
    key up front -- even with no client-supplied conversation_id -- and
    _stamp_conversation_key must put that same key on both
    request.conversation_id and request.context["conversation_id"] so every
    downstream step (skills included) agrees on it."""
    request = AgentChatRequest(user_id=1, role="ceo", message="pdf", conversation_id=None)

    resolved_key = AgentOrchestrator._resolve_conversation_key(request)

    assert resolved_key
    assert resolved_key.startswith("agent:1:ceo:")

    stamped = AgentOrchestrator._stamp_conversation_key(request, resolved_key)

    assert stamped.conversation_id == resolved_key
    assert stamped.context["conversation_id"] == resolved_key

    # A second call with an already-matching key is a no-op (same object back).
    assert AgentOrchestrator._stamp_conversation_key(stamped, resolved_key) is stamped
