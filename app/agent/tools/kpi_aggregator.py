from __future__ import annotations

import csv
import re
import statistics
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

_NULLISH = {"", "n/a", "na", "-", "none", "null"}
_SOURCE_BUCKETS = ("Controle", "Recharge", "Visite", "Livraison")
_MIN_DIFFUSEUR_CLIENTS = 5
_TOP_N = 5

_MONTH_ABBR_FR = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Avr", 5: "Mai", 6: "Jun",
    7: "Jul", 8: "Aou", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}
_MONTH_LONG_FR = {
    1: "janv.", 2: "fevr.", 3: "mars", 4: "avr.", 5: "mai", 6: "juin",
    7: "juil.", 8: "aout", 9: "sept.", 10: "oct.", 11: "nov.", 12: "dec.",
}

_PLACE_LETTER_DIGIT = re.compile(r"([A-Za-z])(\d)")


def _clean_text(raw: str | None) -> str | None:
    if raw is None:
        return None
    stripped = raw.strip()
    if not stripped or stripped.casefold() in _NULLISH:
        return None
    return stripped


def _clean_int(raw: str | None) -> int:
    cleaned = _clean_text(raw)
    if cleaned is None:
        return 0
    try:
        return int(float(cleaned))
    except ValueError:
        return 0


def _normalize_place(name: str) -> str:
    # Source data mixes "Lac1" and "Lac 1" for the same zone; treat them as
    # one bucket instead of splitting a city's count across two rows.
    return _PLACE_LETTER_DIGIT.sub(r"\1 \2", " ".join(name.split()))


def _format_date_fr(value: date) -> str:
    return f"{value.day} {_MONTH_LONG_FR[value.month]} {value.year % 100:02d}"


