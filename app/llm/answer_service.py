from __future__ import annotations

import time
import re

from app.commercial.analyzer import analyze_commercial_opportunity
from app.commercial.opportunity_logger import OpportunityLogger
from app.config import settings
from app.llm.llm_service import LLMService
from app.llm.prompt_builder import build_answer_prompt
from app.llm.token_counter import build_token_usage
from app.observability.langsmith_trace import finish_trace, start_trace
from app.retrieval.context_builder import build_context
from app.retrieval.hybrid_retriever import HybridRetriever
from app.retrieval.query_router import route_query
from schemas.commercial_schema import AdminAlertEvent
from schemas.retrieval_schema import RetrievalResult


class AnswerService:
    def __init__(
        self,
        retriever: HybridRetriever | None = None,
        llm_service: LLMService | None = None,
        opportunity_logger: OpportunityLogger | None = None,
    ) -> None:
        self.retriever = retriever or HybridRetriever()
        self.llm_service = llm_service or LLMService()
        self.opportunity_logger = opportunity_logger or OpportunityLogger()

    def answer(self, query: str) -> dict:
        routed_query = route_query(query)
        trace_client, trace_run_id, trace_started_at = start_trace(
            name="auralys_answer",
            inputs={
                "query": routed_query.original_query,
                "normalized_query": routed_query.normalized_query,
                "intent": routed_query.intent.value,
                "route": routed_query.route.value,
                "filters": routed_query.filters.model_dump(mode="json"),
            },
            metadata={
                "provider": settings.llm_provider,
                "model": _active_llm_model(),
                "interaction_mode": "text",
            },
        )
        started = time.perf_counter()
        retrieval_started = time.perf_counter()
        retrieval_result = self.retriever.search(routed_query.normalized_query)
        retrieval_ms = round((time.perf_counter() - retrieval_started) * 1000, 2)
        answer_payload = self.answer_from_retrieval(retrieval_result)
        total_ms = round((time.perf_counter() - started) * 1000, 2)
        timings = dict(answer_payload.get("timings") or {})
        timings = {
            **timings,
            "retrieval_ms": retrieval_ms,
            "total_ms": total_ms,
        }
        answer_payload.update(
            {
                "original_query": routed_query.original_query,
                "normalized_query": routed_query.normalized_query,
                "route": routed_query.route.value,
                "intent": routed_query.intent.value,
                "filters": routed_query.filters.model_dump(mode="json"),
                "timings": timings,
            }
        )
        finish_trace(
            trace_client,
            trace_run_id,
            trace_started_at,
            outputs={
                "answer": answer_payload["answer"],
                "response_source": answer_payload.get("response_source"),
                "llm_error": answer_payload.get("llm_error"),
                "token_usage": answer_payload.get("token_usage"),
                "timings": timings,
                "hit_count": len(answer_payload.get("hits", [])),
                "intent": answer_payload["intent"],
                "route": answer_payload["route"],
                "relevance_metrics": answer_payload.get("relevance_metrics"),
                "reasoning_signals": answer_payload.get("reasoning_signals"),
                "reasoning_summary": answer_payload.get("reasoning_summary"),
            },
            metadata={
                "provider": settings.llm_provider,
                "model": _active_llm_model(),
                "response_source": answer_payload.get("response_source"),
                "hit_count": len(answer_payload.get("hits", [])),
                "admin_alert": bool(answer_payload.get("admin_alert")),
                "grounding_status": (answer_payload.get("reasoning_signals") or {}).get("grounding_status"),
                "overall_relevance": (answer_payload.get("relevance_metrics") or {}).get("overall_relevance"),
                "top_hit_score": (answer_payload.get("relevance_metrics") or {}).get("top_hit_score"),
            },
            error=answer_payload.get("llm_error"),
        )
        return answer_payload

    def answer_from_retrieval(self, retrieval_result: RetrievalResult) -> dict:
        built_context = build_context(retrieval_result)
        sav_admin_analysis = analyze_commercial_opportunity(retrieval_result.query, retrieval_result)
        prompt = build_answer_prompt(retrieval_result.query, built_context, sav_admin_analysis)
        llm_started = time.perf_counter()
        llm_result = self.llm_service.answer_details(
            prompt,
            built_context.context_text,
            query=retrieval_result.query,
            analysis=sav_admin_analysis,
        )
        llm_ms = round((time.perf_counter() - llm_started) * 1000, 2)
        answer_text = str(llm_result["answer"] or "")
        token_usage = build_token_usage(
            prompt=prompt,
            answer=answer_text,
            context_text=built_context.context_text,
        )
        admin_alert = None
        if sav_admin_analysis.should_alert_admin and sav_admin_analysis.alert_reason:
            admin_alert = AdminAlertEvent(
                query=retrieval_result.query,
                lead_score=sav_admin_analysis.lead_score,
                buying_intent=sav_admin_analysis.buying_intent,
                opportunity_stage=sav_admin_analysis.opportunity_stage,
                matched_products=sav_admin_analysis.matched_products,
                missing_information=sav_admin_analysis.missing_information,
                alert_reason=sav_admin_analysis.alert_reason,
            )
            alert_path = self.opportunity_logger.log(admin_alert)
        else:
            alert_path = None
        hits = [hit.model_dump() for hit in retrieval_result.hits[:5]]
        relevance_metrics = _build_relevance_metrics(hits)
        reasoning_signals = _build_reasoning_signals(
            retrieval_result=retrieval_result,
            context=built_context.context_text,
            analysis=sav_admin_analysis,
            hits=hits,
            response_source=llm_result["response_source"],
            relevance_metrics=relevance_metrics,
        )
        return {
            "query": retrieval_result.query,
            "intent": retrieval_result.intent.value,
            "answer": answer_text,
            "response_source": llm_result["response_source"],
            "model_output": llm_result["model_output"],
            "llm_error": llm_result["llm_error"],
            "token_usage": token_usage,
            "timings": {
                "llm_ms": llm_ms,
            },
            "spoken_text": _build_spoken_text(answer_text, hits),
            "hits": hits,
            "relevance_metrics": relevance_metrics,
            "reasoning_signals": reasoning_signals,
            "reasoning_summary": _build_reasoning_summary(reasoning_signals),
            "sav_admin_analysis": sav_admin_analysis.model_dump(mode="json"),
            "admin_alert": None if admin_alert is None else admin_alert.model_dump(mode="json"),
            "admin_alert_log_path": alert_path,
        }


