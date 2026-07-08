from app.agent.skills.sav_planning import SAVPlanningSkill, compute_sav_score


class _FakeOperationsDataTool:
    def get_client_priority(self, client_id: str):
        return {"priority": "IMPORTANT" if client_id == "victoria" else "STANDARD"}

    def get_opening_hours(self, client_id: str):
        return {"closing_soon": client_id == "victoria", "hours": "08:00-18:00"}


class _FakeMapsTool:
    def calculate_route_matrix(self, origin, destinations):
        return {
            "routes": [
                {
                    "destination_id": "victoria",
                    "distance_km": 6.5,
                    "duration_minutes": 18.0,
                },
                {
                    "destination_id": "other",
                    "distance_km": 19.2,
                    "duration_minutes": 42.0,
                },
            ]
        }


def test_compute_sav_score_matches_pdf_formula():
    score = compute_sav_score(
        urgency="HIGH",
        client_importance="IMPORTANT",
        route_duration_minutes=18,
        intervention_status="EN_RETARD",
        closing_soon=True,
    )

    assert score == 120


def test_sav_planning_ranks_best_destination_first():
    skill = SAVPlanningSkill(operations_data_tool=_FakeOperationsDataTool(), maps_tool=_FakeMapsTool())

    ranked = skill.rank_destinations(
        interventions=[
            {
                "client_id": "victoria",
                "client_name": "Pharmacie Victoria",
                "urgency": "HIGH",
                "status": "EN_RETARD",
                "route_hint": {"lat": 36.8, "lng": 10.1},
            },
            {
                "client_id": "other",
                "client_name": "Autre Client",
                "urgency": "MEDIUM",
                "status": "PLANIFIE",
                "route_hint": {"lat": 36.9, "lng": 10.2},
            },
        ],
        origin={"lat": 36.8065, "lng": 10.1815},
    )

    assert ranked[0]["client_id"] == "victoria"
    assert ranked[0]["score"] > ranked[1]["score"]
