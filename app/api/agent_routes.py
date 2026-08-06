from __future__ import annotations

import json
import logging
import tempfile
import uuid
from datetime import date
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

from app.agent.tools.kpi_aggregator import compute_kpis, format_period_label, resolve_period_range
from app.auth.dependencies import get_current_user, require_ceo
from app.auth.oauth_service import OAuthService
from app.auth.session_token import create_session_token
from app.bootstrap import AppContainer
from app.config import settings
from app.ingestion.fiche_writer import commit_ceo_correction
from app.reporting.report_files import REPORTS_DIR, is_valid_report_filename
from schemas.agent_schema import (
    AgentActionDecisionRequest,
    AgentChatRequest,
    AgentChatResponse,
    AgentFeedbackRequest,
    AgentIntent,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# Two distinct, deliberately separate CEO decision flows that happen to look
# alike -- easy to conflate when extending either one:
#   - ReviewDecisionRequest / /admin/reviews: judges a whole agent response
#     (a discussion_history row). "correct" produces a PENDING
#     KNOWLEDGE_CORRECTION memory as a side effect (see
#     ReviewService._create_correction_memory).
#   - MemoryDecisionRequest / /admin/memories: judges one proposed memory
#     already in the memories table (often that same KNOWLEDGE_CORRECTION).
#     There is no "correct" here -- you can't correct a correction, only
#     activate or drop it.
class ReviewDecisionRequest(BaseModel):
    decision: Literal["approve", "correct", "reject"]
    reviewed_by: str | None = None
    review_notes: str | None = None
    corrected_answer: str | None = None
    knowledge_action: str | None = None


class MemoryDecisionRequest(BaseModel):
    decision: Literal["approve", "reject"]
    reviewed_by: str | None = None


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
    if current_user["role"] != "ceo":
        conversation = container.database.fetch_conversation_by_key(conversation_key)
        if conversation is None or conversation.get("user_id") != current_user["id"]:
            # 404, not 403: don't confirm to a caller that a conversation_key they
            # don't own actually exists.
            raise HTTPException(status_code=404, detail="Conversation not found.")
    rows = container.build_history_service().list_messages(conversation_key=conversation_key, limit=limit)
    return {"rows": rows}


@router.get("/history")
def list_history(
    conversation_id: str | None = None,
    limit: int = Query(default=100),
    container: AppContainer = Depends(get_container),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    scoped_user_id = None if current_user["role"] == "ceo" else current_user["id"]
    rows = container.build_history_service().list_history(
        conversation_id=conversation_id, limit=limit, user_id=scoped_user_id
    )
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


@router.post("/admin/memories/{memory_id}/decision")
def submit_memory_decision(
    memory_id: int,
    request: MemoryDecisionRequest,
    container: AppContainer = Depends(get_container),
    current_user: dict[str, Any] = Depends(require_ceo),
) -> dict[str, Any]:
    memory_tool = container.build_memory_tool()
    reviewed_by = request.reviewed_by or current_user.get("username")
    if request.decision == "approve":
        row = memory_tool.approve_memory(memory_id, reviewed_by=reviewed_by)
    else:
        row = memory_tool.reject_memory(memory_id, reviewed_by=reviewed_by)
    if row is None:
        raise HTTPException(status_code=404, detail="Memory not found.")
    qdrant_stats: dict[str, Any] = {}
    if request.decision == "approve" and row.get("memory_type") == "KNOWLEDGE_CORRECTION":
        try:
            qdrant_stats = commit_ceo_correction(row)
        except Exception:
            logger.exception("Failed to index approved correction memory_id=%s", memory_id)
    return {"row": row, "qdrant": qdrant_stats}


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


@router.get("/kpis")
def kpis(current_user: dict[str, Any] = Depends(require_ceo)) -> dict[str, Any]:
    try:
        return compute_kpis(settings.gold_data_csv_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="Gold data source is unavailable.") from exc


@router.get("/reports")
def generate_report(
    period: Literal["day", "week", "month", "year"] = Query("month"),
    on: str | None = Query(None, description="Anchor date (YYYY-MM-DD) inside the target period, defaults to today."),
    current_user: dict[str, Any] = Depends(require_ceo),
) -> dict[str, Any]:
    """CEO-only KPI report scoped to a single day/week/month/year.

    Reuses compute_kpis (same shape as GET /kpis) so the frontend can render
    a report with the exact same components it already uses for the
    all-time dashboard -- only the underlying rows differ.
    """
    if on:
        try:
            anchor = date.fromisoformat(on)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid 'on' date, expected YYYY-MM-DD.") from exc
    else:
        anchor = date.today()

    start, end = resolve_period_range(period, anchor)
    try:
        report = compute_kpis(settings.gold_data_csv_path, start=start, end=end)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="Gold data source is unavailable.") from exc

    report["report"] = {
        "period": period,
        "label": format_period_label(period, start, end),
        "range_start": start.isoformat(),
        "range_end": end.isoformat(),
    }
    return report


@router.get("/reports/download/{filename}")
def download_report(
    filename: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> FileResponse:
    """Serves a report generated by CEOReportingSkill in chat.

    Open to any authenticated user rather than CEO-only, since the chat
    intent that produces these files (ASK_DAILY_REPORT) isn't itself
    role-restricted -- gating the download tighter than the chat flow that
    creates the link would just 401 on click for a SAV user who asked for it.
    filename is validated against report_files' own naming pattern so this
    can never be tricked into serving an arbitrary path.
    """
    if not is_valid_report_filename(filename):
        raise HTTPException(status_code=400, detail="Invalid report filename.")
    file_path = REPORTS_DIR / filename
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Report not found. It may have expired.")
    media_type = "application/pdf" if filename.endswith(".pdf") else (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    return FileResponse(file_path, media_type=media_type, filename=filename)


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
