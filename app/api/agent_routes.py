from __future__ import annotations

import json
import logging
import tempfile
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

from app.auth.dependencies import get_current_user, require_ceo
from app.auth.oauth_service import OAuthService
from app.auth.session_token import create_session_token
from app.bootstrap import AppContainer
from app.config import settings
from schemas.agent_schema import (
    AgentActionDecisionRequest,
    AgentChatRequest,
    AgentChatResponse,
    AgentFeedbackRequest,
    AgentIntent,
)

router = APIRouter()
logger = logging.getLogger(__name__)


class ReviewDecisionRequest(BaseModel):
    decision: str
    reviewed_by: str | None = None
    review_notes: str | None = None
    corrected_answer: str | None = None
    knowledge_action: str | None = None


class SpeakRequest(BaseModel):
    text: str


class LocalLoginRequest(BaseModel):
    username: str
    password: str


def get_container() -> AppContainer:
    return AppContainer()


# --- health -----------------------------------------------------------------


@router.get("/health")
def health(container: AppContainer = Depends(get_container)) -> dict[str, Any]:
    try:
        with container.database.connection():
            pass
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "degraded", "postgres_error": str(exc)}


# --- auth (local username/password + OAuth) ----------------------------------


@router.post("/auth/login")
def auth_login(request: LocalLoginRequest, container: AppContainer = Depends(get_container)) -> dict[str, Any]:
    from app.auth.local_auth_service import LocalAuthService

    session = LocalAuthService(database=container.database).authenticate(request.username, request.password)
    if session is None:
        raise HTTPException(status_code=401, detail="Identifiants invalides.")
    session["token"] = create_session_token(
        user_id=session["id"],
        username=session["username"],
        role=session["role"],
        display_name=session["display_name"],
    )
    return session


@router.get("/auth/providers")
def auth_providers() -> dict[str, Any]:
    return {"providers": OAuthService().provider_status()}


@router.get("/auth/{provider}/start")
def auth_start(provider: str) -> RedirectResponse:
    try:
        url = OAuthService().build_start_url(provider)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(url)


@router.get("/auth/{provider}/callback")
def auth_callback(provider: str, code: str = Query(...), state: str = Query(...)) -> RedirectResponse:
    oauth_service = OAuthService()
    try:
        session = oauth_service.exchange_code(provider, code, state)
        redirect_url = oauth_service.build_frontend_redirect_url(session=session)
    except ValueError as exc:
        redirect_url = oauth_service.build_frontend_redirect_url(error=str(exc))
    return RedirectResponse(redirect_url)


# --- agent chat / feedback / actions ------------------------------------------


