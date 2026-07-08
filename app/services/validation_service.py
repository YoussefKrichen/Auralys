from __future__ import annotations

from app.graph.state import (
    RecommendationValidationRequest,
    RecommendationValidationResponse,
)


class ValidationService:
    def validate(
        self,
        request: RecommendationValidationRequest,
    ) -> RecommendationValidationResponse:
        validated = []
        for item in request.recommendations:
            cleaned = item.strip()
            if not cleaned:
                continue
            if cleaned[-1] not in {".", "!", "?"}:
                cleaned = f"{cleaned}."
            validated.append(cleaned)

        requires_human_validation = request.priority in {"high", "critical"} or any(
            "verifier" in finding.casefold() for finding in request.findings
        )
        trace = [
            *request.trace,
            f"ValidationService: {len(validated)} recommendation(s) normalized",
            f"ValidationService: requires_human_validation={requires_human_validation}",
        ]

        return RecommendationValidationResponse(
            validated_recommendations=validated,
            requires_human_validation=requires_human_validation,
            trace=trace,
        )
