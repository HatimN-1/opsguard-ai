"""Check auditable tool metadata on all generic orchestrator paths."""

import json
from types import SimpleNamespace

from app.agent import observability, orchestrator


def _response(*, content="", calls=None):
    return SimpleNamespace(
        message=SimpleNamespace(
            content=content,
            tool_calls=[
                SimpleNamespace(function=SimpleNamespace(name=name, arguments=args))
                for name, args in (calls or [])
            ],
        )
    )


class FakeClient:
    def __init__(self, replies):
        self.replies = iter(replies)

    def chat(self, **kwargs):
        return next(self.replies)


def _trace(tmp_path, monkeypatch):
    target = tmp_path / "trace.jsonl"
    monkeypatch.setattr(observability, "TRACE_FILE", target)
    return target


def _assert_events(trace, expected_selection):
    events = trace["events"]
    requested = [event for event in events if event["event_type"] == "TOOL_REQUESTED"]
    completed = [event for event in events if event["event_type"] == "TOOL_COMPLETED"]
    assert len(requested) == len(completed) == 1
    assert requested[0]["selection_source"] == expected_selection
    assert isinstance(completed[0]["duration_ms"], (float, int))
    assert completed[0]["duration_ms"] >= 0
    assert "selection_source" not in completed[0]
    assert "duration_ms" not in requested[0]
    assert "password" not in json.dumps(trace).lower()
    assert "tool_arguments_raw" not in json.dumps(trace).lower()
    return completed[0]


def test_llm_selected_tool_has_selection_and_duration(tmp_path, monkeypatch):
    path = _trace(tmp_path, monkeypatch)
    monkeypatch.setattr(
        orchestrator,
        "execute_tool",
        lambda name, args: {"ok": True, "tool": name, "data": {"status": "Failed"}},
    )
    client = FakeClient([
        _response(calls=[("get_pipeline_status", {"pipeline_id": "etl_orders_daily"})]),
        _response(content="Les informations ont été consultées."),
    ])
    result = orchestrator.run_agent("Examine ce processus.", client=client)
    trace = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
    assert result["tool_call_count"] == 1
    assert _assert_events(trace, "llm_proposed")["outcome_category"] == "SUCCESS"


def test_invalid_tool_arguments_are_traced_and_redacted(tmp_path, monkeypatch):
    path = _trace(tmp_path, monkeypatch)
    client = FakeClient([
        _response(calls=[("get_pipeline_status", "API_KEY=not-a-dict")]),
        _response(content="Arguments invalides."),
    ])
    result = orchestrator.run_agent("Examine ce processus.", client=client)
    trace = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
    assert result["tool_call_count"] == 1
    completion = _assert_events(trace, "llm_proposed")
    assert completion["outcome_category"] == "INVALID_ARGUMENTS"
    assert "API_KEY=not-a-dict" not in path.read_text(encoding="utf-8")


def test_deterministic_policy_tool_has_selection_and_duration(tmp_path, monkeypatch):
    path = _trace(tmp_path, monkeypatch)
    monkeypatch.setattr(orchestrator, "wants_adf_investigation", lambda q: True)
    monkeypatch.setattr(orchestrator, "mentioned_adf_pipeline", lambda q: "adf_04_inventory")
    monkeypatch.setattr(
        orchestrator,
        "execute_tool",
        lambda name, args: {"ok": False, "tool": name, "error": "NOT_FOUND"},
    )
    result = orchestrator.run_agent("Analyse les journaux Azure ADF.")
    trace = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
    assert result["tool_call_count"] == 1
    assert _assert_events(trace, "policy")["outcome_category"] == "NOT_FOUND"
