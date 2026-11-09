
"""Tests for privacy-conscious agent tracing."""

import json
from unittest.mock import Mock

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
