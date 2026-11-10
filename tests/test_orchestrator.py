
"""Tests for the bounded LLM agent orchestrator."""

from types import SimpleNamespace

import pytest
from httpx import ReadTimeout

from app.agent.orchestrator import run_agent


def fake_response(content="", calls=None):
    tool_calls = [
        SimpleNamespace(
            function=SimpleNamespace(
                name=name,
                arguments=args,
            )
        )
        for name, args in (calls or [])
    ]

    return SimpleNamespace(
        message=SimpleNamespace(
            content=content,
            tool_calls=tool_calls,
        )
    )


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def chat(self, **kwargs):
        self.requests.append(kwargs)
        return next(self.responses)


def test_agent_uses_two_tools():
    client = FakeClient([
        fake_response(calls=[
            (
                "get_pipeline_status",
                {"pipeline_id": "etl_orders_daily"},
            ),
        ]),
        fake_response(calls=[
            (
                "search_runbook",
                {"error_code": "SCHEMA_VALIDATION_ERROR"},
            ),
        ]),
        fake_response("Diagnostic completed."),
    ])

    result = run_agent(
        "Diagnose etl_orders_daily",
        client=client,
    )

    assert result["status"] == "completed"
    assert result["tool_call_count"] == 2
    assert [x["tool"] for x in result["tools_used"]] == [
        "get_pipeline_status",
        "search_runbook",
    ]
    assert all(x["ok"] for x in result["tools_used"])

    assert any(
        msg.get("role") == "tool"
        and "FAILED" in msg.get("content", "")
        for msg in client.requests[1]["messages"]
        if isinstance(msg, dict)
    )


def test_agent_without_tool_calls():
    client = FakeClient([
        fake_response("I can help with MLOps.")
    ])

    result = run_agent("Hello", client=client)

    assert result["status"] == "completed"
    assert result["tool_call_count"] == 0


def test_unknown_tool_is_rejected():
    client = FakeClient([
        fake_response(calls=[
            ("delete_everything", {}),
        ]),
        fake_response("Action rejected."),
    ])

    result = run_agent("Delete everything", client=client)

    assert result["tools_used"][0]["ok"] is False
    assert result["tools_used"][0]["error"] == "UNKNOWN_TOOL"


def test_ticket_is_proposal_only():
    client = FakeClient([
        fake_response(calls=[
            (
                "prepare_incident_ticket",
                {
                    "incident_id": "INC-001",
                    "reason": "Investigate ETL schema failure",
                },
            ),
        ]),
        fake_response("Human approval is required."),
    ])

    result = run_agent("Prepare an incident", client=client)

    assert result["tool_call_count"] == 1
    assert result["tools_used"][0]["ok"] is True

    tool_messages = [
        msg
        for msg in client.requests[1]["messages"]
        if isinstance(msg, dict)
        and msg.get("role") == "tool"
    ]

    assert '"ticket_created": false' in tool_messages[0]["content"]


def test_empty_question_rejected():
    with pytest.raises(ValueError):
        run_agent("   ")


def test_tool_observer_receives_arguments():
    observed = []

    client = FakeClient([
        fake_response(calls=[
            (
                "get_pipeline_status",
                {"pipeline_id": "etl_orders_daily"},
            ),
        ]),
        fake_response("Diagnostic completed."),
    ])

    result = run_agent(
        "Diagnose etl_orders_daily",
        client=client,
        tool_observer=lambda name, args: observed.append(
            (name, args)
        ),
    )

    assert result["status"] == "completed"

    assert observed == [
        (
            "get_pipeline_status",
            {"pipeline_id": "etl_orders_daily"},
        )
    ]

    assert "arguments" not in result["tools_used"][0]


def test_ollama_timeout_is_controlled():
    class TimeoutClient:
        def chat(self, **kwargs):
            raise ReadTimeout("Simulated timeout")

    result = run_agent(
        "Diagnose the pipeline",
        client=TimeoutClient(),
    )

    assert result["status"] == "llm_error"
    assert result["tool_call_count"] == 0
    assert result["trace_id"]


