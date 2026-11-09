
"""Tests for the bounded LLM agent orchestrator."""

from types import SimpleNamespace

import pytest

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
