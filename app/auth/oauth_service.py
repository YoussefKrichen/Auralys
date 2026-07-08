from __future__ import annotations

import base64
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.config import settings


@dataclass(frozen=True)
class OAuthUser:
    username: str
    role: str
    display_name: str
    provider: str
    email: str


class OAuthService:
    def __init__(self) -> None:
        self._pending_states: dict[str, tuple[str, float]] = {}

    def provider_status(self) -> dict[str, dict[str, bool]]:
        return {
            "google": {"configured": bool(settings.google_oauth_client_id and settings.google_oauth_client_secret)},
            "facebook": {"configured": bool(settings.facebook_oauth_client_id and settings.facebook_oauth_client_secret)},
        }

    def build_start_url(self, provider: str) -> str:
        normalized_provider = provider.strip().lower()
        state = self._create_state(normalized_provider)
        if normalized_provider == "google":
            if not self.provider_status()["google"]["configured"]:
                raise ValueError("Google authentication is not configured.")
            return (
                "https://accounts.google.com/o/oauth2/v2/auth?"
                + urlencode(
                    {
                        "client_id": settings.google_oauth_client_id,
                        "redirect_uri": self._callback_url("google"),
                        "response_type": "code",
                        "scope": "openid email profile",
                        "state": state,
                    }
                )
            )
        if normalized_provider == "facebook":
            if not self.provider_status()["facebook"]["configured"]:
                raise ValueError("Facebook authentication is not configured.")
            return (
                "https://www.facebook.com/dialog/oauth?"
                + urlencode(
                    {
                        "client_id": settings.facebook_oauth_client_id,
                        "redirect_uri": self._callback_url("facebook"),
                        "response_type": "code",
                        "scope": "email,public_profile",
                        "state": state,
                    }
                )
            )
        raise ValueError("Unsupported OAuth provider.")

    def exchange_code(self, provider: str, code: str, state: str) -> OAuthUser:
        normalized_provider = provider.strip().lower()
        self._consume_state(normalized_provider, state)
        if normalized_provider == "google":
            return self._exchange_google_code(code)
        if normalized_provider == "facebook":
            return self._exchange_facebook_code(code)
        raise ValueError("Unsupported OAuth provider.")

    def build_frontend_redirect_url(self, *, session: OAuthUser | None = None, error: str | None = None) -> str:
        base_url = settings.frontend_public_url.rstrip("/") + "/"
        if error:
            return f"{base_url}?auth_error={urlencode({'message': error})[8:]}"
        if session is None:
            return base_url
        payload = base64.urlsafe_b64encode(
            json.dumps(
                {
                    "username": session.username,
                    "role": session.role,
                    "display_name": session.display_name,
                    "provider": session.provider,
                    "email": session.email,
                },
                separators=(",", ":"),
            ).encode("utf-8")
        ).decode("ascii")
        return f"{base_url}?auth_session={payload}"

    def _callback_url(self, provider: str) -> str:
        return f"{settings.backend_public_url.rstrip('/')}/auth/{provider}/callback"

    def _create_state(self, provider: str) -> str:
        self._cleanup_states()
        state = secrets.token_urlsafe(24)
        self._pending_states[state] = (provider, time.time())
        return state

    def _consume_state(self, provider: str, state: str) -> None:
        record = self._pending_states.pop(state, None)
        if record is None:
            raise ValueError("OAuth state is invalid or expired.")
        stored_provider, created_at = record
        if stored_provider != provider:
            raise ValueError("OAuth provider mismatch.")
        if time.time() - created_at > 600:
            raise ValueError("OAuth state has expired.")

    def _cleanup_states(self) -> None:
        now = time.time()
        expired = [state for state, (_, created_at) in self._pending_states.items() if now - created_at > 600]
        for state in expired:
            self._pending_states.pop(state, None)

    def _exchange_google_code(self, code: str) -> OAuthUser:
        token_payload = self._post_form(
            "https://oauth2.googleapis.com/token",
            {
                "client_id": settings.google_oauth_client_id,
                "client_secret": settings.google_oauth_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": self._callback_url("google"),
            },
        )
        access_token = token_payload.get("access_token")
        if not access_token:
            raise ValueError("Google token exchange did not return an access token.")
        profile = self._get_json(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        return self._build_user("google", profile)

    def _exchange_facebook_code(self, code: str) -> OAuthUser:
        token_url = (
            "https://graph.facebook.com/oauth/access_token?"
            + urlencode(
                {
                    "client_id": settings.facebook_oauth_client_id,
                    "client_secret": settings.facebook_oauth_client_secret,
                    "redirect_uri": self._callback_url("facebook"),
                    "code": code,
                }
            )
        )
        token_payload = self._get_json(token_url)
        access_token = token_payload.get("access_token")
        if not access_token:
            raise ValueError("Facebook token exchange did not return an access token.")
        profile = self._get_json(
            "https://graph.facebook.com/me?"
            + urlencode({"fields": "id,name,email", "access_token": access_token})
        )
        return self._build_user("facebook", profile)

    def _build_user(self, provider: str, profile: dict[str, Any]) -> OAuthUser:
        email = str(profile.get("email") or "").strip().lower()
        if not email:
            raise ValueError(f"{provider.title()} did not return an email address for this account.")
        role = self._resolve_role(email)
        if role is None:
            raise ValueError("This email address is not allowed to access Auralys.")
        display_name = str(profile.get("name") or email.split("@", 1)[0]).strip()
        return OAuthUser(
            username=email,
            role=role,
            display_name=display_name,
            provider=provider,
            email=email,
        )

    def _resolve_role(self, email: str) -> str | None:
        normalized_email = email.strip().lower()
        if normalized_email in settings.oauth_ceo_emails:
            return "ceo"
        if normalized_email in settings.oauth_sav_emails:
            return "sav"
        domain = normalized_email.split("@", 1)[1] if "@" in normalized_email else ""
        if settings.oauth_allowed_email_domains and domain in settings.oauth_allowed_email_domains:
            return settings.oauth_default_role if settings.oauth_default_role in {"sav", "ceo"} else "sav"
        if not settings.oauth_ceo_emails and not settings.oauth_sav_emails and not settings.oauth_allowed_email_domains:
            return settings.oauth_default_role if settings.oauth_default_role in {"sav", "ceo"} else "sav"
        return None

    @staticmethod
    def _post_form(url: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = urlencode(payload).encode("utf-8")
        request = Request(url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    @staticmethod
    def _get_json(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
        request = Request(url, headers=headers or {})
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
