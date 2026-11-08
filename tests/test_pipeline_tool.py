
"""Tests for the first simulated monitoring tool."""

from fastapi.testclient import TestClient

from app.api.main import app
from app.tools.pipeline_tool import get_pipeline_status

client = TestClient(app)


def test_failed_pipeline() -> None:
    pipeline = get_pipeline_status("etl_orders_daily")
    assert pipeline is not None
    assert pipeline["status"] == "FAILED"
    assert pipeline["invalid_records"] == 245


def test_unknown_pipeline() -> None:
    assert get_pipeline_status("does_not_exist") is None


def test_api_pipeline_found() -> None:
    response = client.get("/pipelines/etl_orders_daily")
    assert response.status_code == 200
    assert response.json()["error_code"] == "SCHEMA_VALIDATION_ERROR"


def test_api_pipeline_not_found() -> None:
    response = client.get("/pipelines/does_not_exist")
    assert response.status_code == 404
