
"""Tests for deterministic diagnostic orchestration."""

from fastapi.testclient import TestClient

from app.agent.diagnostic import diagnose_pipeline
from app.api.main import app

client = TestClient(app)


def test_failed_pipeline_diagnosis() -> None:
    result = diagnose_pipeline("etl_orders_daily")

    assert result is not None
    assert result["status"] == "FAILED"
    assert result["error_code"] == "SCHEMA_VALIDATION_ERROR"
    assert result["runbooks"][0]["runbook_id"] == "RB-001"


def test_multiple_tools_are_used() -> None:
    result = diagnose_pipeline("etl_orders_daily")

    assert result is not None
    assert result["tools_used"] == [
        "get_pipeline_status",
        "search_runbook",
    ]
    assert result["ticket_created"] is False


def test_successful_pipeline() -> None:
    result = diagnose_pipeline("etl_customers_daily")

    assert result is not None
    assert result["status"] == "SUCCESS"
    assert result["runbooks"] == []
    assert result["tools_used"] == ["get_pipeline_status"]


def test_unknown_pipeline() -> None:
    assert diagnose_pipeline("unknown") is None


def test_diagnostic_api() -> None:
    response = client.get(
        "/diagnostics/pipelines/etl_orders_daily"
    )

    assert response.status_code == 200
    assert response.json()["runbooks"][0]["runbook_id"] == "RB-001"
