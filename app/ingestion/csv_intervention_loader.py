from __future__ import annotations

import csv
import re
from dataclasses import dataclass, replace
from pathlib import Path

from app.ingestion.client_reference_matcher import match_client_reference
from app.ingestion.normalize import build_fiche_id, parse_service_date
from schemas.fiche_schema import (
    DiffuserControl,
    FicheSchema,
    MaintenanceDetails,
    ProblemRecommendation,
)

EXPECTED_HEADER = [
    "N_Fiche",
    "Client",
    "Adresse",
    "Date",
    "Technicien",
    "Modele_Diffuseur",
    "Emplacement",
    "Quantite_Livree",
    "Nom_Parfum",
    "Observations",
    "Column1",
]

_DATE_PATTERN = re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4}$")


@dataclass(frozen=True)
class InterventionRow:
    n_fiche: str
    client: str | None
    address: str | None
    date_raw: str | None
    technician_name: str | None
    model_diffuseur: str | None
    emplacement: str | None
    quantite_livree: str | None
    nom_parfum: str | None
    observations: str | None


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _looks_like_free_text(value: str) -> bool:
    return len(value) > 20 and " " in value


def _repair_misplaced_note(row: InterventionRow) -> InterventionRow:
    """Some source rows omit one empty column when no diffuser was touched,
    which shifts a free-text delivery/pickup note into Nom_Parfum instead of
    Observations. Detect it (long sentence, no other diffuser fields) and
    move it back rather than recording it as a fake perfume name."""
    if (
        row.nom_parfum
        and not row.observations
        and not row.model_diffuseur
        and not row.emplacement
        and not row.quantite_livree
        and _looks_like_free_text(row.nom_parfum)
    ):
        return replace(row, nom_parfum=None, observations=row.nom_parfum)
    return row


def _realign_row(raw_fields: list[str]) -> list[str]:
    """Repair rows whose Adresse contains an unescaped comma (e.g. "Kantaoui,
    Sousse"), which shifts every later column by one for that row. Locates the
    date-shaped field and treats everything between Client and it as Adresse."""
    header_len = len(EXPECTED_HEADER)
    date_index = None
    for index in range(3, len(raw_fields)):
        if _DATE_PATTERN.match(raw_fields[index].strip()):
            date_index = index
            break

    if date_index is None or date_index == 3:
        fields = raw_fields[:header_len]
        return fields + [""] * (header_len - len(fields))

    address = ", ".join(part.strip() for part in raw_fields[2:date_index] if part.strip())
    realigned = raw_fields[:2] + [address, raw_fields[date_index]] + raw_fields[date_index + 1 :]

    if len(realigned) > header_len:
        head = realigned[: header_len - 1]
        tail = realigned[header_len - 1 :]
        observations = ", ".join(part.strip() for part in tail if part.strip())
        return head + [observations]
    return realigned + [""] * (header_len - len(realigned))


def parse_intervention_csv(path: str | Path) -> list[InterventionRow]:
    csv_path = Path(path)
    rows: list[InterventionRow] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        next(reader, None)  # header
        for raw_fields in reader:
            if not raw_fields or not any(field.strip() for field in raw_fields):
                continue
            fields = _realign_row(list(raw_fields))
            row = InterventionRow(
                n_fiche=_clean(fields[0]) or "",
                client=_clean(fields[1]),
                address=_clean(fields[2]),
                date_raw=_clean(fields[3]),
                technician_name=_clean(fields[4]),
                model_diffuseur=_clean(fields[5]),
                emplacement=_clean(fields[6]),
                quantite_livree=_clean(fields[7]),
                nom_parfum=_clean(fields[8]),
                observations=_clean(fields[9]),
            )
            rows.append(_repair_misplaced_note(row))
    return [row for row in rows if row.n_fiche]


GroupKey = tuple[str, str, str, str]


def group_rows_by_fiche(rows: list[InterventionRow]) -> dict[GroupKey, list[InterventionRow]]:
    """Group rows into visits. N_Fiche alone is not a reliable unique key in this
    export - the same number is occasionally reused across two unrelated visits
    (different client/address/date), so the grouping key also includes those
    fields to avoid silently merging two different clients' history into one fiche."""
    groups: dict[GroupKey, list[InterventionRow]] = {}
    for row in rows:
        key = (row.n_fiche, row.client or "", row.address or "", row.date_raw or "")
        groups.setdefault(key, []).append(row)
    return groups


def build_fiche_from_group(
    source_file: Path,
    n_fiche: str,
    page_key: str,
    rows: list[InterventionRow],
) -> FicheSchema:
    first = rows[0]
    reference_match = match_client_reference(first.client, first.address)
    client_name = (
        reference_match.reference.client_name
        if reference_match and reference_match.reference.client_name
        else first.client
    )
    technician_name = next((row.technician_name for row in rows if row.technician_name), None)

    maintenance_details = MaintenanceDetails(
        client=client_name,
        address=first.address,
        date_raw=first.date_raw,
        technician_name=technician_name,
        client_maintenance_number=n_fiche,
    )
    maintenance_details.service_date = parse_service_date(first.date_raw)

    diffusers = [
        DiffuserControl(
            model_diffuseur_raw=row.model_diffuseur,
            model_diffuseur=row.model_diffuseur,
            emplacement=row.emplacement,
            nom_parfum=row.nom_parfum,
            qte_parfum_existante_raw=row.quantite_livree,
            qte_parfum_existante=row.quantite_livree,
        )
        for row in rows
        if row.model_diffuseur or row.emplacement or row.nom_parfum or row.quantite_livree
    ]

    observations = [row.observations for row in rows if row.observations]
    problem = ProblemRecommendation(
        probleme_rencontree_raw="; ".join(dict.fromkeys(observations)) or None,
    )

    fiche_id = build_fiche_id(source_file=source_file, page_key=page_key, maintenance_number=n_fiche)

    return FicheSchema(
        fiche_id=fiche_id,
        source_file=str(source_file),
        page_key=page_key,
        document_type="client_maintenance_form",
        maintenance_details=maintenance_details,
        controle_diffuseur_recharge=diffusers,
        probleme_recommandation=problem,
        raw_payload={"source_format": "csv_intervention_export", "row_count": len(rows)},
    )


def load_fiches_from_csv(path: str | Path) -> list[FicheSchema]:
    source_file = Path(path)
    rows = parse_intervention_csv(source_file)
    groups = group_rows_by_fiche(rows)

    occurrences: dict[str, int] = {}
    for (n_fiche, *_rest) in groups:
        occurrences[n_fiche] = occurrences.get(n_fiche, 0) + 1

    seen: dict[str, int] = {}
    fiches: list[FicheSchema] = []
    for (n_fiche, *_rest), group_rows in groups.items():
        if occurrences[n_fiche] > 1:
            seen[n_fiche] = seen.get(n_fiche, 0) + 1
            page_key = f"n_fiche_{n_fiche}-{seen[n_fiche]}"
        else:
            page_key = f"n_fiche_{n_fiche}"
        fiches.append(build_fiche_from_group(source_file, n_fiche, page_key, group_rows))
    return fiches
