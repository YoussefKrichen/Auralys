from __future__ import annotations

import uuid

import pytest

from app.agent.store import AgentStore
from app.db import default_database
from app.history.history_service import HistoryService
from app.review.review_service import ReviewService
from schemas.agent_schema import AgentActionStatus, ProposedAction


def _require_live_postgres():
    try:
        default_database.healthcheck()
    except Exception as exc:  # pragma: no cover - depends on local services
        pytest.skip(f"PostgreSQL non disponible: {exc}")


def test_agent_store_conversation_action_and_memory_round_trip():
    _require_live_postgres()
    store = AgentStore(database=default_database)
    unique_key = f"test:{uuid.uuid4()}"

    conversation_id, conversation_key = store.save_conversation(
        user_id=1,
        role="sav",
        message="Message de test",
        answer="Reponse de test",
        intent="GENERAL_QUESTION",
        conversation_key=unique_key,
    )
    assert conversation_key == unique_key
    assert isinstance(conversation_id, int)

    action = ProposedAction(
        id=None,
        action_type="TEST_ACTION",
        status=AgentActionStatus.PENDING_APPROVAL,
        requires_approval=True,
        input_json={},
        output_json={},
    )
    action_id = store.save_action(conversation_id, action)

    pending = store.list_pending_actions()
    assert any(row["id"] == action_id for row in pending)

    updated = store.update_action_status(action_id=action_id, status="APPROVED", approved_by=42)
    assert updated["status"] == "APPROVED"
    assert updated["approved_by"] == 42

    memory_content = f"Regle de test {uuid.uuid4()}"
    memory_id = store.save_memory(memory_type="BUSINESS_RULE", content=memory_content, source="test_suite")
    active_memory = store.get_active_memory()
    assert any(row["id"] == memory_id and row["content"] == memory_content for row in active_memory)


def test_history_service_conversations_and_messages_round_trip():
    _require_live_postgres()
    store = AgentStore(database=default_database)
    history_service = HistoryService(database=default_database)
    unique_key = f"test:{uuid.uuid4()}"

    _, conversation_key = store.save_conversation(
        user_id=2,
        role="ceo",
        message="Question historique",
        answer="Reponse historique",
        intent="ASK_DAILY_REPORT",
        conversation_key=unique_key,
    )

    conversations = history_service.list_conversations(limit=200, role="ceo", user_id=2)
    assert any(row["conversation_key"] == conversation_key for row in conversations)

    messages = history_service.list_messages(conversation_key=conversation_key, limit=10)
    senders = {message["sender"] for message in messages}
    assert senders == {"user", "assistant"}


def test_review_service_decision_round_trip():
    _require_live_postgres()
    database = default_database
    database.init_schema()
    conversation_id_str = f"test:{uuid.uuid4()}"

    with database.connection() as connection:
        history_id = database.insert_discussion_history(
            connection,
            {
                "conversation_id": conversation_id_str,
                "input_type": "text",
                "original_query": "Question de revue",
                "answer": "Reponse a revoir",
                "intent": "GENERAL_QUESTION",
                "route": "hybrid",
            },
        )

    review_service = ReviewService(database=database)
    reviews = review_service.list_reviews(limit=200, status="all")
    assert any(row["history_id"] == history_id and row["review_status"] == "pending" for row in reviews)

    updated_row = review_service.save_decision(
        history_id=history_id,
        decision="approve",
        reviewed_by="test_suite",
        review_notes="OK",
    )
    assert updated_row["history_id"] == history_id
    assert updated_row["review_status"] == "approved"
