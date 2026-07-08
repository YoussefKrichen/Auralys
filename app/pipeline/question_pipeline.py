from __future__ import annotations

from pathlib import Path

from app.audio.speech_service import SpeechService
from app.history.history_service import HistoryService
from app.llm.answer_service import AnswerService
from schemas.pipeline_schema import PipelineResponse


class QuestionPipeline:
    def __init__(
        self,
        answer_service: AnswerService | None = None,
        speech_service: SpeechService | None = None,
        history_service: HistoryService | None = None,
    ) -> None:
        self.answer_service = answer_service or AnswerService()
        self.speech_service = speech_service or SpeechService()
        self.history_service = history_service or HistoryService()

    def answer_text(
        self,
        query: str,
        output_audio_path: str | Path | None = None,
        conversation_id: str | None = None,
    ) -> PipelineResponse:
        answer_payload = self.answer_service.answer(query)
        audio_path = None
        if output_audio_path is not None:
            audio_path = str(
                self.speech_service.synthesize(
                    answer_payload.get("spoken_text") or answer_payload["answer"],
                    output_audio_path,
                )
            )
        response = PipelineResponse(
            input_type="text",
            original_query=answer_payload["original_query"],
            normalized_query=answer_payload["normalized_query"],
            route=answer_payload["route"],
            intent=answer_payload["intent"],
            filters=answer_payload["filters"],
            answer=answer_payload["answer"],
            response_source=answer_payload.get("response_source"),
            model_output=answer_payload.get("model_output"),
            llm_error=answer_payload.get("llm_error"),
            token_usage=answer_payload.get("token_usage") or {},
            timings=answer_payload.get("timings") or {},
            spoken_text=answer_payload.get("spoken_text"),
            hits=answer_payload["hits"],
            relevance_metrics=answer_payload.get("relevance_metrics") or {},
            reasoning_signals=answer_payload.get("reasoning_signals") or {},
            reasoning_summary=answer_payload.get("reasoning_summary"),
            sav_admin_analysis=answer_payload["sav_admin_analysis"],
            admin_alert=answer_payload["admin_alert"],
            admin_alert_log_path=answer_payload["admin_alert_log_path"],
            output_audio_path=audio_path,
        )
        try:
            history_id, resolved_conversation_id = self.history_service.save_response(
                response,
                conversation_id=conversation_id,
            )
        except Exception:
            return response.model_copy(update={"conversation_id": conversation_id})
        return response.model_copy(
            update={
                "history_id": history_id,
                "conversation_id": resolved_conversation_id,
            }
        )

    def answer_voice(
        self,
        input_audio_path: str | Path,
        output_audio_path: str | Path | None = None,
        conversation_id: str | None = None,
    ) -> PipelineResponse:
        transcript = self.speech_service.transcribe(input_audio_path)
        response = self.answer_text(
            transcript,
            output_audio_path=output_audio_path,
            conversation_id=conversation_id,
        )
        return response.model_copy(
            update={
                "input_type": "voice",
                "transcript": transcript,
                "original_query": str(Path(input_audio_path)),
            }
        )
