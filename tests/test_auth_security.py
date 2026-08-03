from __future__ import annotations

import os
import uuid
from types import SimpleNamespace

import pytest

import app.auth.local_auth_service as local_auth_service_module
from app.auth.local_auth_service import LocalAuthService
from app.config import settings
from app.db import default_database


def _require_live_postgres():
    try:
        default_database.healthcheck()
    except Exception as exc:  # pragma: no cover - depends on local services
        pytest.skip(f"PostgreSQL non disponible: {exc}")


class _TrackingDatabase:
    """A database stub with no real users -- records whether it was queried at
    all, so a test can prove the demo-login branch short-circuited before
    ever reaching the DB (vs. falling through to a real, empty lookup)."""

    def __init__(self):
        self.queried = False

    def init_schema(self):
        self.queried = True

    def fetch_user_by_username(self, username):
        self.queried = True
        return None


def test_session_secret_is_not_the_old_hardcoded_default():
    # Regression guard: SESSION_SECRET must never fall back to a fixed, publicly
    # known literal. Either the operator set it explicitly, or config.py must
    # have generated a random one at import time.
    assert settings.session_secret != "dev-insecure-session-secret-change-me"
    assert len(settings.session_secret) >= 16


def test_demo_login_is_disabled_by_default():
    # AURALYS_ALLOW_DEMO_LOGIN is not set in a bare environment, so this must be False.
    if "AURALYS_ALLOW_DEMO_LOGIN" not in os.environ:
        assert settings.allow_demo_login is False


def test_ceo_demo_credentials_rejected_when_demo_login_disabled(monkeypatch):
    monkeypatch.setattr(local_auth_service_module, "settings", SimpleNamespace(allow_demo_login=False))
    database = _TrackingDatabase()
    service = LocalAuthService(database=database)
    assert service.authenticate("ceo", "ceo123") is None
    assert service.authenticate("sav", "sav123") is None
    # Confirms it fell through to a real (empty) DB lookup rather than some other
    # silent bypass -- the rejection comes from "no such user", same as any
    # unregistered username would get.
    assert database.queried is True


def test_ceo_demo_credentials_accepted_when_demo_login_explicitly_enabled(monkeypatch):
    monkeypatch.setattr(local_auth_service_module, "settings", SimpleNamespace(allow_demo_login=True))
    database = _TrackingDatabase()
    service = LocalAuthService(database=database)
    user = service.authenticate("ceo", "ceo123")
    assert user is not None
    assert user["role"] == "ceo"
    # The static branch must short-circuit before ever touching the DB.
    assert database.queried is False


def test_wrong_password_for_demo_account_falls_through_to_db_lookup(monkeypatch):
    monkeypatch.setattr(local_auth_service_module, "settings", SimpleNamespace(allow_demo_login=True))
    database = _TrackingDatabase()
    service = LocalAuthService(database=database)
    # A wrong password for a static account must not be silently accepted --
    # it should fall through to the (real, empty) DB lookup like any other
    # unrecognized login, proving the demo-login gate only widens what's
    # accepted and never weakens the password check itself.
    assert service.authenticate("ceo", "not-the-password") is None
    assert database.queried is True


def test_fetch_conversation_by_key_exposes_owner_for_authorization_checks():
    _require_live_postgres()
    database = default_database
    database.init_schema()
    key = f"test:{uuid.uuid4()}"
    with database.connection() as connection:
        conversation_pk = database.upsert_conversation(
            connection,
            conversation_key=key,
            user_id=4242,
            role="sav",
            channel="chat",
            metadata={},
        )

    conversation = database.fetch_conversation_by_key(key)
    assert conversation is not None
    assert conversation["id"] == conversation_pk
    assert conversation["user_id"] == 4242
    assert conversation["role"] == "sav"
    assert database.fetch_conversation_by_key(f"does-not-exist:{uuid.uuid4()}") is None


def test_fetch_discussion_history_scopes_by_owner_when_user_id_given():
    """Reproduces the IDOR this fixes: without user_id scoping, GET /history
    returned every conversation's discussion_history rows to any logged-in
    user. Two different owners' history must never leak into each other's
    scoped view."""
    _require_live_postgres()
    database = default_database
    database.init_schema()
    owner_a, owner_b = 5001, 5002
    key_a, key_b = f"test:{uuid.uuid4()}", f"test:{uuid.uuid4()}"

    with database.connection() as connection:
        database.upsert_conversation(
            connection, conversation_key=key_a, user_id=owner_a, role="sav", channel="chat", metadata={}
        )
        database.upsert_conversation(
            connection, conversation_key=key_b, user_id=owner_b, role="sav", channel="chat", metadata={}
        )
        history_id_a = database.insert_discussion_history(
            connection,
            {
                "conversation_id": key_a,
                "input_type": "text",
                "original_query": f"Question privee de A {uuid.uuid4()}",
                "answer": "Reponse A",
                "intent": "GENERAL_QUESTION",
                "route": "GENERAL_QUESTION",
            },
        )
        history_id_b = database.insert_discussion_history(
            connection,
            {
                "conversation_id": key_b,
                "input_type": "text",
                "original_query": f"Question privee de B {uuid.uuid4()}",
                "answer": "Reponse B",
                "intent": "GENERAL_QUESTION",
                "route": "GENERAL_QUESTION",
            },
        )

    rows_for_a = database.fetch_discussion_history(limit=500, user_id=owner_a)
    ids_visible_to_a = {row["history_id"] for row in rows_for_a}
    assert history_id_a in ids_visible_to_a
    assert history_id_b not in ids_visible_to_a

    rows_unscoped = database.fetch_discussion_history(limit=500)
    ids_visible_unscoped = {row["history_id"] for row in rows_unscoped}
    assert history_id_a in ids_visible_unscoped
    assert history_id_b in ids_visible_unscoped
