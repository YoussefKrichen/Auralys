from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.db.models import (
    ClientRecord,
    DiffuseurRecord,
    InterventionRecord,
    RecommendationRecord,
    ReclamationRecord,
    TechnicienRecord,
)
from app.db.postgres import PostgresDatabase


DEMO_CLIENTS = [
    ClientRecord(
        id=1,
        name="Pharmacie du Centre",
        segment="pharmacie",
        city="Paris",
        status="active",
        notes="Client premium avec trafic eleve et exigence forte sur la disponibilite.",
    ),
    ClientRecord(
        id=2,
        name="Hotel Belle Vue",
        segment="hotel",
        city="Lyon",
        status="watch",
        notes="Client sensible a la qualite du parfum et aux retours clients.",
    ),
]

DEMO_DIFFUSEURS = [
    DiffuseurRecord(
        id=1,
        client_id=1,
        model="AromaFlow X2",
        serial_number="AFX2-001",
        status="maintenance_due",
        last_service_date=date.today() - timedelta(days=45),
        notes="Diffusion irreguliere signalee sur les heures de pointe.",
    ),
    DiffuseurRecord(
        id=2,
        client_id=2,
        model="AromaLobby S",
        serial_number="ALS-009",
        status="operational",
        last_service_date=date.today() - timedelta(days=10),
        notes="RAS apres le dernier remplacement de recharge.",
    ),
]

DEMO_TECHNICIENS = [
    TechnicienRecord(
        id=1,
        name="Ines Martin",
        zone="Ile-de-France",
        skill_level="senior",
        availability="available",
    ),
    TechnicienRecord(
        id=2,
        name="Karim Dupont",
        zone="Auvergne-Rhone-Alpes",
        skill_level="intermediate",
        availability="on_call",
    ),
]

DEMO_INTERVENTIONS = [
    InterventionRecord(
        id=1,
        client_id=1,
        diffuseur_id=1,
        technicien_id=1,
        status="open",
        priority="high",
        scheduled_at=datetime.now(timezone.utc) + timedelta(days=1),
        summary="Verifier la pompe et recalibrer le debit du diffuseur principal.",
    ),
    InterventionRecord(
        id=2,
        client_id=2,
        diffuseur_id=2,
        technicien_id=2,
        status="closed",
        priority="medium",
        scheduled_at=datetime.now(timezone.utc) - timedelta(days=3),
        summary="Recharge remplacee et cycle de diffusion reconfigure.",
    ),
]

DEMO_RECLAMATIONS = [
    ReclamationRecord(
        id=1,
        client_id=1,
        intervention_id=1,
        status="open",
        severity="critical",
        description="Le diffuseur s'arrete en pleine journee et degrade l'experience magasin.",
    ),
    ReclamationRecord(
        id=2,
        client_id=2,
        intervention_id=2,
        status="resolved",
        severity="low",
        description="Demande de verification apres un parfum juge trop discret.",
    ),
]

DEMO_RECOMMENDATIONS = [
    RecommendationRecord(
        id=1,
        client_id=1,
        diffuseur_id=1,
        intervention_id=1,
        status="proposed",
        priority="high",
        recommendation_text="Planifier une verification sur site sous 24h et controler la pompe.",
    ),
    RecommendationRecord(
        id=2,
        client_id=2,
        diffuseur_id=2,
        intervention_id=2,
        status="validated",
        priority="medium",
        recommendation_text="Conserver la configuration actuelle et suivre les retours pendant 7 jours.",
    ),
]

DEMO_VECTOR_DOCUMENTS = [
    {
        "document_id": "doc-maint-001",
        "title": "Fiche maintenance Pharmacie du Centre",
        "text": (
            "Historique maintenance Pharmacie du Centre. Symptomes: debit instable, pause"
            " en milieu de journee, suspicion de pompe fatiguee. Action precedente:"
            " nettoyage partiel et reamor cage de la ligne."
        ),
        "source_type": "maintenance_report",
        "metadata": {"client_id": 1, "diffuseur_id": 1, "document_type": "maintenance"},
    },
    {
        "document_id": "doc-email-002",
        "title": "Email client Hotel Belle Vue",
        "text": (
            "Le client note une legere baisse d'intensite du parfum dans le hall, mais"
            " aucun arret complet. Priorite faible, demande de suivi au prochain passage."
        ),
        "source_type": "email",
        "metadata": {"client_id": 2, "diffuseur_id": 2, "document_type": "email"},
    },
]

DEMO_MEMORY_DOCUMENTS = [
    {
        "document_id": "mem-001",
        "title": "Memoire SAV pompe diffuseur",
        "text": (
            "Quand un diffuseur AromaFlow X2 presente des pauses aleatoires, verifier en"
            " priorite la pompe, puis le calibrage de debit et l'alimentation."
        ),
        "source_type": "memory",
        "metadata": {"topic": "sav", "model": "AromaFlow X2"},
    }
]


def seed_postgres(database: PostgresDatabase) -> None:
    database.upsert_records("clients", [item.model_dump() for item in DEMO_CLIENTS])
    database.upsert_records("diffuseurs", [item.model_dump() for item in DEMO_DIFFUSEURS])
    database.upsert_records("techniciens", [item.model_dump() for item in DEMO_TECHNICIENS])
    database.upsert_records("interventions", [item.model_dump() for item in DEMO_INTERVENTIONS])
    database.upsert_records("reclamations", [item.model_dump() for item in DEMO_RECLAMATIONS])
    database.upsert_records("recommendations", [item.model_dump() for item in DEMO_RECOMMENDATIONS])
