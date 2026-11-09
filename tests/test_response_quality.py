
"""Tests for response language and factual coverage."""

from app.agent.response_quality import (
    detect_language,
    score_response,
)
from scripts.evaluate_responses import evaluate_cases


def test_french_response_detected():
    answer = (
        "Le pipeline est en échec. "
        "Vous devez vérifier les données."
    )

    assert detect_language(answer) == "fr"


def test_english_response_detected():
    answer = (
        "The pipeline has failed. "
        "You should check the data."
    )

    assert detect_language(answer) == "en"


def test_missing_fact_detected():
    quality = score_response(
        "Le pipeline etl_orders_daily est en échec.",
        {
            "pipeline_id": ["etl_orders_daily"],
            "error_code": ["SCHEMA_VALIDATION_ERROR"],
        },
    )

    assert quality["passed"] is False
    assert quality["fact_coverage"] == 0.5
    assert quality["missing_facts"] == ["error_code"]


def test_correct_french_answer_passes():
    quality = score_response(
        (
            "Le pipeline etl_orders_daily est en échec. "
            "L'erreur est SCHEMA_VALIDATION_ERROR."
        ),
        {
            "pipeline_id": ["etl_orders_daily"],
            "error_code": ["SCHEMA_VALIDATION_ERROR"],
        },
    )

    assert quality["language_ok"] is True
    assert quality["fact_coverage"] == 1.0
    assert quality["passed"] is True


def test_report_does_not_contain_answer():
    case = {
        "id": "EVAL-002",
        "question": "Quel est le statut du pipeline ?",
    }

    secret_answer = (
        "Le pipeline etl_customers_daily "
        "est un succès. PRIVATE_TEST_STRING"
    )

    def fake_runner(question):
        return {
            "status": "completed",
            "answer": secret_answer,
            "trace_id": "fake-trace",
            "latency_ms": 100.0,
        }

    report = evaluate_cases(
        [case],
        agent_runner=fake_runner,
    )

    assert report["passed_cases"] == 1
    assert "PRIVATE_TEST_STRING" not in str(report)
    assert "answer" not in report["results"][0]
