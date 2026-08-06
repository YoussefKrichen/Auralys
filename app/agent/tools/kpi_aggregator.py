from __future__ import annotations

import calendar
import csv
import re
import statistics
import unicodedata
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

REPORT_PERIODS = ("day", "week", "month", "year")

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


def resolve_period_range(period: str, anchor: date) -> tuple[date, date]:
    """Turn a period keyword + anchor date into an inclusive (start, end) range.

    "week" follows the ISO convention (Monday->Sunday) since that's the
    convention already used for service planning elsewhere in the app.
    """
    if period == "day":
        return anchor, anchor
    if period == "week":
        start = anchor - timedelta(days=anchor.weekday())
        return start, start + timedelta(days=6)
    if period == "month":
        start = anchor.replace(day=1)
        last_day = calendar.monthrange(anchor.year, anchor.month)[1]
        return start, anchor.replace(day=last_day)
    if period == "year":
        return date(anchor.year, 1, 1), date(anchor.year, 12, 31)
    raise ValueError(f"Unsupported report period: {period!r}. Expected one of {REPORT_PERIODS}.")


def format_period_label(period: str, start: date, end: date) -> str:
    if period == "day":
        return _format_date_fr(start)
    if period == "week":
        return f"Semaine du {_format_date_fr(start)} au {_format_date_fr(end)}"
    if period == "month":
        return f"{_MONTH_LONG_FR[start.month].capitalize()} {start.year}"
    if period == "year":
        return str(start.year)
    raise ValueError(f"Unsupported report period: {period!r}. Expected one of {REPORT_PERIODS}.")


_MONTH_NAME_TO_NUM = {
    # French
    "janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12,
    # English -- the CEO chat sees both languages in practice.
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}
_WEEK_KEYWORDS = ("semaine", "week")
_MONTH_KEYWORDS = ("mois", "month")
_YEAR_KEYWORDS = ("annee", "year")
_DAY_KEYWORDS = ("jour", "day", "aujourd'hui", "today")
_LAST_KEYWORDS = ("dernier", "derniere", "last")

_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_EXPLICIT_DATE_RE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-]((?:19|20)\d{2})\b")


def parse_period_from_text(text: str, *, today: date) -> tuple[str, date] | None:
    """Best-effort extraction of a (period, anchor) pair from a free-form report request.

    Handles the phrasing the CEO chat actually sees: an explicit dd/mm/yyyy date, a
    month name (FR or EN) with an optional year, a bare year, or a period keyword
    ("semaine"/"week", optionally with "dernier"/"last"). Returns None when the
    message doesn't reference any period at all, so the caller can fall back to
    its own default instead of guessing.
    """
    normalized = _normalize_report_text(text)
    period_keyword = _detect_period_keyword(normalized)
    is_last = _contains_any(normalized, _LAST_KEYWORDS)

    explicit_date = _EXPLICIT_DATE_RE.search(normalized)
    if explicit_date:
        day, month, year = (int(part) for part in explicit_date.groups())
        try:
            anchor = date(year, month, day)
        except ValueError:
            anchor = None
        if anchor is not None:
            return period_keyword or "day", anchor

    month_num = _find_month_name(normalized)
    year_match = _YEAR_RE.search(normalized)

    if month_num is not None:
        year = int(year_match.group()) if year_match else today.year
        period = period_keyword or "month"
        if period == "week" and is_last:
            anchor = date(year, month_num, calendar.monthrange(year, month_num)[1])
        elif period == "year":
            anchor = date(year, 1, 1)
        else:
            anchor = date(year, month_num, 1)
        return period, anchor

    if year_match:
        year = int(year_match.group())
        period = period_keyword or "year"
        anchor = date(year, 1, 1) if period == "year" else date(year, today.month, 1)
        return period, anchor

    if period_keyword is not None:
        return period_keyword, today

    return None


def _detect_period_keyword(normalized: str) -> str | None:
    if _contains_any(normalized, _WEEK_KEYWORDS):
        return "week"
    if _contains_any(normalized, _MONTH_KEYWORDS):
        return "month"
    if _contains_any(normalized, _YEAR_KEYWORDS):
        return "year"
    if _contains_any(normalized, _DAY_KEYWORDS):
        return "day"
    return None


def _find_month_name(normalized: str) -> int | None:
    for name, num in _MONTH_NAME_TO_NUM.items():
        if re.search(rf"\b{name}\b", normalized):
            return num
    return None


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    # Word-boundary match, not plain substring -- "jour" is a substring of
    # "bonjour" and would otherwise misfire on an ordinary greeting.
    return any(re.search(rf"\b{re.escape(keyword)}\b", text) for keyword in keywords)


def _normalize_report_text(value: str) -> str:
    lowered = value.strip().lower()
    ascii_text = unicodedata.normalize("NFKD", lowered).encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_text.split())


def compute_kpis(
    csv_path: str | Path,
    *,
    start: date | None = None,
    end: date | None = None,
) -> dict[str, Any]:
    """Aggregate the gold intervention CSV into CEO-facing KPIs.

    Passing start/end restricts the aggregation to a single reporting period
    (see resolve_period_range) instead of the full history -- rows with no
    parseable service_date are excluded when a range is given, since there's
    no way to tell which period they'd belong to.
    """
    with open(csv_path, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    def _row_date_precheck(row: dict[str, Any]) -> date | None:
        cleaned = _clean_text(row.get("service_date"))
        return date.fromisoformat(cleaned) if cleaned else None

    if start is not None or end is not None:
        rows = [
            row
            for row in rows
            if (row_date := _row_date_precheck(row)) is not None
            and (start is None or row_date >= start)
            and (end is None or row_date <= end)
        ]

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
