from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any

from app.agent.store import AgentStore
from app.agent.tools.base import LoggedTool
from app.agent.tools.emplacement_normalizer import canonical_emplacement
from app.agent.tools.gold_data_source import GoldVisit, load_gold_visits
from app.agent.tools.text_normalize import client_id as compute_client_id
from app.config import settings


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

    def find_client_mentioned_in_text(self, text: str) -> dict[str, Any] | None:
        """Reverse lookup: does any known client's name appear inside free-form text?

        IntentRouter.extract_client_name only matches "client: X"/"chez X" patterns, and
        _lookup_client only matches when the query is a substring of the client name (the
        opposite direction). A natural question like "combien de diffuseurs a le client X"
        fits neither, so this scans the client index for the longest name that appears
        inside the message.
        """
        return self._run_logged(
            "find_client_mentioned_in_text",
            {"text": text},
            lambda: self._find_client_in_text(text),
        )

    def count_client_diffusers(self, client_id: str) -> dict[str, Any]:
        def _build() -> dict[str, Any]:
            history = self._collect_client_history(client_id)
            groups: dict[tuple[str, ...], dict[str, Any]] = {}
            for visit in history:
                for diffuser in visit.get("diffusers", []):
                    if not diffuser.get("emplacement") and not diffuser.get("model"):
                        continue
                    key = canonical_emplacement(diffuser.get("emplacement"))
                    group = groups.setdefault(key, {"raw_labels": {}, "models": set()})
                    raw_label = diffuser.get("emplacement") or "Emplacement non precise"
                    group["raw_labels"][raw_label] = group["raw_labels"].get(raw_label, 0) + 1
                    if diffuser.get("model"):
                        group["models"].add(diffuser["model"])
            locations = []
            for group in groups.values():
                best_label = max(group["raw_labels"].items(), key=lambda kv: (kv[1], len(kv[0])))[0]
                locations.append({"emplacement": best_label, "models": sorted(group["models"])})
            return {
                "client_id": client_id,
                "diffuser_count": len(locations),
                "locations": locations,
                "raw_visit_count": len(history),
                "history": history[:10],
            }

        return self._run_logged("count_client_diffusers", {"client_id": client_id}, _build)

    def list_recent_clients(self, limit: int = 10) -> dict[str, Any]:
        def _build() -> dict[str, Any]:
            activity: dict[str, dict[str, Any]] = {}
            for visit in load_gold_visits(settings.gold_data_csv_path):
                if not visit.client:
                    continue
                client_id = self._client_id(visit.client)
                entry = activity.setdefault(
                    client_id,
                    {
                        "client_id": client_id,
                        "client_name": visit.client,
                        "address": visit.address,
                        "last_service_date": None,
                        "visit_count": 0,
                    },
                )
                entry["visit_count"] += 1
                service_date = visit.service_date
                if service_date is not None:
                    current = entry["last_service_date"]
                    if current is None or service_date > current:
                        entry["last_service_date"] = service_date

            dated = [row for row in activity.values() if row["last_service_date"] is not None]
            dated.sort(key=lambda row: row["last_service_date"], reverse=True)
            top = dated[: max(limit, 1)]
            return {
                "clients": [
                    {**row, "last_service_date": row["last_service_date"].isoformat()}
                    for row in top
                ]
            }

        return self._run_logged("list_recent_clients", {"limit": limit}, _build)

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

    def _find_client_in_text(self, text: str) -> dict[str, Any] | None:
        normalized_text = text.casefold()
        best: ClientRecord | None = None
        for record in self._build_client_index():
            name = record.client_name.strip()
            if len(name) < 3:
                continue
            if name.casefold() in normalized_text:
                if best is None or len(name) > len(best.client_name):
                    best = record
        return best.__dict__ if best else None

    def _collect_today_interventions(self) -> list[dict[str, Any]]:
        visits = load_gold_visits(settings.gold_data_csv_path)
        dated = [visit for visit in visits if visit.service_date is not None]
        if not dated:
            return []
        target_date = max(visit.service_date for visit in dated)
        return [self._visit_to_intervention(visit) for visit in dated if visit.service_date == target_date]

    def _collect_client_history(self, client_id: str) -> list[dict[str, Any]]:
        records = []
        for visit in load_gold_visits(settings.gold_data_csv_path):
            if self._client_id(visit.client or "") != client_id:
                continue
            records.append(self._visit_to_intervention(visit))
        records.sort(
            key=lambda item: (item.get("service_date") or "", item.get("maintenance_number") or ""),
            reverse=True,
        )
        return records

    def _build_client_index(self) -> list[ClientRecord]:
        seen: dict[str, ClientRecord] = {}
        for visit in load_gold_visits(settings.gold_data_csv_path):
            if not visit.client:
                continue
            client_id = self._client_id(visit.client)
            seen.setdefault(
                client_id,
                ClientRecord(
                    client_id=client_id,
                    client_name=visit.client,
                    address=visit.address,
                ),
            )
        return list(seen.values())

    def _visit_to_intervention(self, visit: GoldVisit) -> dict[str, Any]:
        client_name = visit.client or "Client inconnu"
        client_id = self._client_id(client_name)
        diffusers = [
            {
                "model": diffuser.get("model"),
                "emplacement": diffuser.get("emplacement"),
                "quantity_ml": diffuser.get("quantity_ml"),
                "quality": None,
            }
            for diffuser in visit.diffusers
        ]
        issue = visit.issue
        status = "EN_RETARD" if issue else "PLANIFIE"
        return {
            "client_id": client_id,
            "client_name": client_name,
            "address": visit.address,
            "maintenance_number": visit.maintenance_number,
            "service_date": visit.service_date.isoformat() if visit.service_date else None,
            "service_time": None,
            "issue": issue,
            "recommendation": None,
            "status": status,
            "urgency": "HIGH" if issue else "MEDIUM",
            "diffusers": diffusers,
            "route_hint": self._stable_coordinates(client_name),
        }

    @staticmethod
    def _client_id(client_name: str) -> str:
        return compute_client_id(client_name)

    @staticmethod
    def _stable_coordinates(seed: str) -> dict[str, float]:
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
        lat_offset = int(digest[:4], 16) / 65535
        lng_offset = int(digest[4:8], 16) / 65535
        return {
            "lat": 36.8 + (lat_offset - 0.5) * 0.4,
            "lng": 10.18 + (lng_offset - 0.5) * 0.4,
        }
