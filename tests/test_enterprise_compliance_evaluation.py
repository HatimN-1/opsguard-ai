"""Offline and deterministic quality gates for Project 3 compliance."""

import json

from scripts.evaluate_enterprise_compliance import evaluate


def test_quality_gate_all_six_cases_pass(tmp_path, monkeypatch):
    # The evaluator restores pre-existing application environment variables.
    monkeypatch.setenv("OPSGUARD_ADF_SOURCE", "external_demo")
    monkeypatch.setenv("OPSGUARD_ADF_EXTERNAL_DIR", str(tmp_path / "existing"))
    report = evaluate()
    assert report["quality_gate_pass"] is True
    assert report["case_count"] == 6
    assert report["task_success_rate"] == 1.0
    assert report["third_tool_execution_pass"] is True
    assert report["manual_approval_boundary_pass"] is True
    assert report["tracing_pass"] is True
    assert report["tool_calls_mean_in_valid_investigations"] == 2.0
    assert {case["kind"] for case in report["cases"]} == {
        "nominal_status", "grounded_diagnosis", "three_tools_proposal_only",
        "unauthorized_refusal", "ambiguous_refusal", "human_approval_and_validation",
    }
    assert "run_id" not in json.dumps(report).lower()
    assert "Prépare une proposition" not in json.dumps(report, ensure_ascii=False)
