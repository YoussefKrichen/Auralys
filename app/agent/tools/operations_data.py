from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
from typing import Any

from app.agent.store import AgentStore
from app.agent.tools.base import LoggedTool
from app.config import settings
from app.ingestion.normalize import load_fiches_from_directory


@dataclass
class ClientRecord:
    client_id: str
    client_name: str
    address: str | None


class OperationsDataTool(LoggedTool):
    def __init__(self, store: AgentStore | None = None) -> None:
        super().__init__(store=store)

    def get_client_by_name(self, name: str) -> dict[str, Any]:
        lookup = name.strip()
        return self._run_logged(
            "get_client_by_name",
            {"name": lookup},
            lambda: self._lookup_client(lookup),
        )

    def get_client_history(self, client_id: str) -> dict[str, Any]:
        return self._run_logged(
            "get_client_history",
            {"client_id": client_id},
            lambda: {"history": self._collect_client_history(client_id)},
        )

    def get_client_interventions(self, client_id: str) -> dict[str, Any]:
        return self._run_logged(
            "get_client_interventions",
            {"client_id": client_id},
            lambda: {"interventions": self._collect_client_history(client_id)},
        )

    def get_client_reclamations(self, client_id: str) -> dict[str, Any]:
        def _build() -> dict[str, Any]:
            rows = [
                row
                for row in self._collect_client_history(client_id)
                if row.get("issue")
            ]
            return {"reclamations": rows}

        return self._run_logged("get_client_reclamations", {"client_id": client_id}, _build)

    def get_today_interventions(self) -> dict[str, Any]:
        return self._run_logged("get_today_interventions", {}, lambda: {"interventions": self._collect_today_interventions()})

    def get_interventions_by_team(self, team_id: int) -> dict[str, Any]:
        def _build() -> dict[str, Any]:
            interventions = self._collect_today_interventions()
            for item in interventions:
                item["team_id"] = team_id
            return {"interventions": interventions}

        return self._run_logged("get_interventions_by_team", {"team_id": team_id}, _build)

    def get_open_reclamations(self) -> dict[str, Any]:
        def _build() -> dict[str, Any]:
            rows = []
            for intervention in self._collect_today_interventions():
                if intervention.get("issue"):
                    age_hours = 72 if intervention.get("status") == "EN_RETARD" else 24
                    rows.append({**intervention, "age_hours": age_hours})
            return {"reclamations": rows[:8]}

        return self._run_logged("get_open_reclamations", {}, _build)

    def get_client_stock(self, client_id: str) -> dict[str, Any]:
        def _build() -> dict[str, Any]:
            history = self._collect_client_history(client_id)
            quantities = [
                diffuser["quantity_ml"]
                for item in history
                for diffuser in item.get("diffusers", [])
                if diffuser.get("quantity_ml") is not None
            ]
            current_level = min(quantities) if quantities else None
            return {
                "client_id": client_id,
                "current_level_ml": current_level,
                "status": "LOW" if current_level is not None and current_level <= 20 else "OK",
            }

        return self._run_logged("get_client_stock", {"client_id": client_id}, _build)

    def create_alert(self, client_id: str, message: str) -> dict[str, Any]:
        return self._run_logged(
            "create_alert",
            {"client_id": client_id, "message": message},
            lambda: {
                "client_id": client_id,
                "message": message,
                "status": "PROPOSED_ONLY",
            },
        )

    def propose_intervention(self, client_id: str, intervention_type: str) -> dict[str, Any]:
        return self._run_logged(
            "propose_intervention",
            {"client_id": client_id, "intervention_type": intervention_type},
            lambda: {
                "client_id": client_id,
                "intervention_type": intervention_type,
                "status": "PROPOSED_ONLY",
            },
        )

    def get_client_priority(self, client_id: str) -> dict[str, Any]:
        return self._run_logged(
            "get_client_priority",
            {"client_id": client_id},
            lambda: {
                "client_id": client_id,
                "priority": "IMPORTANT" if any(token in client_id for token in ("pharmacie", "victoria", "716")) else "STANDARD",
            },
        )

    def get_opening_hours(self, client_id: str) -> dict[str, Any]:
        return self._run_logged(
            "get_opening_hours",
            {"client_id": client_id},
            lambda: {
                "client_id": client_id,
                "closing_soon": "pharmacie" in client_id,
                "hours": "08:00-18:00",
            },
        )

    def get_client_diffusers(self, client_id: str) -> dict[str, Any]:
        def _build() -> dict[str, Any]:
            history = self._collect_client_history(client_id)
            if not history:
                return {"diffusers": []}
            return {"diffusers": history[-1].get("diffusers", [])}

        return self._run_logged("get_client_diffusers", {"client_id": client_id}, _build)

    def get_last_intervention(self, client_id: str) -> dict[str, Any]:
        def _build() -> dict[str, Any]:
            history = self._collect_client_history(client_id)
            return {"intervention": history[0] if history else None}

        return self._run_logged("get_last_intervention", {"client_id": client_id}, _build)

    def _lookup_client(self, name: str) -> dict[str, Any]:
        normalized = name.casefold()
        records = self._build_client_index()
        for record in records:
            if record.client_name.casefold() == normalized:
                return record.__dict__
        partial_matches = [
            record
            for record in records
            if normalized in record.client_name.casefold()
        ]
        if partial_matches:
            partial_matches.sort(
                key=lambda record: (len(record.client_name), record.client_name.casefold())
            )
            return partial_matches[0].__dict__
        raise ValueError(f"Client not found for lookup: {name}")

    def _collect_today_interventions(self) -> list[dict[str, Any]]:
        fiches = [fiche for fiche in load_fiches_from_directory(settings.processed_data_dir) if fiche.document_type == "client_maintenance_form"]
        dated = [fiche for fiche in fiches if fiche.maintenance_details.service_date is not None]
        if not dated:
            return []
        target_date = max((fiche.maintenance_details.service_date for fiche in dated if fiche.maintenance_details.service_date is not None), default=date.today())
        interventions = []
        for fiche in dated:
            if fiche.maintenance_details.service_date != target_date:
                continue
            interventions.append(self._fiche_to_intervention(fiche))
        return interventions

    def _collect_client_history(self, client_id: str) -> list[dict[str, Any]]:
        records = []
        for fiche in load_fiches_from_directory(settings.processed_data_dir):
            if fiche.document_type != "client_maintenance_form":
                continue
            if self._client_id(fiche.client or "") != client_id:
                continue
            records.append(self._fiche_to_intervention(fiche))
        records.sort(
            key=lambda item: (item.get("service_date") or "", item.get("maintenance_number") or ""),
            reverse=True,
        )
        return records

    def _build_client_index(self) -> list[ClientRecord]:
        seen: dict[str, ClientRecord] = {}
        for fiche in load_fiches_from_directory(settings.processed_data_dir):
            if fiche.document_type != "client_maintenance_form" or not fiche.client:
                continue
            client_id = self._client_id(fiche.client)
            seen.setdefault(
                client_id,
                ClientRecord(
                    client_id=client_id,
                    client_name=fiche.client,
                    address=fiche.maintenance_details.address,
                ),
            )
        return list(seen.values())

    def _fiche_to_intervention(self, fiche) -> dict[str, Any]:
        client_name = fiche.client or "Client inconnu"
        client_id = self._client_id(client_name)
        diffusers = [
            {
                "model": diffuser.model_diffuseur,
                "emplacement": diffuser.emplacement,
                "quantity_ml": diffuser.qte_parfum_existante,
                "quality": diffuser.qualite_diffusion,
            }
            for diffuser in fiche.controle_diffuseur_recharge
        ]
        issue = fiche.probleme_recommandation.probleme_rencontree_raw
        status = "EN_RETARD" if issue else "PLANIFIE"
        return {
            "client_id": client_id,
            "client_name": client_name,
            "address": fiche.maintenance_details.address,
            "maintenance_number": fiche.maintenance_number,
            "service_date": fiche.maintenance_details.service_date.isoformat() if fiche.maintenance_details.service_date else None,
            "service_time": fiche.maintenance_details.service_time.isoformat() if fiche.maintenance_details.service_time else None,
            "issue": issue,
            "recommendation": fiche.probleme_recommandation.solution_proposee,
            "status": status,
            "urgency": "HIGH" if issue else "MEDIUM",
            "diffusers": diffusers,
            "route_hint": self._stable_coordinates(client_name),
        }

    @staticmethod
    def _client_id(client_name: str) -> str:
        return client_name.strip().casefold().replace(" ", "-")

    @staticmethod
    def _stable_coordinates(seed: str) -> dict[str, float]:
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
        lat_offset = int(digest[:4], 16) / 65535
        lng_offset = int(digest[4:8], 16) / 65535
        return {
            "lat": 36.8 + (lat_offset - 0.5) * 0.4,
            "lng": 10.18 + (lng_offset - 0.5) * 0.4,
        }
