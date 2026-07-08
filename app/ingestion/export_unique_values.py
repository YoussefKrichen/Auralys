from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from app.config import settings
from app.ingestion.normalize import load_fiches_from_directory


def collect_unique_values(
    processed_data_dir: str | None = None,
) -> dict[str, object]:
    source_dir = Path(processed_data_dir or settings.processed_data_dir)

    fiches = load_fiches_from_directory(source_dir)
    unique_clients: dict[str, str] = {}
    unique_addresses: dict[str, str] = {}
    unique_emplacements: dict[str, str] = {}

    for fiche in fiches:
        if fiche.document_type == "client_maintenance_form":
            _store_unique(unique_clients, fiche.maintenance_details.client, kind="client")
        _store_unique(unique_addresses, fiche.maintenance_details.address)

        for control in fiche.controle_diffuseur_recharge:
            _store_unique(unique_emplacements, control.emplacement)
        for recharge in fiche.recharge_bouteille_effectuee:
            _store_unique(unique_emplacements, recharge.emplacement)

    return {
        "source_dir": str(source_dir),
        "counts": {
            "clients": len(unique_clients),
            "addresses": len(unique_addresses),
            "emplacements": len(unique_emplacements),
        },
        "clients": _sorted_values(unique_clients),
        "addresses": _sorted_values(unique_addresses),
        "emplacements": _sorted_values(unique_emplacements),
    }


def export_unique_values(
    processed_data_dir: str | None = None,
    output_path: str | Path | None = None,
) -> dict[str, object]:
    payload = collect_unique_values(processed_data_dir=processed_data_dir)
    destination = Path(output_path or "data/unique_reference_values.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        "source_dir": payload["source_dir"],
        "output_path": str(destination),
        **payload["counts"],
    }


def _store_unique(bucket: dict[str, str], value: str | None, *, kind: str = "default") -> None:
    cleaned = _clean_value(value)
    if not cleaned:
        return
    if kind == "client":
        cleaned = _normalize_client_name(cleaned)
    key = _dedupe_key(cleaned)
    if key not in bucket:
        bucket[key] = cleaned


def _clean_value(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"\s+", " ", value).strip()
    if not cleaned or cleaned in {"-", "/", "N/A", "n/a"}:
        return None
    return cleaned


def _normalize_client_name(value: str) -> str:
    if value.startswith("knowledge:"):
        return value
    normalized = re.sub(r"[^\W\d_]+", lambda match: _capitalize_word(match.group(0)), value, flags=re.UNICODE)
    return _apply_client_aliases(normalized)


def _capitalize_word(word: str) -> str:
    return word[:1].upper() + word[1:].lower()


def _apply_client_aliases(value: str) -> str:
    csv_alias = _csv_client_aliases().get(_dedupe_key(value))
    if csv_alias:
        return csv_alias
    alias_key = re.sub(r"[^a-z0-9]+", "", value.casefold())
    if alias_key.startswith("edward"):
        return "Edwards"
    if alias_key == "arumair":
        return "Aromair"
    return value


@lru_cache(maxsize=1)
def _csv_client_aliases() -> dict[str, str]:
    alias_path = Path("data/client_name_aliases.json")
    if not alias_path.exists():
        return {}
    payload = json.loads(alias_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    aliases: dict[str, str] = {}
    for source, target in payload.items():
        cleaned_source = _clean_value(source)
        cleaned_target = _clean_value(target)
        if not cleaned_source or not cleaned_target:
            continue
        aliases[_dedupe_key(cleaned_source)] = cleaned_target
    return aliases


def _dedupe_key(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _sorted_values(bucket: dict[str, str]) -> list[str]:
    return sorted(bucket.values(), key=lambda item: item.casefold())
