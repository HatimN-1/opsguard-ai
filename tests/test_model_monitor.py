
"""Tests du monitoring des modèles ML."""

from fastapi.testclient import TestClient

from app.api.main import app
from app.tools.model_monitor import get_model_metrics

client = TestClient(app)


def test_fraud_model_metrics() -> None:
    metrics = get_model_metrics("fraud_detection_v1")

    assert metrics is not None
    assert metrics["requests_total"] == 1000
    assert metrics["error_rate_pct"] == 4.5
    assert metrics["invalid_input_rate_pct"] == 8.0
    assert metrics["latency_p95_ms"] == 150


def test_churn_model_metrics() -> None:
    metrics = get_model_metrics("churn_prediction_v2")

    assert metrics is not None
    assert metrics["error_rate_pct"] == 1.0
    assert metrics["invalid_input_rate_pct"] == 2.0


def test_model_without_requests() -> None:
    metrics = get_model_metrics("sales_forecast_v1")

    assert metrics is not None
    assert metrics["error_rate_pct"] is None
    assert metrics["latency_p95_ms"] is None


def test_unknown_model() -> None:
    assert get_model_metrics("unknown_model") is None


def test_api_model_metrics() -> None:
    response = client.get(
        "/models/fraud_detection_v1/metrics"
    )

    assert response.status_code == 200
    assert response.json()["error_rate_pct"] == 4.5
    assert response.json()["data_mode"] == "simulated"


def test_api_unknown_model() -> None:
    response = client.get("/models/unknown/metrics")

    assert response.status_code == 404