def _active_llm_model() -> str:
    if settings.llm_provider == "gemini":
        return settings.gemini_chat_model
    return settings.groq_chat_model


def _build_spoken_text(answer_text: str, hits: list[dict]) -> str:
    normalized_answer = _normalize_spoken_text(answer_text)
    if normalized_answer:
        return normalized_answer
    if settings.speech_speak_content_only:
        for hit in hits:
            spoken = _build_spoken_text_from_hit(hit)
            normalized_spoken = _normalize_spoken_text(spoken)
            if normalized_spoken:
                return normalized_spoken
    return answer_text.strip()


def _build_spoken_text_from_hit(hit: dict) -> str | None:
    metadata = hit.get("metadata") or {}
    chunk_type = str(metadata.get("chunk_type") or hit.get("chunk_type") or "").strip().lower()
    content = str(hit.get("content") or "").strip()
    client = str(metadata.get("client") or "").strip()

    if chunk_type == "issue":
        issue = str(metadata.get("issue") or "").strip()
        solution = str(metadata.get("solution") or "").strip()
        if not issue:
            match = re.search(
                r"^Issue for (?P<client>.*?): (?P<issue>.*?)(?:\. Proposed solution: (?P<solution>.*?))?\.?$",
                content,
                re.IGNORECASE,
            )
            if match:
                client = client or match.group("client").strip()
                issue = match.group("issue").strip()
                solution = str(match.group("solution") or "").strip()
        parts = []
        if client:
            parts.append(f"Chez {client},")
        if issue:
            parts.append(f"le probleme signale est : {issue}.")
        if solution and solution.lower() != "none":
            parts.append(f"La solution proposee est : {solution}.")
        if parts:
            return " ".join(parts)

    if chunk_type == "diffuser":
        model = str(metadata.get("model_diffuseur") or "").strip()
        emplacement = str(metadata.get("emplacement") or "").strip()
        parfum = str(metadata.get("nom_parfum") or "").strip()
        quantite = metadata.get("qte_parfum_existante")
        qualite = str(metadata.get("qualite_diffusion") or "").strip()
        etat = str(metadata.get("en_marche_arret") or "").strip()
        fuite = str(metadata.get("fuite") or "").strip()

        details = []
        if model:
            details.append(f"diffuseur {model}")
        if emplacement:
            details.append(f"emplacement {emplacement}")
        if parfum:
            details.append(f"parfum {parfum}")
        if quantite not in (None, ""):
            details.append(f"quantite restante {quantite} millilitres")
        if qualite:
            details.append(f"qualite de diffusion {qualite}")
        if etat:
            details.append(f"etat {etat}")
        if fuite:
            details.append(f"fuite {fuite}")
        if details:
            prefix = f"Chez {client}, " if client else ""
            return prefix + ", ".join(details) + "."

    if chunk_type == "recharge":
        ml = metadata.get("ml")
        parfum = str(metadata.get("parfum") or "").strip()
        emplacement = str(metadata.get("emplacement") or "").strip()
        frequence = str(metadata.get("frequence_diffusion") or "").strip()

        details = []
        if ml not in (None, ""):
            details.append(f"recharge de {ml} millilitres")
        else:
            details.append("recharge effectuee")
        if parfum:
            details.append(f"parfum {parfum}")
        if emplacement:
            details.append(f"emplacement {emplacement}")
        if frequence:
            details.append(f"frequence {frequence}")
        prefix = f"Chez {client}, " if client else ""
        return prefix + ", ".join(details) + "."

    if metadata.get("knowledge_category") in {"survey_knowledge", "docx_report"}:
        question = str(metadata.get("question") or "").strip()
        if question and content:
            return content.replace("Question:", "").replace("Answer:", "").strip()

    return content or None


