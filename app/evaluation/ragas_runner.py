from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from app.bootstrap import AppContainer


def _load_ragas_dependencies() -> tuple[Any, Any, dict[str, Any]]:
    try:
        from datasets import Dataset
        from ragas import evaluate
    except ImportError as exc:
        raise RuntimeError(
            "RAGAS dependencies are not installed. Run `pip install -r requirements.txt`."
        ) from exc

    metrics_map: dict[str, Any] = {}
    try:
        from ragas.metrics import (
            answer_correctness,
            answer_relevancy,
            context_precision,
            faithfulness,
        )

        metrics_map.update(
            {
                "answer_correctness": answer_correctness,
                "answer_relevancy": answer_relevancy,
                "context_precision": context_precision,
                "faithfulness": faithfulness,
            }
        )
    except ImportError:
        from ragas.metrics import (
            AnswerCorrectness,
            ContextPrecision,
            Faithfulness,
            ResponseRelevancy,
        )

        metrics_map.update(
            {
                "answer_correctness": AnswerCorrectness(),
                "answer_relevancy": ResponseRelevancy(),
                "context_precision": ContextPrecision(),
                "faithfulness": Faithfulness(),
            }
        )

    return Dataset, evaluate, metrics_map


def load_eval_samples(file_path: str | Path) -> list[dict[str, Any]]:
    path = Path(file_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Evaluation file must be a JSON array.")
    samples: list[dict[str, Any]] = []
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Sample {index} must be a JSON object.")
        question = item.get("question")
        ground_truth = item.get("ground_truth")
        if not question or not ground_truth:
            raise ValueError(
                f"Sample {index} must contain non-empty `question` and `ground_truth` fields."
            )
        sample = {
            "question": str(question),
            "ground_truth": str(ground_truth),
        }
        for optional_key in ("case_id", "category", "interaction_mode", "notes"):
            optional_value = item.get(optional_key)
            if optional_value is not None:
                sample[optional_key] = optional_value
        samples.append(sample)
    return samples


def build_prediction_rows(
    samples: list[dict[str, Any]],
    container: AppContainer | None = None,
) -> list[dict[str, Any]]:
    container = container or AppContainer()
    answer_service = container.build_answer_service()
    rows: list[dict[str, Any]] = []
    for sample in samples:
        result = answer_service.answer(sample["question"])
        contexts = [hit["content"] for hit in result.get("hits", [])]
        rows.append(
            {
                "question": sample["question"],
                "answer": result["answer"],
                "contexts": contexts,
                "ground_truth": sample["ground_truth"],
                "case_id": sample.get("case_id"),
                "category": sample.get("category"),
                "interaction_mode": sample.get("interaction_mode"),
                "notes": sample.get("notes"),
            }
        )
    return rows


def run_ragas_evaluation(
    input_path: str | Path,
    output_path: str | Path | None = None,
    container: AppContainer | None = None,
) -> dict[str, Any]:
    Dataset, evaluate, metrics_map = _load_ragas_dependencies()
    samples = load_eval_samples(input_path)
    rows = build_prediction_rows(samples, container=container)
    dataset = Dataset.from_list(rows)
    selected_metrics = [
        metrics_map["faithfulness"],
        metrics_map["answer_relevancy"],
        metrics_map["context_precision"],
        metrics_map["answer_correctness"],
    ]
    result = evaluate(dataset=dataset, metrics=selected_metrics)
    scores = result.to_pandas().to_dict(orient="records")
    if hasattr(result, "to_dict"):
        summary = result.to_dict()
    else:
        summary = {}
        if hasattr(result, "_repr_dict") and callable(result._repr_dict):
            summary = result._repr_dict()
        elif hasattr(result, "__dict__"):
            summary = {
                key: value
                for key, value in result.__dict__.items()
                if isinstance(value, (str, int, float, bool, list, dict, type(None)))
            }
        if not summary and scores:
            numeric_keys = [
                key
                for key, value in scores[0].items()
                if isinstance(value, (int, float))
            ]
            summary = {
                key: sum(row.get(key, 0) for row in scores) / max(len(scores), 1)
                for key in numeric_keys
            }
    payload = {
        "samples": len(rows),
        "summary": summary,
        "rows": scores,
    }
    if output_path is not None:
        output = Path(output_path)
        if output.suffix.lower() == ".csv":
            _write_csv_report(output, scores)
        else:
            output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def _write_csv_report(output_path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)

    with output_path.open("w", encoding="utf-8", newline="") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json.dumps(value, ensure_ascii=False)
                    if isinstance(value, (list, dict))
                    else value
                    for key, value in row.items()
                }
            )
