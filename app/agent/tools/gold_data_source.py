from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from app.agent.tools.text_normalize import normalize_text

_NULLISH = {"", "n/a", "na", "-", "none", "null"}

_ISSUE_KEYWORDS = (
    "probleme",
    "panne",
    "fuite",
    "defectueux",
    "ne fonctionne",
    "reclam",
    "retard livraison",
    "casse",
)
_NEGATION_PATTERNS = (
    "aucun probleme",
    "pas de probleme",
    "aucun defaut",
    "avons trouve aucun",
    "sans probleme",
)


@dataclass
class GoldVisit:
    maintenance_number: str
    client: str | None
    address: str | None
    service_date: date | None
    diffusers: list[dict] = field(default_factory=list)
    issue: str | None = None


def _clean_text(raw: str | None) -> str | None:
    if raw is None:
        return None
    stripped = raw.strip()
    if not stripped or stripped.casefold() in _NULLISH:
        return None
    return stripped


def _clean_int(raw: str | None) -> int | None:
    cleaned = _clean_text(raw)
    if cleaned is None:
        return None
    try:
        return int(float(cleaned))
    except ValueError:
        digits = "".join(character for character in cleaned if character.isdigit())
        return int(digits) if digits else None


def _parse_service_date(raw: str | None) -> date | None:
    cleaned = _clean_text(raw)
    if cleaned is None:
        return None
    try:
        return date.fromisoformat(cleaned)
    except ValueError:
        return None


def _derive_issue(comments: list[str]) -> str | None:
    for comment in comments:
        normalized = normalize_text(comment)
        if any(pattern in normalized for pattern in _NEGATION_PATTERNS):
            continue
        if any(keyword in normalized for keyword in _ISSUE_KEYWORDS):
            return comment
    return None


def load_gold_visits(csv_path: str | Path) -> list[GoldVisit]:
    """Read the gold CSV fresh and group its per-diffuser rows into one
    GoldVisit per maintenance_number (a visit can service several diffuser
    locations, one row each, all sharing the same maintenance_number)."""
    groups: dict[str, dict] = {}
    order: list[str] = []
    with open(csv_path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            maintenance_number = _clean_text(row.get("maintenance_number"))
            if maintenance_number is None:
                continue
            group = groups.get(maintenance_number)
            if group is None:
                group = {
                    "client": _clean_text(row.get("client")),
                    "address": _clean_text(row.get("address")),
                    "service_date": _parse_service_date(row.get("service_date")),
                    "diffusers": [],
                    "comments": [],
                }
                groups[maintenance_number] = group
                order.append(maintenance_number)
            if group["client"] is None:
                group["client"] = _clean_text(row.get("client"))
            if group["address"] is None:
                group["address"] = _clean_text(row.get("address"))
            if group["service_date"] is None:
                group["service_date"] = _parse_service_date(row.get("service_date"))
            comment = _clean_text(row.get("commentaire"))
            if comment is not None:
                group["comments"].append(comment)
            group["diffusers"].append(
                {
                    "model": _clean_text(row.get("model_diffuseur")),
                    "emplacement": _clean_text(row.get("emplacement")),
                    "quantity_ml": _clean_int(row.get("qte_restante")),
                }
            )

    return [
        GoldVisit(
            maintenance_number=maintenance_number,
            client=groups[maintenance_number]["client"],
            address=groups[maintenance_number]["address"],
            service_date=groups[maintenance_number]["service_date"],
            diffusers=groups[maintenance_number]["diffusers"],
            issue=_derive_issue(groups[maintenance_number]["comments"]),
        )
        for maintenance_number in order
    ]
