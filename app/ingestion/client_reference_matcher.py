from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

REFERENCE_CSV_PATH = Path("data/Fiche de Aromair - Sheet1.csv")
MIN_REFERENCE_MATCH_SCORE = 0.55


@dataclass(frozen=True)
class ClientReference:
    client_name: str | None = None
    perfume: str | None = None
    address: str | None = None
    diffuser_model: str | None = None
    diffuser_ref: str | None = None
    technician_name: str | None = None
    emplacement: str | None = None
    bottle_reference: str | None = None


@dataclass(frozen=True)
class ClientReferenceMatch:
    reference: ClientReference
    score: float
    client_score: float
    address_score: float


def clean_text(value: object) -> str | None:
    if value is None:
        return None
    text = maybe_fix_text(str(value)) or str(value).strip()
    text = text.strip().strip('"').strip()
    return text or None


def maybe_fix_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    if "Ãƒ" in text or "Ã‚" in text:
        try:
            repaired = text.encode("latin1").decode("utf-8")
            return repaired.strip()
        except (UnicodeEncodeError, UnicodeDecodeError):
            return text
    return text


def normalize_header(value: str | None) -> str:
    text = clean_text(value) or ""
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def normalize_for_match(value: str | None) -> str:
    text = clean_text(value) or ""
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def similarity_score(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    if left in right or right in left:
        return 0.9
    return SequenceMatcher(None, left, right).ratio()


def extract_numeric_key(value: str) -> str:
    match = re.search(r"\d+", value)
    return match.group(0) if match else ""


def load_client_references(csv_path: Path = REFERENCE_CSV_PATH) -> list[ClientReference]:
    if not csv_path.exists():
        return []

    references: list[ClientReference] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as file_handle:
        reader = csv.DictReader(file_handle)
        for row in reader:
            normalized_row = {normalize_header(key): clean_text(value) for key, value in row.items()}
            references.append(
                ClientReference(
                    client_name=normalized_row.get("liste_des_clients"),
                    perfume=normalized_row.get("liste_des_parfums"),
                    address=normalized_row.get("liste_des_adresses"),
                    diffuser_model=normalized_row.get("liste_des_modeles_diffuseurs"),
                    diffuser_ref=normalized_row.get("liste_des_ref"),
                    technician_name=normalized_row.get("liste_des_noms_des_techniciens"),
                    emplacement=normalized_row.get("liste_des_emplacements"),
                    bottle_reference=normalized_row.get("liste_des_references_bouteilles"),
                )
            )
    return references


@lru_cache(maxsize=1)
def get_client_references() -> tuple[ClientReference, ...]:
    return tuple(load_client_references())


def match_client_reference(
    client_name: str | None,
    address: str | None,
    references: list[ClientReference] | tuple[ClientReference, ...] | None = None,
) -> ClientReferenceMatch | None:
    client_key = normalize_for_match(client_name)
    address_key = normalize_for_match(address)
    if not client_key and not address_key:
        return None

    numeric_client_key = extract_numeric_key(client_key)
    numeric_mode = bool(numeric_client_key)
    candidates = references if references is not None else get_client_references()
    best_match: ClientReference | None = None
    best_score = 0.0
    best_client_score = 0.0
    best_address_score = 0.0

    for reference in candidates:
        ref_client = normalize_for_match(reference.client_name)
        ref_address = normalize_for_match(reference.address)
        client_score = similarity_score(client_key, ref_client)
        address_score = similarity_score(address_key, ref_address)
        score = (client_score * 0.75) + (address_score * 0.25)

        if numeric_mode:
            numeric_reference_key = extract_numeric_key(ref_client)
            numeric_client_score = similarity_score(numeric_client_key, numeric_reference_key)
            score = max(score, (numeric_client_score * 0.4) + (address_score * 0.6))

        if score > best_score:
            best_score = score
            best_match = reference
            best_client_score = client_score
            best_address_score = address_score

    if best_match is None:
        return None

    if numeric_mode:
        if best_score < MIN_REFERENCE_MATCH_SCORE or best_address_score < 0.15:
            return None
    elif best_score < 0.72 or best_address_score < 0.2:
        return None

    return ClientReferenceMatch(
        reference=best_match,
        score=best_score,
        client_score=best_client_score,
        address_score=best_address_score,
    )
