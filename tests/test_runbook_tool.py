
"""Tests for technical runbook retrieval."""

from fastapi.testclient import TestClient

from app.api.main import app
from app.tools.runbook_tool import search_runbook

client = TestClient(app)


def test_runbook_found() -> None:
    results = search_runbook("SCHEMA_VALIDATION_ERROR")

    assert len(results) == 1
    assert results[0]["runbook_id"] == "RB-001"
    assert results[0]["version"] == "1.0.0"


def test_case_insensitive_search() -> None:
    results = search_runbook("high_latency")

    assert len(results) == 1
    assert results[0]["runbook_id"] == "RB-002"


def test_unknown_error_code() -> None:
    assert search_runbook("UNKNOWN_ERROR") == []


def test_api_runbook_search() -> None:
    response = client.get(
        "/runbooks/search",
        params={"error_code": "MISSING_VALUES"},
    )

    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["results"][0]["runbook_id"] == "RB-003"


def test_api_rejects_invalid_error_code() -> None:
    response = client.get(
        "/runbooks/search",
        params={"error_code": "INVALID CODE!"},
    )

    assert response.status_code == 422
