
"""Tests for privacy-conscious agent tracing."""

import json
from unittest.mock import Mock

import pytest

from app.agent import observability
from app.agent.orchestrator import run_agent


def fake_client():
    client = Mock()
    client.chat.return_value.message.content = (
        "Réponse confidentielle"
    )
    client.chat.return_value.message.tool_calls = []
    return client


def test_agent_trace_contains_metadata_only(
    tmp_path,
    monkeypatch,
):
    trace_file = tmp_path / "agent_traces.jsonl"

    monkeypatch.setattr(
        observability,
        "TRACE_FILE",
        trace_file,
    )

    result = run_agent(
        "Question privée",
        client=fake_client(),
    )

    assert result["status"] == "completed"
    assert result["trace_id"]
    assert result["latency_ms"] >= 0

    contents = trace_file.read_text(
        encoding="utf-8"
    )

    event = json.loads(contents)

    assert event["trace_id"] == result["trace_id"]
    assert event["status"] == "completed"
    assert event["tool_call_count"] == 0
    assert event["execution_mode"] == "injected_client"

    assert "Question privée" not in contents
    assert "Réponse confidentielle" not in contents


def test_logging_failure_does_not_break_agent(
    tmp_path,
    monkeypatch,
):
    # A directory cannot be opened as a JSONL file.
    monkeypatch.setattr(
        observability,
        "TRACE_FILE",
        tmp_path,
    )

    result = run_agent(
        "Test logging failure",
        client=fake_client(),
    )

    assert result["status"] == "completed"
    assert result["trace_id"]

def test_event_timeline_contains_safe_metadata(tmp_path):
    """The timeline must never persist private content."""

    trace_file = tmp_path / "events.jsonl"

    event = observability.make_agent_event(
        "TOOL_COMPLETED",
        step=1,
        tool="get_pipeline_status",
        ok=True,
    )

    # Simulate accidentally supplied sensitive metadata.
    event["question"] = "PRIVATE_QUESTION"
    event["answer"] = "PRIVATE_ANSWER"
    event["arguments"] = {
        "secret": "PRIVATE_SECRET",
    }

    observability.record_agent_trace(
        {
            "status": "completed",
            "model": "qwen3:1.7b",
            "tools_used": [],
            "tool_call_count": 0,
            "answer": "PRIVATE_ANSWER",
        },
        latency_ms=25.5,
        path=trace_file,
        events=[event],
    )

    contents = trace_file.read_text(
        encoding="utf-8",
    )

    trace = json.loads(contents)

    assert trace["event_count"] == 1
    assert trace["events"][0]["event_type"] == (
        "TOOL_COMPLETED"
    )
    assert trace["events"][0]["tool"] == (
        "get_pipeline_status"
    )
    assert trace["events"][0]["ok"] is True

    assert "PRIVATE_QUESTION" not in contents
    assert "PRIVATE_ANSWER" not in contents
    assert "PRIVATE_SECRET" not in contents


def test_invalid_event_type_is_rejected():
    """Unknown event types must not enter the timeline."""

    with pytest.raises(ValueError):
        observability.make_agent_event(
            "DELETE_INFRASTRUCTURE",
        )
