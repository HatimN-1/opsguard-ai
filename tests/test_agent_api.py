
"""HTTP tests for the local MLOps agent endpoint."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


def test_agent_chat_success():
    fake_result = {
        "status": "completed",
        "answer": "The pipeline has a schema error.",
        "model": "qwen3:1.7b",
        "tools_used": [
            {
                "tool": "get_pipeline_status",
                "ok": True,
                "error": None,
            },
        ],
        "tool_call_count": 1,
    }

    with patch(
        "app.api.main.run_agent",
        return_value=fake_result,
    ) as mocked:
        response = client.post(
            "/agent/chat",
            json={
                "question": "Analyse etl_orders_daily",
            },
        )

    assert response.status_code == 200
    assert response.json() == fake_result
    mocked.assert_called_once_with(
        "Analyse etl_orders_daily"
    )


def test_agent_chat_empty_question():
    response = client.post(
        "/agent/chat",
        json={"question": "   "},
    )

    assert response.status_code == 422


def test_agent_chat_question_too_long():
    response = client.post(
        "/agent/chat",
        json={"question": "x" * 2001},
    )

    assert response.status_code == 422


def test_agent_chat_llm_unavailable():
    with patch(
        "app.api.main.run_agent",
        return_value={
            "status": "llm_error",
            "answer": "",
            "model": "qwen3:1.7b",
            "tools_used": [],
            "tool_call_count": 0,
        },
    ):
        response = client.post(
            "/agent/chat",
            json={"question": "Diagnose my pipeline"},
        )

    assert response.status_code == 503