def _normalize_spoken_text(text: str | None) -> str:
    if not text:
        return ""
    normalized = text.replace("\r", "\n").strip()
    if not normalized:
        return ""
    normalized = re.sub(r"[*_#`]+", " ", normalized)
    normalized = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", normalized)
    normalized = re.sub(r"\b\d+\.\s+", "", normalized)
    normalized = re.sub(r"(?m)^\s*[-•]\s*", "", normalized)
    normalized = re.sub(r"\n{2,}", "\n", normalized)
    normalized = re.sub(r"\s*\n\s*", " ", normalized)
    normalized = re.sub(r"\s{2,}", " ", normalized)
    return normalized.strip()


def _build_reasoning_signals(
    retrieval_result: RetrievalResult,
    context: str,
    analysis,
    hits: list[dict],
    response_source: str | None,
    relevance_metrics: dict,
) -> dict:
    top_hit = hits[0] if hits else {}
    top_metadata = top_hit.get("metadata") or {}
    distinct_clients = sorted(
        {
            str((hit.get("metadata") or {}).get("client") or "").strip()
            for hit in hits
            if str((hit.get("metadata") or {}).get("client") or "").strip()
        }
    )
    chunk_types = [
        str((hit.get("metadata") or {}).get("chunk_type") or "").strip().lower()
        for hit in hits
        if str((hit.get("metadata") or {}).get("chunk_type") or "").strip()
    ]
    evidence_sources = sorted({str(hit.get("source") or "").strip() for hit in hits if str(hit.get("source") or "").strip()})
    return {
        "query": retrieval_result.query,
        "intent": retrieval_result.intent.value,
        "filters": retrieval_result.filters.model_dump(mode="json"),
        "response_source": response_source,
        "grounding_status": "grounded" if context.strip() else "ungrounded",
        "context_present": bool(context.strip()),
        "retrieved_hit_count": len(hits),
        "top_chunk_type": str(top_metadata.get("chunk_type") or "").strip().lower() or None,
        "top_client": str(top_metadata.get("client") or "").strip() or None,
        "top_maintenance_number": str(top_metadata.get("maintenance_number") or "").strip() or None,
        "distinct_clients": distinct_clients,
        "chunk_types": chunk_types,
        "evidence_sources": evidence_sources,
        "matched_products": [str(item) for item in analysis.matched_products if item],
        "missing_information": [str(item) for item in analysis.missing_information if item],
        "recommended_next_steps": [str(item) for item in analysis.recommended_next_steps if item],
        "overall_relevance": relevance_metrics.get("overall_relevance"),
        "top_hit_score": relevance_metrics.get("top_hit_score"),
        "average_hit_score": relevance_metrics.get("average_hit_score"),
        "client_consistency": relevance_metrics.get("client_consistency"),
        "coverage_score": relevance_metrics.get("coverage_score"),
    }


