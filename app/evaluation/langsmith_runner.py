from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from app.bootstrap import AppContainer
from app.config import settings
from app.evaluation.ragas_runner import load_eval_samples
from app.llm.llm_service import LLMService


def _read_mapping_or_attr(value: Any, key: str, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _active_llm_model() -> str:
    if settings.llm_provider == "gemini":
        return settings.gemini_chat_model
    return settings.groq_chat_model


def _load_langsmith_dependencies() -> tuple[Any, Any]:
    try:
        from langsmith import Client, evaluate
    except ImportError as exc:
        raise RuntimeError(
            "LangSmith dependencies are not installed. Run `pip install -r requirements.txt`."
        ) from exc
    return Client, evaluate


def _ensure_langsmith_env() -> None:
    if not settings.langsmith_api_key:
        raise RuntimeError("LANGSMITH_API_KEY is required to use the LangSmith module.")
    os.environ.setdefault("LANGSMITH_API_KEY", settings.langsmith_api_key)
    os.environ.setdefault("LANGSMITH_ENDPOINT", settings.langsmith_endpoint)
    os.environ.setdefault("LANGSMITH_PROJECT", settings.langsmith_project)
    if settings.langsmith_tracing:
        os.environ.setdefault("LANGSMITH_TRACING", "true")


def _build_client() -> Any:
    _ensure_langsmith_env()
    Client, _ = _load_langsmith_dependencies()
    return Client(
        api_key=settings.langsmith_api_key,
        api_url=settings.langsmith_endpoint,
    )


def _get_or_create_dataset(
    client: Any,
    dataset_name: str,
    description: str | None = None,
) -> Any:
    try:
        return client.read_dataset(dataset_name=dataset_name)
    except Exception:
        return client.create_dataset(dataset_name=dataset_name, description=description)


def sync_langsmith_dataset(
    input_path: str | Path,
    dataset_name: str,
    description: str | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    client = client or _build_client()
    samples = load_eval_samples(input_path)
    dataset = _get_or_create_dataset(client, dataset_name, description=description)
    existing_questions = {
        str(example.inputs.get("question"))
        for example in client.list_examples(dataset_id=dataset.id)
        if getattr(example, "inputs", None)
    }

    inputs: list[dict[str, Any]] = []
    outputs: list[dict[str, Any]] = []
    metadata: list[dict[str, Any]] = []
    for index, sample in enumerate(samples, start=1):
        if sample["question"] in existing_questions:
            continue
        inputs.append({"question": sample["question"]})
        outputs.append({"answer": sample["ground_truth"]})
        metadata.append(
            {
                "source_index": index,
                "source_file": str(Path(input_path)),
                "case_id": sample.get("case_id"),
                "category": sample.get("category"),
                "interaction_mode": sample.get("interaction_mode"),
                "notes": sample.get("notes"),
            }
        )

    if inputs:
        client.create_examples(
            dataset_id=dataset.id,
            inputs=inputs,
            outputs=outputs,
            metadata=metadata,
        )
    return {
        "dataset_name": dataset_name,
        "dataset_id": str(dataset.id),
        "uploaded_examples": len(inputs),
        "skipped_examples": len(samples) - len(inputs),
    }


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().split())


def _answer_exact_match(outputs: dict[str, Any], reference_outputs: dict[str, Any]) -> dict[str, Any]:
    predicted = _normalize_text(outputs.get("answer"))
    expected = _normalize_text(reference_outputs.get("answer"))
    return {"key": "answer_exact_match", "score": predicted == expected}


def _answer_contains_reference(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> dict[str, Any]:
    predicted = _normalize_text(outputs.get("answer"))
    expected = _normalize_text(reference_outputs.get("answer"))
    return {
        "key": "answer_contains_reference",
        "score": bool(expected) and expected in predicted,
    }


def _retrieved_context_count(outputs: dict[str, Any]) -> dict[str, Any]:
    hits = outputs.get("hits", [])
    return {"key": "retrieved_context_count", "score": len(hits)}


def _reasoning_grounded(outputs: dict[str, Any]) -> dict[str, Any]:
    reasoning_signals = outputs.get("reasoning_signals") or {}
    grounded = reasoning_signals.get("grounding_status") == "grounded"
    hit_count = reasoning_signals.get("retrieved_hit_count", 0)
    return {
        "key": "reasoning_grounded",
        "score": grounded and hit_count > 0,
        "comment": reasoning_signals.get("reasoning_summary") or outputs.get("reasoning_summary"),
    }


def _reasoning_has_structure(outputs: dict[str, Any]) -> dict[str, Any]:
    reasoning_signals = outputs.get("reasoning_signals") or {}
    required_keys = {
        "grounding_status",
        "retrieved_hit_count",
        "top_chunk_type",
        "distinct_clients",
        "matched_products",
        "missing_information",
    }
    present = sum(1 for key in required_keys if key in reasoning_signals)
    return {
        "key": "reasoning_structure_coverage",
        "score": present / len(required_keys),
    }


def _judge_answer_with_llm(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> dict[str, Any]:
    if not _judge_provider_available():
        return {
            "key": "llm_judge_grounded_answer",
            "score": None,
            "comment": "Skipped because no active LLM judge provider is configured.",
        }

    judge_prompt = _build_llm_judge_prompt(outputs, reference_outputs)
    try:
        raw = LLMService().generate_text(judge_prompt)
        parsed = _parse_judge_payload(raw)
        return {
            "key": "llm_judge_grounded_answer",
            "score": parsed["score"],
            "comment": parsed["comment"],
        }
    except Exception as exc:
        return {
            "key": "llm_judge_grounded_answer",
            "score": None,
            "comment": f"Judge failed: {exc}",
        }


def _judge_provider_available() -> bool:
    if settings.llm_provider == "gemini":
        return bool(settings.google_api_key)
    if settings.llm_provider == "groq":
        return bool(settings.groq_api_key)
    return False


def _build_llm_judge_prompt(outputs: dict[str, Any], reference_outputs: dict[str, Any]) -> str:
    hits = outputs.get("hits", []) or []
    rendered_hits = []
    for index, hit in enumerate(hits[:3], start=1):
        metadata = hit.get("metadata") or {}
        rendered_hits.append(
            "\n".join(
                [
                    f"Hit {index}:",
                    f"- score: {hit.get('score')}",
                    f"- source: {hit.get('source')}",
                    f"- client: {metadata.get('client')}",
                    f"- chunk_type: {metadata.get('chunk_type')}",
                    f"- content: {hit.get('content')}",
                ]
            )
        )
    reasoning_signals = outputs.get("reasoning_signals") or {}
    return (
        "Tu es un evaluateur strict de pipeline RAG.\n"
        "Tu notes si la reponse produite est correcte, suffisamment appuyee par les preuves recuperees, "
        "et utile par rapport a la reponse de reference.\n"
        "Ne recompense pas une reponse qui invente des faits absents des hits.\n"
        "Attribue une note entre 0 et 1.\n"
        "0 = incorrecte ou non fondee.\n"
        "0.5 = partiellement correcte ou partiellement fondee.\n"
        "1 = correcte, fondee et utile.\n"
        "Reponds en JSON strict sur une seule ligne avec les cles `score` et `comment`.\n\n"
        f"Question:\n{outputs.get('question') or ''}\n\n"
        f"Reponse de reference:\n{reference_outputs.get('answer') or ''}\n\n"
        f"Reponse du systeme:\n{outputs.get('answer') or ''}\n\n"
        f"Signaux de raisonnement:\n{json.dumps(reasoning_signals, ensure_ascii=False)}\n\n"
        f"Preuves recuperees:\n{'\n\n'.join(rendered_hits) if rendered_hits else 'Aucune preuve'}\n"
    )


def _parse_judge_payload(raw: str) -> dict[str, Any]:
    payload_text = raw.strip()
    match = re.search(r"\{.*\}", payload_text, re.DOTALL)
    if match:
        payload_text = match.group(0)
    payload = json.loads(payload_text)
    score = payload.get("score")
    comment = str(payload.get("comment") or "").strip()
    if not isinstance(score, (int, float)):
        raise ValueError("Judge output did not contain a numeric `score`.")
    bounded_score = max(0.0, min(1.0, float(score)))
    return {"score": bounded_score, "comment": comment}


def run_langsmith_evaluation(
    input_path: str | Path,
    dataset_name: str,
    experiment_prefix: str = "auralys",
    description: str | None = None,
    upload_dataset: bool = True,
    container: AppContainer | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    client = client or _build_client()
    _, evaluate = _load_langsmith_dependencies()
    if upload_dataset:
        sync_langsmith_dataset(
            input_path=input_path,
            dataset_name=dataset_name,
            description=description,
            client=client,
        )

    container = container or AppContainer()
    answer_service = container.build_answer_service()

    def target(inputs: dict[str, Any]) -> dict[str, Any]:
        question = str(inputs["question"])
        result = answer_service.answer(question)
        return {
            "question": question,
            "answer": result["answer"],
            "intent": result["intent"],
            "hits": result["hits"],
            "reasoning_signals": result.get("reasoning_signals") or {},
            "reasoning_summary": result.get("reasoning_summary"),
            "response_source": result.get("response_source"),
        }

    results = evaluate(
        target,
        data=dataset_name,
        evaluators=[
            _answer_exact_match,
            _answer_contains_reference,
            _retrieved_context_count,
            _reasoning_grounded,
            _reasoning_has_structure,
            _judge_answer_with_llm,
        ],
        experiment_prefix=experiment_prefix,
        description=description or f"Auralys evaluation for dataset `{dataset_name}`.",
        metadata={
            "dataset_name": dataset_name,
            "input_path": str(Path(input_path)),
            "provider": settings.llm_provider,
            "model": _active_llm_model(),
        },
        client=client,
        blocking=True,
    )

    rows: list[dict[str, Any]] = []
    summary_scores: dict[str, list[float]] = {}
    for row in results:
        evaluation_results_payload = _read_mapping_or_attr(row, "evaluation_results", {})
        evaluation_results = _read_mapping_or_attr(evaluation_results_payload, "results", []) or []
        row_scores: dict[str, Any] = {}
        for item in evaluation_results:
            key = _read_mapping_or_attr(item, "key")
            score = _read_mapping_or_attr(item, "score")
            if key is None:
                continue
            row_scores[key] = score
            if isinstance(score, bool):
                summary_scores.setdefault(key, []).append(1.0 if score else 0.0)
            elif isinstance(score, (int, float)):
                summary_scores.setdefault(key, []).append(float(score))
        example = _read_mapping_or_attr(row, "example")
        run = _read_mapping_or_attr(row, "run")
        rows.append(
            {
                "example_id": str(_read_mapping_or_attr(example, "id", "")),
                "inputs": _read_mapping_or_attr(example, "inputs", {}),
                "reference_outputs": _read_mapping_or_attr(example, "outputs", {}),
                "outputs": _read_mapping_or_attr(run, "outputs"),
                "scores": row_scores,
            }
        )

    summary = {
        key: sum(values) / len(values)
        for key, values in summary_scores.items()
        if values
    }
    return {
        "dataset_name": dataset_name,
        "experiment_name": getattr(results, "experiment_name", None),
        "samples": len(rows),
        "summary": summary,
        "rows": rows,
    }
