
"""Tests for conservative response contradiction checks."""

from app.agent.grounded_answer import compose_grounded_answer
from app.agent.response_guard import detect_contradictions


def test_pipeline_status_contradiction():
    results = [
        {
            "ok": True,
            "tool": "get_pipeline_status",
            "data": {
                "pipeline_id": "etl_orders_daily",
                "status": "FAILED",
            },
        },
    ]

    issues = detect_contradictions(
        "Le pipeline a réussi son exécution.",
        results,
    )

    assert "PIPELINE_STATUS_CONFLICT" in issues


def test_correct_pipeline_status_is_accepted():
    results = [
        {
            "ok": True,
            "tool": "get_pipeline_status",
            "data": {
                "pipeline_id": "etl_orders_daily",
                "status": "FAILED",
            },
        },
    ]

    issues = detect_contradictions(
        "Le pipeline est en échec.",
        results,
    )

    assert issues == []


def test_unverified_percentage_is_detected():
    results = [
        {
            "ok": True,
            "tool": "get_model_metrics",
            "data": {
                "model_id": "fraud_detection_v1",
                "error_rate_pct": 4.5,
                "invalid_input_rate_pct": 8.0,
            },
        },
    ]

    issues = detect_contradictions(
        "Le taux d'erreur est de 12 %.",
        results,
    )

    assert "UNVERIFIED_PERCENTAGE" in issues


def test_contradictory_generated_text_is_hidden():
    results = [
        {
            "ok": True,
            "tool": "get_pipeline_status",
            "data": {
                "pipeline_id": "etl_orders_daily",
                "status": "FAILED",
            },
        },
    ]

    answer = compose_grounded_answer(
        "Analyse le pipeline.",
        "Le pipeline est réussi avec succès.",
        results,
    )

    assert "statut FAILED" in answer
    assert "Le pipeline est réussi" not in answer
    assert "contradiction potentielle" in answer
