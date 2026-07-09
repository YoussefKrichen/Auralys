from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from app.config import settings


def _sign(body: bytes) -> str:
    signature = hmac.new(settings.session_secret.encode("utf-8"), body, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")


def create_session_token(*, user_id: int, username: str, role: str, display_name: str) -> str:
    payload = {
        "id": user_id,
        "username": username,
        "role": role,
        "display_name": display_name,
        "exp": int(time.time()) + settings.session_ttl_seconds,
    }
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")).rstrip(b"=")
    return f"{body.decode('ascii')}.{_sign(body)}"


def verify_session_token(token: str) -> dict[str, Any] | None:
    try:
        body_b64, signature = token.split(".", 1)
    except ValueError:
        return None
    body = body_b64.encode("ascii")
    if not hmac.compare_digest(_sign(body), signature):
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(body_b64 + "=" * (-len(body_b64) % 4)))
    except (ValueError, json.JSONDecodeError):
        return None
    if payload.get("exp", 0) < time.time():
        return None
    return payload