@router.post("/agent/chat", response_model=AgentChatResponse)
def agent_chat(
    request: AgentChatRequest,
    container: AppContainer = Depends(get_container),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> AgentChatResponse:
    request.user_id = current_user["id"]
    request.role = current_user["role"]
    try:
        return container.build_agent_orchestrator().handle_chat(request)
    except Exception:
        # A skill bug or an unreachable dependency should never surface as a
        # raw HTTP 500 in the chat UI -- log it for debugging and answer with
        # a normal chat message instead, so the conversation can continue.
        logger.exception("agent_chat failed for message=%r", request.message)
        return AgentChatResponse(
            conversation_id=request.conversation_id,
            intent=AgentIntent.GENERAL_QUESTION,
            answer=(
                "Desole, je rencontre un probleme technique pour repondre a cette demande. "
                "Merci de reessayer, ou de reformuler votre question."
            ),
            requires_approval=False,
            confidence=0.0,
            justification="Erreur technique interceptee au niveau de l'API.",
        )


@router.post("/agent/feedback")
def agent_feedback(
    request: AgentFeedbackRequest,
    container: AppContainer = Depends(get_container),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, int]:
    request.user_id = current_user["id"]
    try:
        return container.build_agent_orchestrator().save_feedback(**request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/agent/actions/pending")
def agent_actions_pending(
    container: AppContainer = Depends(get_container),
    current_user: dict[str, Any] = Depends(require_ceo),
) -> dict[str, Any]:
    return {"rows": container.build_agent_orchestrator().list_pending_actions()}


@router.post("/agent/actions/{action_id}/approve")
def approve_action(
    action_id: int,
    request: AgentActionDecisionRequest,
    container: AppContainer = Depends(get_container),
    current_user: dict[str, Any] = Depends(require_ceo),
) -> dict[str, Any]:
    return container.build_agent_orchestrator().approve_action(action_id, request.approved_by, request.review_note)


@router.post("/agent/actions/{action_id}/reject")
def reject_action(
    action_id: int,
    request: AgentActionDecisionRequest,
    container: AppContainer = Depends(get_container),
    current_user: dict[str, Any] = Depends(require_ceo),
) -> dict[str, Any]:
    return container.build_agent_orchestrator().reject_action(action_id, request.approved_by, request.review_note)


# --- conversations / history ---------------------------------------------------


@router.get("/conversations")
def list_conversations(
    limit: int = Query(default=40),
    role: str | None = None,
    user_id: int | None = None,
    channel: str | None = None,
    container: AppContainer = Depends(get_container),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    if current_user["role"] != "ceo":
        role = current_user["role"]
        user_id = current_user["id"]
    rows = container.build_history_service().list_conversations(
        limit=limit, channel=channel, role=role, user_id=user_id
    )
    return {"rows": rows}


@router.get("/conversations/{conversation_key}/messages")
def list_conversation_messages(
    conversation_key: str,
    limit: int = Query(default=200),
    container: AppContainer = Depends(get_container),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    rows = container.build_history_service().list_messages(conversation_key=conversation_key, limit=limit)
    return {"rows": rows}


@router.get("/history")
def list_history(
    conversation_id: str | None = None,
    limit: int = Query(default=100),
    container: AppContainer = Depends(get_container),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    rows = container.build_history_service().list_history(conversation_id=conversation_id, limit=limit)
    return {"rows": rows}


# --- CEO review queue -----------------------------------------------------------


@router.get("/admin/reviews")
def list_admin_reviews(
    limit: int = Query(default=48),
    status: str | None = Query(default="all"),
    container: AppContainer = Depends(get_container),
    current_user: dict[str, Any] = Depends(require_ceo),
) -> dict[str, Any]:
    review_service = container.build_review_service()
    return {
        "rows": review_service.list_reviews(limit=limit, status=status),
        "summary": review_service.summarize_reviews(),
    }


@router.post("/admin/reviews/{history_id}/decision")
def submit_review_decision(
    history_id: int,
    request: ReviewDecisionRequest,
    container: AppContainer = Depends(get_container),
    current_user: dict[str, Any] = Depends(require_ceo),
) -> dict[str, Any]:
    try:
        row = container.build_review_service().save_decision(history_id=history_id, **request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"row": row}


# --- memory / rag status / reference data ---------------------------------------


@router.get("/memories/active")
def list_active_memories(
    container: AppContainer = Depends(get_container),
    current_user: dict[str, Any] = Depends(require_ceo),
) -> dict[str, Any]:
    return {"rows": container.build_agent_orchestrator().get_active_memory()}


@router.get("/rag/status")
def rag_status() -> dict[str, Any]:
    llm_model = settings.groq_chat_model if settings.llm_provider == "groq" else settings.gemini_chat_model
    return {
        "llm_provider": settings.llm_provider,
        "llm_model": llm_model,
        "embedding_backend": settings.embedding_backend,
        "embedding_model": settings.embedding_model_name,
        "qdrant_collection": settings.qdrant_collection,
    }


@router.get("/reference-values")
def reference_values() -> dict[str, Any]:
    cached_path = Path("data/unique_reference_values.json")
    if cached_path.exists():
        return json.loads(cached_path.read_text(encoding="utf-8"))
    from app.ingestion.export_unique_values import collect_unique_values

    return collect_unique_values()


# --- audio: transcription / speech synthesis -------------------------------------


async def _write_upload_to_tempfile(upload: UploadFile) -> Path:
    suffix = Path(upload.filename or "voice-input.webm").suffix or ".webm"
    tmp_path = Path(tempfile.gettempdir()) / f"auralys-upload-{uuid.uuid4().hex}{suffix}"
    tmp_path.write_bytes(await upload.read())
    return tmp_path


@router.post("/ask-audio-upload")
async def ask_audio_upload(
    audio: UploadFile = File(...),
    conversation_id: str | None = Form(default=None),
    container: AppContainer = Depends(get_container),
) -> dict[str, Any]:
    tmp_path = await _write_upload_to_tempfile(audio)
    try:
        response = container.build_question_pipeline().answer_voice(tmp_path, conversation_id=conversation_id)
    finally:
        tmp_path.unlink(missing_ok=True)
    return response.model_dump(mode="json")


@router.post("/transcribe-upload")
async def transcribe_upload(
    audio: UploadFile = File(...),
    container: AppContainer = Depends(get_container),
) -> dict[str, Any]:
    tmp_path = await _write_upload_to_tempfile(audio)
    try:
        transcript = container.build_speech_service().transcribe(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)
    return {"transcript": transcript}


@router.post("/speak-audio")
def speak_audio(request: SpeakRequest, container: AppContainer = Depends(get_container)) -> FileResponse:
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="`text` is required.")
    tmp_path = Path(tempfile.gettempdir()) / f"auralys-speak-{uuid.uuid4().hex}.wav"
    try:
        output_path = container.build_speech_service().synthesize(text, tmp_path)
    except Exception as exc:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=503, detail=f"La synthese vocale a echoue: {exc}") from exc
    return FileResponse(
        output_path,
        media_type="audio/wav",
        filename="speech.wav",
        background=BackgroundTask(lambda: Path(output_path).unlink(missing_ok=True)),
    )


# --- static reference pages (catch-all, must stay last in this router) -----------


_STATIC_PAGES_DIR = Path("static")


@router.get("/{page_name}")
def serve_static_page(page_name: str) -> FileResponse:
    file_name = f"{page_name.replace('-', '_')}.html"
    file_path = _STATIC_PAGES_DIR / file_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Static page not found: {file_name}")
    return FileResponse(file_path)
