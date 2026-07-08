from __future__ import annotations

from typing import Any

from app.db import Database, default_database


class ReviewService:
    def __init__(self, database: Database | None = None) -> None:
        self.database = database or default_database

    def ensure_schema(self) -> None:
        self.database.init_schema()

    def list_reviews(
        self,
        limit: int = 100,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        self.ensure_schema()
        return self.database.fetch_review_queue(limit=limit, status=status)

    def save_decision(
        self,
        *,
        history_id: int,
        decision: str,
        reviewed_by: str | None = None,
        review_notes: str | None = None,
        corrected_answer: str | None = None,
        knowledge_action: str | None = None,
    ) -> dict[str, Any]:
        self.ensure_schema()
        normalized_decision = decision.strip().lower()
        status_map = {
            "approve": "approved",
            "correct": "corrected",
            "reject": "rejected",
        }
        if normalized_decision not in status_map:
            raise ValueError("Unsupported review decision.")
        payload = {
            "history_id": history_id,
            "review_status": status_map[normalized_decision],
            "decision": normalized_decision,
            "review_notes": (review_notes or "").strip() or None,
            "corrected_answer": (corrected_answer or "").strip() or None,
            "knowledge_action": (knowledge_action or "").strip() or None,
            "reviewed_by": (reviewed_by or "").strip() or None,
        }
        with self.database.connection() as connection:
            self.database.upsert_review_case(connection, payload)
        for row in self.list_reviews(limit=200, status="all"):
            if row["history_id"] == history_id:
                return row
        raise ValueError("Reviewed history entry not found.")

    def summarize_reviews(self, limit: int = 200) -> dict[str, Any]:
        rows = self.list_reviews(limit=limit, status="all")
        summary = {
            "total": len(rows),
            "pending": 0,
            "approved": 0,
            "corrected": 0,
            "rejected": 0,
            "with_alert": 0,
            "with_llm_error": 0,
            "knowledge_ready": 0,
        }
        for row in rows:
            status = row.get("review_status") or "pending"
            summary[status] = summary.get(status, 0) + 1
            if row.get("admin_alert") is not None:
                summary["with_alert"] += 1
            if row.get("llm_error"):
                summary["with_llm_error"] += 1
            if row.get("knowledge_action"):
                summary["knowledge_ready"] += 1
        return summary
