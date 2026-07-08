from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class ClientRecord(BaseModel):
    id: int
    name: str
    segment: str
    city: str
    status: str
    notes: str


class DiffuseurRecord(BaseModel):
    id: int
    client_id: int
    model: str
    serial_number: str
    status: str
    last_service_date: date | None = None
    notes: str


class TechnicienRecord(BaseModel):
    id: int
    name: str
    zone: str
    skill_level: str
    availability: str


class InterventionRecord(BaseModel):
    id: int
    client_id: int
    diffuseur_id: int
    technicien_id: int | None = None
    status: str
    priority: str
    scheduled_at: datetime | None = None
    summary: str


class ReclamationRecord(BaseModel):
    id: int
    client_id: int
    intervention_id: int | None = None
    status: str
    severity: str
    description: str


class RecommendationRecord(BaseModel):
    id: int
    client_id: int | None = None
    diffuseur_id: int | None = None
    intervention_id: int | None = None
    status: str
    priority: str
    recommendation_text: str


TABLE_COLUMNS: dict[str, list[str]] = {
    "clients": ["id", "name", "segment", "city", "status", "notes"],
    "diffuseurs": [
        "id",
        "client_id",
        "model",
        "serial_number",
        "status",
        "last_service_date",
        "notes",
    ],
    "techniciens": ["id", "name", "zone", "skill_level", "availability"],
    "interventions": [
        "id",
        "client_id",
        "diffuseur_id",
        "technicien_id",
        "status",
        "priority",
        "scheduled_at",
        "summary",
    ],
    "reclamations": [
        "id",
        "client_id",
        "intervention_id",
        "status",
        "severity",
        "description",
    ],
    "recommendations": [
        "id",
        "client_id",
        "diffuseur_id",
        "intervention_id",
        "status",
        "priority",
        "recommendation_text",
    ],
}


SCHEMA_STATEMENTS: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS clients (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        segment TEXT NOT NULL,
        city TEXT NOT NULL,
        status TEXT NOT NULL,
        notes TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS diffuseurs (
        id INTEGER PRIMARY KEY,
        client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
        model TEXT NOT NULL,
        serial_number TEXT NOT NULL,
        status TEXT NOT NULL,
        last_service_date DATE,
        notes TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS techniciens (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        zone TEXT NOT NULL,
        skill_level TEXT NOT NULL,
        availability TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS interventions (
        id INTEGER PRIMARY KEY,
        client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
        diffuseur_id INTEGER NOT NULL REFERENCES diffuseurs(id) ON DELETE CASCADE,
        technicien_id INTEGER REFERENCES techniciens(id) ON DELETE SET NULL,
        status TEXT NOT NULL,
        priority TEXT NOT NULL,
        scheduled_at TIMESTAMPTZ,
        summary TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS reclamations (
        id INTEGER PRIMARY KEY,
        client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
        intervention_id INTEGER REFERENCES interventions(id) ON DELETE SET NULL,
        status TEXT NOT NULL,
        severity TEXT NOT NULL,
        description TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS recommendations (
        id INTEGER PRIMARY KEY,
        client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL,
        diffuseur_id INTEGER REFERENCES diffuseurs(id) ON DELETE SET NULL,
        intervention_id INTEGER REFERENCES interventions(id) ON DELETE SET NULL,
        status TEXT NOT NULL,
        priority TEXT NOT NULL,
        recommendation_text TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_diffuseurs_client_id ON diffuseurs (client_id)",
    "CREATE INDEX IF NOT EXISTS idx_interventions_client_id ON interventions (client_id)",
    "CREATE INDEX IF NOT EXISTS idx_interventions_diffuseur_id ON interventions (diffuseur_id)",
    "CREATE INDEX IF NOT EXISTS idx_interventions_technicien_id ON interventions (technicien_id)",
    "CREATE INDEX IF NOT EXISTS idx_reclamations_client_id ON reclamations (client_id)",
    "CREATE INDEX IF NOT EXISTS idx_recommendations_client_id ON recommendations (client_id)",
]
