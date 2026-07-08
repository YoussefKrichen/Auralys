from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ingestion.client_reference_matcher import (
    ClientReference,
    clean_text,
    load_client_references,
    match_client_reference,
    normalize_header,
)
from app.ingestion.normalize import load_fiches_from_file, maybe_fix_text


ROOT_DIR = Path(__file__).resolve().parents[1]
INPUT_DIR_CANDIDATES = [
    ROOT_DIR / "data" / "processed" / "Maintenance",
    ROOT_DIR / "data" / "processed" / "maintenance",
]
OUTPUT_DIR = ROOT_DIR / "data" / "processed" / "Maintenance_txt"
CLIENT_CSV_PATH = ROOT_DIR / "data" / "Fiche de Aromair - Sheet1.csv"


def main() -> None:
    input_dir = resolve_input_dir()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    references = load_client_references(CLIENT_CSV_PATH)

    exported = 0
    for json_path in sorted(input_dir.glob("*.json")):
        try:
            fiches = load_fiches_from_file(json_path)
        except Exception as exc:
            write_error_file(json_path, exc)
            exported += 1
            continue

        if not fiches:
            write_text_file(json_path.stem, "Aucune donnee exploitable trouvee.")
            exported += 1
            continue

        fiche = fiches[0]
        reference_match = match_client_reference(
            fiche.maintenance_details.client,
            fiche.maintenance_details.address,
            references,
        )
        content = render_fiche_text(
            fiche.model_dump(mode="json"),
            reference_match.reference if reference_match else None,
        )
        write_text_file(json_path.stem, content)
        exported += 1

    print(f"Exported {exported} TXT files to {OUTPUT_DIR}")


def resolve_input_dir() -> Path:
    for candidate in INPUT_DIR_CANDIDATES:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("No maintenance input directory found under data/processed.")

def render_fiche_text(payload: dict[str, Any], reference: ClientReference | None) -> str:
    maintenance = payload.get("maintenance_details") or {}
    service_type = payload.get("service_type") or {}
    controls = payload.get("controle_diffuseur_recharge") or []
    recharges = payload.get("recharge_bouteille_effectuee") or []
    problems = payload.get("probleme_recommandation") or {}
    signature = payload.get("signature_cachet") or {}

    lines: list[str] = []
    add_section(lines, "Client")
    add_field(lines, "Nom du client", maintenance.get("client"))
    add_field(lines, "Adresse", maintenance.get("address"))
    phone = extract_phone(signature.get("text"))
    add_field(lines, "Telephone", phone)
    if reference:
        add_field(lines, "Correspondance client", reference.client_name)
        add_field(lines, "Adresse correspondante", reference.address)
        add_field(lines, "Parfum reference", reference.perfume)
        add_field(lines, "Modele diffuseur reference", reference.diffuser_model)
        add_field(lines, "Reference diffuseur", reference.diffuser_ref)
        add_field(lines, "Emplacement reference", reference.emplacement)
        add_field(lines, "Reference bouteille", reference.bottle_reference)
        add_field(lines, "Technicien reference", reference.technician_name)

    add_blank_line(lines)
    add_section(lines, "Intervention")
    add_field(lines, "Date", maintenance.get("service_date") or maintenance.get("date_raw"))
    add_field(lines, "Technicien", maintenance.get("technician_name"))
    add_field(lines, "Reference / numero", maintenance.get("client_maintenance_number"))
    service_labels = [name for name, value in service_type.items() if value]
    add_field(lines, "Type de service", ", ".join(service_labels) if service_labels else None)

    add_blank_line(lines)
    add_section(lines, "Presence des sections")
    lines.append(
        f"Contient controle_diffuseur_recharge: {'oui' if has_non_empty_entries(controls) else 'non'}"
    )
    lines.append(
        f"Contient recharge_bouteille_effectuee: {'oui' if has_non_empty_entries(recharges) else 'non'}"
    )

    add_blank_line(lines)
    add_section(lines, "Controle diffuseur recharge")
    if has_non_empty_entries(controls):
        for index, control in enumerate(controls, start=1):
            lines.append(f"Diffuseur {index}:")
            add_indented_field(lines, "Modele", pick_first(control, "model_diffuseur", "model_diffuseur_raw"))
            add_indented_field(
                lines,
                "CAB diffuseur",
                pick_first(control, "reference_diffuseur", "reference_diffuseur_raw"),
            )
            add_indented_field(lines, "Emplacement", control.get("emplacement"))
            add_indented_field(lines, "Statut", control.get("en_marche_arret"))
            add_indented_field(lines, "Qualite diffusion", control.get("qualite_diffusion"))
            add_indented_field(lines, "Fuite", control.get("fuite"))
            add_indented_field(lines, "Parfum", control.get("nom_parfum"))
            add_indented_field(
                lines,
                "CAB bouteille",
                pick_first(control, "reference_bouteille", "reference_bouteille_raw"),
            )
            add_indented_field(
                lines,
                "Quantite existante",
                pick_first(control, "qte_parfum_existante", "qte_parfum_existante_raw"),
            )
            add_indented_field(lines, "Programme frequence", control.get("frequence_diffusion_existante"))
            add_indented_field(lines, "Programme plage horaire", control.get("plage_horaire_diffusion"))
            add_indented_field(lines, "Remarques", control.get("motif_arret"))
    else:
        lines.append("Aucun controle diffuseur mentionne.")

    add_blank_line(lines)
    add_section(lines, "Recharge bouteille effectuee")
    if has_non_empty_entries(recharges):
        for index, recharge in enumerate(recharges, start=1):
            lines.append(f"Bouteille {index}:")
            add_indented_field(
                lines,
                "CAB bouteille",
                pick_first(recharge, "reference_bouteille", "reference_bouteille_raw"),
            )
            add_indented_field(lines, "Parfum", recharge.get("parfum"))
            quantity = recharge.get("ml")
            add_indented_field(lines, "Quantite", f"{quantity} ml" if quantity not in (None, "") else None)
            add_indented_field(lines, "Emplacement", recharge.get("emplacement"))
            add_indented_field(lines, "Recharge / remplacement", recharge.get("frequence_diffusion"))
            add_indented_field(
                lines,
                "Programme / plage horaire",
                recharge.get("plage_horaire_fonctionnement"),
            )
    else:
        lines.append("Aucune recharge bouteille mentionnee.")

    add_blank_line(lines)
    add_section(lines, "Problemes et recommandations")
    problem_lines = [
        format_problem_line("Problemes", problems.get("probleme_rencontree_raw")),
        format_problem_line("Anomalies", problems.get("probleme_rencontree_code")),
        format_problem_line("Recommandations", problems.get("solution_proposee")),
    ]
    problem_lines = [line for line in problem_lines if line]
    if problem_lines:
        lines.extend(problem_lines)
    else:
        lines.append("Aucun probleme ou recommandation mentionne.")

    return "\n".join(trim_trailing_blank_lines(lines)).strip() + "\n"


