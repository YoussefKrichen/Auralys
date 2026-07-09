from __future__ import annotations

from typing import Any

from fastapi import Header, HTTPException

from app.auth.session_token import verify_session_token


def get_current_user(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authentification requise.")
    payload = verify_session_token(authorization.split(" ", 1)[1].strip())
    if payload is None:
        raise HTTPException(status_code=401, detail="Session invalide ou expiree.")
    return payload


def require_ceo(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    current_user = get_current_user(authorization)
    if current_user.get("role") != "ceo":
        raise HTTPException(status_code=403, detail="Reserve a l'espace CEO.")
    return current_user