def compute_kpis(csv_path: str | Path) -> dict[str, Any]:
    with open(csv_path, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    total_interventions = len(rows)

    def _row_date(row: dict[str, Any]) -> date | None:
        cleaned = _clean_text(row.get("service_date"))
        return date.fromisoformat(cleaned) if cleaned else None

    service_dates = sorted(d for d in (_row_date(row) for row in rows) if d is not None)
    period = {
        "start": _format_date_fr(service_dates[0]) if service_dates else None,
        "end": _format_date_fr(service_dates[-1]) if service_dates else None,
    }

    client_counts: Counter[str] = Counter()
    client_emplacements: dict[str, set[str]] = defaultdict(set)
    model_clients: dict[str, set[str]] = defaultdict(set)
    model_volume: Counter[str] = Counter()
    source_counter: Counter[str] = Counter()
    month_counts: Counter[tuple[int, int]] = Counter()
    year_stats: dict[str, dict[str, Any]] = defaultdict(lambda: {"total": 0, "months": set()})
    parfum_counter: Counter[str] = Counter()
    place_counter: Counter[str] = Counter()
    volume_livre = 0

    for row in rows:
        client = _clean_text(row.get("client"))
        qte_livree = _clean_int(row.get("qte_livree"))
        volume_livre += qte_livree

        if client:
            client_counts[client] += 1
            emplacement = _clean_text(row.get("emplacement"))
            if emplacement:
                client_emplacements[client].add(emplacement)

        model = _clean_text(row.get("model_diffuseur"))
        if model:
            if client:
                model_clients[model].add(client)
            model_volume[model] += qte_livree

        source = _clean_text(row.get("source")) or "Autres"
        source_counter[source if source in _SOURCE_BUCKETS else "Autres"] += 1

        parsed_date = _row_date(row)
        if parsed_date is not None:
            month_counts[(parsed_date.year, parsed_date.month)] += 1

        reference_year = _clean_text(row.get("reference_year"))
        if reference_year:
            year_stats[reference_year]["total"] += 1
            if parsed_date is not None:
                year_stats[reference_year]["months"].add(parsed_date.month)

        parfum = _clean_text(row.get("parfum"))
        if parfum:
            parfum_counter[parfum] += 1

        place = _clean_text(row.get("address"))
        if place:
            place_counter[_normalize_place(place)] += 1

    total_clients = len(client_counts)
    median_raw = statistics.median(client_counts.values()) if client_counts else 0
    median_interventions_per_client = int(median_raw) if median_raw == int(median_raw) else round(median_raw, 1)

    top_clients = [{"name": name, "count": count} for name, count in client_counts.most_common(_TOP_N)]

    min_count = min(client_counts.values()) if client_counts else 0
    least_active = sorted(name for name, count in client_counts.items() if count == min_count)
    bottom_clients = [{"name": name, "count": min_count} for name in least_active[:_TOP_N]]
    bottom_clients_note = (
        f"{len(least_active)} clients sur {total_clients} "
        f"({round(len(least_active) / total_clients * 100, 1) if total_clients else 0} %) "
        "n'ont eu qu'une seule intervention sur toute la periode - l'echantillon ci-dessus "
        "est pris parmi eux, tous strictement ex-aequo."
        if min_count == 1
        else f"{len(least_active)} clients sur {total_clients} sont a egalite avec {min_count} intervention(s), le minimum observe."
    )

    diffuseurs_by_clients = sorted(
        (
            {"model": model, "clients": len(clients)}
            for model, clients in model_clients.items()
            if len(clients) >= _MIN_DIFFUSEUR_CLIENTS
        ),
        key=lambda row: (-row["clients"], row["model"]),
    )

    top_volume_model, top_volume_units = max(model_volume.items(), key=lambda item: item[1], default=(None, 0))
    diffuseur_extreme_note = ""
    if top_volume_model:
        formatted_units = f"{top_volume_units:,}".replace(",", " ")
        diffuseur_extreme_note = (
            "Classement par adoption client (un client compte une seule fois). Trie par volume de parfum "
            f"livre, {top_volume_model} arrive en tete avec {formatted_units} unites - proxy commercial "
            "faute de champ prix dans les donnees."
        )

    total_sources = sum(source_counter.values()) or 1
    source_breakdown = [
        {"label": label, "pct": round(count / total_sources * 100, 1)}
        for label, count in source_counter.most_common()
    ]

    monthly_trend = []
    if service_dates:
        cursor_year, cursor_month = service_dates[0].year, service_dates[0].month
        end_year, end_month = service_dates[-1].year, service_dates[-1].month
        while (cursor_year, cursor_month) <= (end_year, end_month):
            count = month_counts.get((cursor_year, cursor_month), 0)
            monthly_trend.append(
                {
                    "label": f"{_MONTH_ABBR_FR[cursor_month]} {cursor_year % 100:02d}",
                    "count": count,
                    "has_data": count > 0,
                }
            )
            cursor_month += 1
            if cursor_month > 12:
                cursor_month = 1
                cursor_year += 1

    year_rhythm = {}
    for year_key, stats in sorted(year_stats.items()):
        months_covered = len(stats["months"]) or 1
        year_rhythm[f"y{year_key}"] = {
            "total": stats["total"],
            "months_covered": len(stats["months"]),
            "per_month": round(stats["total"] / months_covered, 1),
        }

    parfums_top = [{"name": name, "count": count} for name, count in parfum_counter.most_common(_TOP_N)]
    villes_top = [{"name": name, "count": count} for name, count in place_counter.most_common(_TOP_N)]

    top_diffuser_owners = sorted(
        ({"name": client, "count": len(emplacements)} for client, emplacements in client_emplacements.items()),
        key=lambda row: (-row["count"], row["name"]),
    )[:_TOP_N]

    return {
        "period": period,
        "totals": {
            "interventions": total_interventions,
            "clients": total_clients,
            "volume_livre": volume_livre,
            "median_interventions_per_client": median_interventions_per_client,
        },
        "top_clients": top_clients,
        "bottom_clients": bottom_clients,
        "bottom_clients_note": bottom_clients_note,
        "diffuseurs_by_clients": diffuseurs_by_clients,
        "diffuseur_extreme_note": diffuseur_extreme_note,
        "source_breakdown": source_breakdown,
        "monthly_trend": monthly_trend,
        "year_rhythm": year_rhythm,
        "parfums_top": parfums_top,
        "villes_top": villes_top,
        "top_diffuser_owners": top_diffuser_owners,
    }
