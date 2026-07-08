from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from app.ingestion.normalize import normalize_scalar


CATALOG_PATH = Path("data/raw_json/List_of_diffusers/list_diffusers.json")
SURFACE_RE = re.compile(r"\b(\d{2,4})\s*(m2|m²|metres? carres?|metres? carrés?)\b", re.IGNORECASE)


def recommend_products(query: str, limit: int = 3) -> list[str]:
    normalized_query = _normalize_text(query)
    surface = _extract_surface(query)
    ranked: list[tuple[int, str]] = []
    for item in _load_catalog():
        product = str(item.get("produit") or "").strip()
        if not product:
            continue
        score = 0
        ideal_for = [_normalize_text(str(value)) for value in item.get("ideal_pour", [])]
        argument = _normalize_text(str(item.get("argument_commercial") or ""))
        coverage = _extract_surface(str(item.get("couverture") or ""))

        for term in ideal_for:
            if term and term in normalized_query:
                score += 3
        if surface is not None and coverage is not None:
            if coverage >= surface:
                score += 3
                if coverage - surface <= 100:
                    score += 1
            else:
                score -= 2
        if "premium" in normalized_query or "luxe" in normalized_query or "luxueux" in normalized_query:
            if "premium" in argument or "lux" in argument or "haut de gamme" in argument:
                score += 2
        if score > 0:
            ranked.append((score, product))

    ordered = [name for _, name in sorted(ranked, key=lambda item: (-item[0], item[1]))]
    deduped: list[str] = []
    for name in ordered:
        if name not in deduped:
            deduped.append(name)
    return deduped[:limit]


def _load_catalog() -> list[dict]:
    if not CATALOG_PATH.exists():
        return []
    payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    normalized = normalize_scalar(payload)
    return [item for item in normalized if isinstance(item, dict)]


def _extract_surface(text: str) -> int | None:
    match = SURFACE_RE.search(text)
    if not match:
        return None
    return int(match.group(1))


def _normalize_text(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_text.lower().split())
