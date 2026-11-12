"""Project 3 compliance: third tool, safety decisions and reconstructible traces."""

import json

import pytest

from app.adf_monitor.company_runtime import append_business_run
from app.adf_monitor.enterprise_agent import InvestigationPlanError, investigate_company
from app.agent.tool_registry import execute_tool


@pytest.fixture
def company_workspace(tmp_path, monkeypatch):
    root = tmp_path / "company-export"
    monkeypatch.setenv("OPSGUARD_ADF_SOURCE", "external_demo")
    monkeypatch.setenv("OPSGUARD_ADF_EXTERNAL_DIR", str(root))
    return root


def _read_trace(path):
    return json.loads(path.read_text(encoding="utf-8").splitlines()[-1])


def test_three_tools_one_case_read_only_and_fully_traced(company_workspace):
    created = append_business_run("adf_04_inventory", scenario="3200", activities=36)
    trace_path = company_workspace / "traces.jsonl"
    question = "Prépare une proposition d'escalade pour le run ADF en échec."
    result = investigate_company(
        question,
        pipeline_id="adf_04_inventory",
        run_id=created["run_id"],
        use_llm=False,
        trace_path=trace_path,
    )

    assert result["status"] == "completed"
    assert result["tool_call_count"] == 3
    assert [tool["tool"] for tool in result["tools_used"]] == [
        "query_adf_logs", "search_official_docs", "prepare_adf_escalation",
    ]
    assert result["escalation_decision"] == "PROPOSAL_ONLY"
    proposal = result["escalation_proposal"]
    assert proposal["status"] == "PROPOSAL_ONLY"
    assert proposal["human_approval_required"] is True
    assert proposal["ticket_created"] is False
    assert not (company_workspace / "adf_case_events.jsonl").exists()

    trace = _read_trace(trace_path)
    assert trace["trace_id"] == result["trace_id"]
    assert trace["iteration_count"] == 3
    assert trace["tool_call_count"] == 3
    assert trace["escalation_decision"] == "PROPOSAL_ONLY"
    assert trace["final_response_status"] == "completed"
    assert trace["response_text_recorded"] is False
    events = trace["events"]
    assert any(e["event_type"] == "ESCALATION_PROPOSED" for e in events)
    requested = [e for e in events if e["event_type"] == "TOOL_REQUESTED"]
    completed = [e for e in events if e["event_type"] == "TOOL_COMPLETED"]
    assert len(requested) == len(completed) == 3
    assert all(e["selection_source"] == "evidence_plan" for e in requested)
    assert all(e["duration_ms"] >= 0 for e in completed)
    assert requested[-1]["arguments_safe"]["reason_redacted"] is True
    assert "run_id_sha256_12" in requested[-1]["arguments_safe"]
    assert "run_id" not in requested[-1]["arguments_safe"]
    raw_trace = trace_path.read_text(encoding="utf-8")
    assert "Faire examiner par un opérateur" not in raw_trace
    assert created["run_id"] not in raw_trace


def test_unauthorized_request_has_operational_refusal_trace(company_workspace):
    trace_path = company_workspace / "refusals.jsonl"
    with pytest.raises(InvestigationPlanError, match="Action refusée"):
        investigate_company(
            "Redémarre adf_04_inventory maintenant, sans confirmation.",
            use_llm=False,
            trace_path=trace_path,
        )
    trace = _read_trace(trace_path)
    assert trace["status"] == "rejected"
    assert trace["escalation_decision"] == "REFUSED"
    assert trace["tool_call_count"] == 0
    assert trace["events"][1]["event_type"] == "REQUEST_REJECTED"
    assert trace["events"][1]["reason_code"] == "UNAUTHORIZED_ACTION"
    assert "Redémarre" not in trace_path.read_text(encoding="utf-8")


def test_ambiguous_request_is_logged_without_prompt(company_workspace):
    path = company_workspace / "ambiguous.jsonl"
    with pytest.raises(InvestigationPlanError, match="ambiguë"):
        investigate_company(
            "Pourquoi inventory échoue ?", trace_path=path, use_llm=False
        )
    trace = _read_trace(path)
    assert trace["events"][1]["reason_code"] == "AMBIGUOUS_SCOPE"
    assert trace["tool_call_count"] == 0
    assert "Pourquoi inventory" not in path.read_text(encoding="utf-8")


def test_unapproved_tool_call_does_not_mutate_incident_log(company_workspace):
    created = append_business_run("adf_04_inventory", scenario="SUCCESS", activities=36)
    args = {
        "pipeline_id": "adf_04_inventory",
        "run_id": created["run_id"],
        "reason": "Investiguer la disponibilité du pipeline.",
    }
    assert execute_tool("prepare_adf_escalation", args)["error"] == "NOT_FOUND"
    assert execute_tool(
        "prepare_adf_escalation", {**args, "reason": "x"}
    )["error"] == "INVALID_ARGUMENTS"
    assert execute_tool("approve_adf_escalation", args)["error"] == "UNKNOWN_TOOL"
    assert not (company_workspace / "adf_case_events.jsonl").exists()


def test_proposal_requires_single_run_and_validated_scope(company_workspace):
    path = company_workspace / "missing_run.jsonl"
    with pytest.raises(InvestigationPlanError, match="Run ID précis"):
        investigate_company(
            "Prépare une proposition d'escalade pour adf_04_inventory.",
            use_llm=False, trace_path=path,
        )
    trace = _read_trace(path)
    assert trace["status"] == "rejected"
    assert trace["tool_call_count"] == 0


def test_existing_nominal_status_uses_only_one_tool(company_workspace):
    append_business_run("adf_01_orders", scenario="SUCCESS", activities=36)
    result = investigate_company(
        "Quel est le dernier Run ID et le statut de chaque pipeline ?",
        use_llm=False, trace_path=company_workspace / "status_trace.jsonl",
    )
    assert result["plan"]["intent"] == "LATEST_STATUS"
    assert [t["tool"] for t in result["tools_used"]] == ["query_adf_logs"]
    assert result["escalation_decision"] == "NONE"
