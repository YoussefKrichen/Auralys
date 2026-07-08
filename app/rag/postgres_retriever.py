from __future__ import annotations

from typing import Any

from app.db.postgres import PostgresDatabase


class PostgresRetriever:
    def __init__(self, database: PostgresDatabase) -> None:
        self.database = database

    def retrieve(
        self,
        *,
        request_type: str,
        client_id: int | None = None,
        diffuseur_id: int | None = None,
        technicien_id: int | None = None,
        limit: int = 3,
    ) -> dict[str, list[dict[str, Any]]]:
        context: dict[str, list[dict[str, Any]]] = {
            "clients": [],
            "diffuseurs": [],
            "techniciens": [],
            "interventions": [],
            "reclamations": [],
            "recommendations": [],
        }

        needs_client = request_type in {
            "client_analysis",
            "sav_analysis",
            "recommendation_analysis",
            "report_learning",
        }
        needs_diffuseur = request_type in {
            "diffuseur_analysis",
            "sav_analysis",
            "recommendation_analysis",
        }
        needs_technicien = request_type in {
            "technicien_analysis",
            "sav_analysis",
            "report_learning",
        }

        if client_id is not None or needs_client:
            context["clients"] = self.database.fetch_records(
                "clients",
                filters={"id": client_id} if client_id is not None else None,
                limit=limit,
            )
            context["interventions"] = self.database.fetch_records(
                "interventions",
                filters={"client_id": client_id} if client_id is not None else None,
                limit=limit,
            )
            context["reclamations"] = self.database.fetch_records(
                "reclamations",
                filters={"client_id": client_id} if client_id is not None else None,
                limit=limit,
            )
            context["recommendations"] = self.database.fetch_records(
                "recommendations",
                filters={"client_id": client_id} if client_id is not None else None,
                limit=limit,
            )

        if diffuseur_id is not None or needs_diffuseur:
            context["diffuseurs"] = self.database.fetch_records(
                "diffuseurs",
                filters={"id": diffuseur_id} if diffuseur_id is not None else None,
                limit=limit,
            )
            if not context["interventions"]:
                context["interventions"] = self.database.fetch_records(
                    "interventions",
                    filters={"diffuseur_id": diffuseur_id} if diffuseur_id is not None else None,
                    limit=limit,
                )

        if technicien_id is not None or needs_technicien:
            context["techniciens"] = self.database.fetch_records(
                "techniciens",
                filters={"id": technicien_id} if technicien_id is not None else None,
                limit=limit,
            )
            if not context["interventions"]:
                context["interventions"] = self.database.fetch_records(
                    "interventions",
                    filters={"technicien_id": technicien_id} if technicien_id is not None else None,
                    limit=limit,
                )

        return context