def _build_reasoning_summary(reasoning_signals: dict) -> str:
    grounding_status = reasoning_signals.get("grounding_status") or "unknown"
    hit_count = reasoning_signals.get("retrieved_hit_count", 0)
    top_client = reasoning_signals.get("top_client") or "aucun client dominant"
    top_chunk_type = reasoning_signals.get("top_chunk_type") or "aucun type dominant"
    overall_relevance = reasoning_signals.get("overall_relevance")
    missing_information = reasoning_signals.get("missing_information") or []
    missing_info_text = ", ".join(missing_information[:3]) if missing_information else "aucune"
    return (
        f"grounding={grounding_status}; "
        f"hits={hit_count}; "
        f"top_client={top_client}; "
        f"top_chunk_type={top_chunk_type}; "
        f"relevance={overall_relevance if overall_relevance is not None else 'n/a'}; "
        f"missing_information={missing_info_text}"
    )


def _build_relevance_metrics(hits: list[dict]) -> dict[str, float | int | None]:
    if not hits:
        return {
            "overall_relevance": 0.0,
            "top_hit_score": 0.0,
            "average_hit_score": 0.0,
            "coverage_score": 0.0,
            "metadata_match_score": 0.0,
            "client_consistency": 0.0,
            "hit_count": 0,
        }

    scores = [max(0.0, min(1.0, float(hit.get("score") or 0.0))) for hit in hits]
    top_hit_score = scores[0]
    average_hit_score = sum(scores) / len(scores)

    coverage_values: list[float] = []
    metadata_values: list[float] = []
    client_counts: dict[str, int] = {}
    for hit in hits:
        metadata = hit.get("metadata") or {}
        breakdown = metadata.get("score_breakdown") or {}
        coverage_values.append(max(0.0, min(1.0, float(breakdown.get("term_overlap") or 0.0))))
        metadata_values.append(max(0.0, min(1.0, float(breakdown.get("metadata_overlap") or 0.0))))
        client = str(metadata.get("client") or "").strip()
        if client:
            client_counts[client] = client_counts.get(client, 0) + 1

    coverage_score = sum(coverage_values) / len(coverage_values) if coverage_values else 0.0
    metadata_match_score = sum(metadata_values) / len(metadata_values) if metadata_values else 0.0
    dominant_client_hits = max(client_counts.values()) if client_counts else 0
    client_consistency = dominant_client_hits / len(hits) if hits else 0.0

    overall_relevance = (
        (top_hit_score * 0.34)
        + (average_hit_score * 0.26)
        + (coverage_score * 0.18)
        + (metadata_match_score * 0.12)
        + (client_consistency * 0.10)
    )
    overall_relevance = max(0.0, min(1.0, overall_relevance))

    return {
        "overall_relevance": round(overall_relevance, 4),
        "top_hit_score": round(top_hit_score, 4),
        "average_hit_score": round(average_hit_score, 4),
        "coverage_score": round(coverage_score, 4),
        "metadata_match_score": round(metadata_match_score, 4),
        "client_consistency": round(client_consistency, 4),
        "hit_count": len(hits),
    }
