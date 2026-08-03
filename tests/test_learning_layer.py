from __future__ import annotations

import uuid

import pytest

from app.agent.store import AgentStore
from app.db import default_database
from app.retrieval.hybrid_retriever import _score_hit
from app.review.review_service import ReviewService
from schemas.retrieval_schema import RetrievalHit


def _require_live_postgres():
    try:
        default_database.healthcheck()
    except Exception as exc:  # pragma: no cover - depends on local services
        pytest.skip(f"PostgreSQL non disponible: {exc}")


def test_ceo_correction_flows_from_review_decision_to_active_business_rule():
    """Reproduces the scenario from the CEO: Auralys answers a question about a
    diffuser wrong, the CEO corrects it via the review queue ("Correct" + corrected
    answer), and once the CEO explicitly confirms the resulting memory candidate,
    the correction becomes an active business rule fed into future prompts."""
    _require_live_postgres()
    database = default_database
    database.init_schema()
    store = AgentStore(database=database)
    review_service = ReviewService(database=database)
    conversation_key = f"test:{uuid.uuid4()}"

    # 1. Simulate the original (wrong) answer Auralys gave, as if it came from a
    #    live SAV or CEO chat turn (this is what handle_chat() now persists).
    with database.connection() as connection:
        history_id = database.insert_discussion_history(
            connection,
            {
                "conversation_id": conversation_key,
                "input_type": "text",
                "original_query": "Comment fonctionne le diffuseur X ?",
                "answer": "Le diffuseur X ne possede qu'un seul bouton marche/arret.",
                "intent": "ASK_MAINTENANCE_PROBLEM",
                "route": "ASK_MAINTENANCE_PROBLEM",
            },
        )

    # 2. The CEO corrects it: decision="correct" + corrected_answer. This must not
    #    silently change future answers yet -- only create a PENDING candidate.
    # The text carries a uuid so repeated runs against a persistent live Postgres
    # never collide with a previous run's leftover (now ACTIVE) correction row.
    corrected_text = (
        f"En realite, le diffuseur X a deux boutons ({uuid.uuid4()}): un pour "
        "marche/arret et un second pour regler l'intensite de diffusion."
    )
    review_row = review_service.save_decision(
        history_id=history_id,
        decision="correct",
        reviewed_by="ceo_test",
        corrected_answer=corrected_text,
    )
    assert review_row["review_status"] == "corrected"

    pending_corrections = [
        row
        for row in store.get_active_memory()
        if row["memory_type"] == "KNOWLEDGE_CORRECTION" and row["content"] == corrected_text
    ]
    assert len(pending_corrections) == 1
    memory_id = pending_corrections[0]["id"]
    assert pending_corrections[0]["status"] == "PENDING"

    # 3. Before confirmation, the correction must NOT influence future answers.
    assert corrected_text not in store.get_active_business_rules()

    # 4. The CEO explicitly confirms the correction (separate step, per the
    #    "confirmation requise" decision -- never silent/automatic).
    approved_row = store.approve_memory(memory_id, reviewed_by="ceo_test")
    assert approved_row["status"] == "ACTIVE"

    # 5. Only now does it show up as an active business rule, ready to be folded
    #    into the prompt for the next question about this topic.
    assert corrected_text in store.get_active_business_rules()


def test_ceo_correction_rejected_never_becomes_a_business_rule():
    _require_live_postgres()
    database = default_database
    database.init_schema()
    store = AgentStore(database=database)
    review_service = ReviewService(database=database)
    conversation_key = f"test:{uuid.uuid4()}"

    with database.connection() as connection:
        history_id = database.insert_discussion_history(
            connection,
            {
                "conversation_id": conversation_key,
                "input_type": "text",
                "original_query": "Le diffuseur Y fuit, que faire ?",
                "answer": "Reponse initiale incorrecte.",
                "intent": "ASK_MAINTENANCE_PROBLEM",
                "route": "ASK_MAINTENANCE_PROBLEM",
            },
        )

    corrected_text = f"Correction jamais confirmee {uuid.uuid4()}"
    review_service.save_decision(
        history_id=history_id,
        decision="correct",
        reviewed_by="ceo_test",
        corrected_answer=corrected_text,
    )
    memory_id = next(
        row["id"] for row in store.get_active_memory() if row["content"] == corrected_text
    )

    store.reject_memory(memory_id, reviewed_by="ceo_test")

    assert corrected_text not in store.get_active_business_rules()
    rejected_rows = [row for row in store.database.fetch_active_memories() if row["id"] == memory_id]
    # fetch_active_memories excludes REJECTED rows entirely.
    assert rejected_rows == []


def _fake_hit(chunk_id: str, content: str, *, is_correction: bool) -> RetrievalHit:
    return RetrievalHit(
        chunk_id=chunk_id,
        fiche_id=chunk_id,
        score=0.0,
        content=content,
        source="qdrant",
        metadata={"is_correction": is_correction, "chunk_type": "information"},
    )


def test_ceo_correction_chunk_always_outranks_the_original_knowledge_base_chunk():
    """Even when the original (uncorrected) knowledge_base chunk is a near-perfect
    term/metadata match (maxed out at the 1.0 ceiling), the CEO-approved correction
    on the same topic must still win the ranking."""
    query_terms = ["diffuseur", "x", "boutons"]

    original_hit = _fake_hit("kb:diffuseur_x", "Le diffuseur X boutons marche arret", is_correction=False)
    original_score, _ = _score_hit(
        original_hit,
        query_terms=query_terms,
        rank=1,
        total_hits=2,
        maintenance_like=False,
        retriever="qdrant",
    )

    correction_hit = _fake_hit(
        "ceo_correction:1",
        "Le diffuseur X a deux boutons : marche/arret et intensite",
        is_correction=True,
    )
    correction_score, _ = _score_hit(
        correction_hit,
        query_terms=query_terms,
        rank=2,
        total_hits=2,
        maintenance_like=False,
        retriever="qdrant",
    )

    assert original_score <= 1.0
    assert correction_score > original_score
    assert correction_score > 1.0