def test_missing_ollama_message_is_rejected():
    client = FakeClient([
        SimpleNamespace(message=None),
    ])

    result = run_agent(
        "Diagnose a pipeline",
        client=client,
    )

    assert result["status"] == "invalid_response"
    assert result["tool_call_count"] == 0


def test_malformed_ollama_tool_call_is_rejected():
    client = FakeClient([
        SimpleNamespace(
            message=SimpleNamespace(
                content="",
                tool_calls=[
                    SimpleNamespace(function=None),
                ],
            )
        ),
    ])

    result = run_agent(
        "Diagnose a pipeline",
        client=client,
    )

    assert result["status"] == "invalid_response"
    assert result["tool_call_count"] == 0



def test_tool_unexpected_exception_is_controlled(
    monkeypatch,
):
    """Unexpected tool failures must not crash the agent."""

    def broken_tool(name, arguments):
        raise RuntimeError("Internal sensitive error")

    monkeypatch.setattr(
        "app.agent.orchestrator.execute_tool",
        broken_tool,
    )

    client = FakeClient([
        fake_response(calls=[
            (
                "get_pipeline_status",
                {"pipeline_id": "etl_orders_daily"},
            ),
        ]),
        fake_response("L'outil a échoué."),
    ])

    result = run_agent(
        "Analyse etl_orders_daily.",
        client=client,
    )

    assert result["status"] == "completed"
    assert result["tools_used"][0]["ok"] is False
    assert (
        result["tools_used"][0]["error"]
        == "TOOL_EXECUTION_ERROR"
    )
    assert "Internal sensitive error" not in str(result)


def test_malformed_tool_result_is_controlled(
    monkeypatch,
):
    """Invalid tool results must be rejected safely."""

    monkeypatch.setattr(
        "app.agent.orchestrator.execute_tool",
        lambda name, arguments: None,
    )

    client = FakeClient([
        fake_response(calls=[
            (
                "get_pipeline_status",
                {"pipeline_id": "etl_orders_daily"},
            ),
        ]),
        fake_response("Le résultat est indisponible."),
    ])

    result = run_agent(
        "Analyse etl_orders_daily.",
        client=client,
    )

    assert result["status"] == "completed"
    assert result["tool_call_count"] == 1
    assert result["tools_used"][0]["ok"] is False
    assert (
        result["tools_used"][0]["error"]
        == "TOOL_EXECUTION_ERROR"
    )


def test_max_steps_allows_final_answer_without_tools():
    """After the step limit, only a final answer is allowed."""

    client = FakeClient([
        fake_response(calls=[
            (
                "get_pipeline_status",
                {"pipeline_id": "etl_orders_daily"},
            ),
        ]),
        fake_response("Le diagnostic est terminé."),
    ])

    result = run_agent(
        "Analyse etl_orders_daily.",
        client=client,
        max_steps=1,
    )

    assert result["status"] == "completed"
    assert result["tool_call_count"] == 1
    assert len(client.requests) == 2
    assert client.requests[1]["tools"] == []


def test_max_steps_blocks_additional_tool_requests():
    """Tool requests after the step limit must be rejected."""

    client = FakeClient([
        fake_response(calls=[
            (
                "get_pipeline_status",
                {"pipeline_id": "etl_orders_daily"},
            ),
        ]),
        fake_response(calls=[
            (
                "search_runbook",
                {"error_code": "SCHEMA_VALIDATION_ERROR"},
            ),
        ]),
    ])

    result = run_agent(
        "Analyse etl_orders_daily.",
        client=client,
        max_steps=1,
    )

    assert result["status"] == "limit_reached"
    assert result["tool_call_count"] == 1
    assert len(client.requests) == 2
    assert client.requests[1]["tools"] == []
