
"""Tests for deterministic human escalation evaluation."""

import json

from app.agent import observability
from scripts.evaluate_escalation import evaluate_cases


def test_all_escalation_guardrails_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(
        observability,
        "TRACE_FILE",
        tmp_path / "agent_traces.jsonl",
    )

    report = evaluate_cases()

    assert report["total_cases"] == 7
    assert report["passed_cases"] == 7
    assert report["pass_rate"] == 1.0
    assert report["real_llm_inference"] is False

    assert all(
        case["passed"]
        for case in report["results"]
    )

    encoded_report = json.dumps(report)

    assert "Investigate the simulated ETL failure" not in encoded_report
    assert "arguments" not in encoded_report

    traces = [
        json.loads(line)
        for line in (
            tmp_path / "agent_traces.jsonl"
        ).read_text(encoding="utf-8").splitlines()
    ]

    assert len(traces) == 7
    assert all(
        trace["execution_mode"] == "injected_client"
        for trace in traces
    )


def test_escalation_evaluation_detects_missing_tool_calls():
    def broken_runner(question, *, client):
        return {
            "status": "completed",
            "tools_used": [],
            "tool_call_count": 0,
            "trace_id": "simulated-test",
        }

    report = evaluate_cases(
        agent_runner=broken_runner
    )

    assert report["total_cases"] == 7
    assert report["passed_cases"] == 0
    assert report["pass_rate"] == 0.0
