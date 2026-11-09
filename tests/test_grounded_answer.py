
"""Tests for grounded French agent responses."""

from app.agent.grounded_answer import (
    compose_grounded_answer,
)


def test_pipeline_facts_and_runbook():
    answer = compose_grounded_answer(
        "Analyse le pipeline et consulte la procédure.",
        "The schema is invalid.",
        [
            {
                "ok": True,
                "tool": "get_pipeline_status",
                "data": {
                    "pipeline_id": "etl_orders_daily",
                    "status": "FAILED",
                    "error_code": "SCHEMA_VALIDATION_ERROR",
                },
            },
            {
                "ok": True,
                "tool": "search_runbook",
                "data": [
                    {"runbook_id": "RB-001"},
                ],
            },
        ],
    )

    assert "etl_orders_daily" in answer
    assert "FAILED" in answer
    assert "SCHEMA_VALIDATION_ERROR" in answer
    assert "RB-001" in answer
    assert "The schema is invalid." not in answer


def test_model_metrics_are_grounded():
    answer = compose_grounded_answer(
        "Consulte les métriques du modèle.",
        "Le modèle présente des erreurs.",
        [
            {
                "ok": True,
                "tool": "get_model_metrics",
                "data": {
                    "model_id": "fraud_detection_v1",
                    "error_rate_pct": 4.5,
                    "invalid_input_rate_pct": 8.0,
                },
            },
        ],
    )

    assert "fraud_detection_v1" in answer
    assert "4.5 %" in answer
    assert "8 %" in answer


def test_failed_tool_adds_no_verified_facts():
    answer = compose_grounded_answer(
        "Analyse le pipeline.",
        "Le diagnostic est indisponible.",
        [
            {
                "ok": False,
                "tool": "get_pipeline_status",
                "error": "NOT_FOUND",
            },
        ],
    )

    assert answer == "Le diagnostic est indisponible."