def has_non_empty_entries(entries: list[dict[str, Any]]) -> bool:
    for entry in entries:
        if isinstance(entry, dict) and any(clean_text(value) for value in entry.values()):
            return True
    return False


def pick_first(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = payload.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def extract_phone(value: str | None) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    matches = re.findall(r"\+?\d[\d\s\-]{5,}\d", text)
    if not matches:
        return None
    return " | ".join(" ".join(match.split()) for match in matches)


def add_section(lines: list[str], title: str) -> None:
    lines.append(title)
    lines.append("=" * len(title))


def add_field(lines: list[str], label: str, value: Any) -> None:
    cleaned = clean_text(value)
    if cleaned:
        lines.append(f"{label}: {cleaned}")


def add_indented_field(lines: list[str], label: str, value: Any) -> None:
    cleaned = clean_text(value)
    if cleaned:
        lines.append(f"  - {label}: {cleaned}")


def add_blank_line(lines: list[str]) -> None:
    if lines and lines[-1] != "":
        lines.append("")


def format_problem_line(label: str, value: Any) -> str | None:
    cleaned = clean_text(value)
    if not cleaned:
        return None
    return f"{label}: {cleaned}"


def trim_trailing_blank_lines(lines: list[str]) -> list[str]:
    trimmed = list(lines)
    while trimmed and trimmed[-1] == "":
        trimmed.pop()
    return trimmed


def write_text_file(base_name: str, content: str) -> None:
    output_path = OUTPUT_DIR / f"{base_name}.txt"
    output_path.write_text(content, encoding="utf-8")


def write_error_file(json_path: Path, exc: Exception) -> None:
    message = (
        "Fichier non converti proprement.\n"
        "Raison:\n"
        f"{type(exc).__name__}: {exc}\n"
    )
    write_text_file(json_path.stem, message)


if __name__ == "__main__":
    main()
