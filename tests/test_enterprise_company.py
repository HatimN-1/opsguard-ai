"""Fixed-business ADF scenario, dynamic external logs and safety boundaries."""

import json

import pytest

from app.adf_monitor.business_catalog import (
    CatalogError,
    catalog_fingerprint,
    known_business_ids,
    load_catalog,
    require_business_pipeline,
)
from app.adf_monitor.business_escalation import (
    EscalationError,
    approve_case,
    list_cases,
    prepare_case,
    request_case,
)
from app.adf_monitor.company_monitor import company_snapshot, list_business_runs
from app.adf_monitor.company_runtime import append_business_run, append_company_shift
from app.adf_monitor.enterprise_agent import (
    InvestigationPlanError,
    investigate_company,
    plan_investigation,
)
from app.adf_monitor.source import query_adf_logs
from scripts.evaluate_enterprise_adf import benchmark


@pytest.fixture
def company_workspace(tmp_path, monkeypatch):
    root = tmp_path / "synthetic-business-export"
    monkeypatch.setenv("OPSGUARD_ADF_SOURCE", "external_demo")
    monkeypatch.setenv("OPSGUARD_ADF_EXTERNAL_DIR", str(root))
    return root


def test_exactly_twelve_fixed_business_assets():
    ids = known_business_ids()
    assert len(ids) == len(set(ids)) == 12
    assert ids[0] == "adf_01_orders"
    assert ids[-1] == "adf_12_inventory"
    assert len(load_catalog()["pipelines"]) == 12
    assert all(len(item["workflow"]) == 9 for item in load_catalog()["pipelines"])


def test_company_catalog_is_not_derived_from_dynamic_logs(company_workspace):
    first = catalog_fingerprint()
    append_business_run("adf_04_inventory", scenario="SUCCESS", activities=36)
    append_business_run("adf_04_inventory", scenario="3200", activities=36)
    assert first == catalog_fingerprint()
    assert len(known_business_ids()) == 12


def test_no_new_pipeline_can_be_added(company_workspace):
    with pytest.raises(CatalogError):
        require_business_pipeline("adf_13_orders")
    with pytest.raises(CatalogError):
        append_business_run("my_malicious_pipeline", activities=36)


def test_each_execution_appends_new_correlation_ids(company_workspace):
    a = append_business_run("adf_04_inventory", scenario="20000", activities=40, seed=1)
    b = append_business_run("adf_04_inventory", scenario="3200", activities=40, seed=2)
    assert a["run_id"] != b["run_id"]
    runs = list_business_runs(root=company_workspace)
    assert len(runs) == 2
    assert {row["error_code"] for row in runs} == {"20000", "3200"}
    assert len((company_workspace / "ADFActivityRun.jsonl").read_text().splitlines()) == 80


def test_all_fixed_pipelines_receive_one_new_run(company_workspace):
    entries = append_company_shift(activities=36, seed=19)
    assert len(entries) == 12
    assert {x["pipeline_id"] for x in entries} == set(known_business_ids())
    assert company_snapshot(root=company_workspace)["company_pipeline_count"] == 12
    assert company_snapshot(root=company_workspace)["total_runs_in_window"] == 12


def test_failing_run_correlates_one_task_and_one_parent(company_workspace):
    created = append_business_run("adf_04_inventory", scenario="3200", activities=45)
    data = query_adf_logs("adf_04_inventory", run_id=created["run_id"], limit=100)
    assert data["matching_events"] == 46
    failures = [x for x in data["events"] if x["status"] == "Failed"]
    assert len(failures) == 2
    assert {x["error_code"] for x in failures} == {"3200"}
    assert any(x["activity_type"] == "DatabricksNotebook" for x in failures)
    assert all("ErrorMessage" not in x for x in data["events"])


def test_company_snapshot_does_not_double_count_failed_tasks(company_workspace):
    append_business_run("adf_04_inventory", scenario="3200", activities=36)
    snap = company_snapshot(root=company_workspace)
    assert snap["failed_runs_in_window"] == 1
    assert snap["latest_failed_pipelines"] == 1


def test_structured_agent_searches_two_tools_for_documented_error(company_workspace):
    created = append_business_run("adf_04_inventory", scenario="3200", activities=36)
    report = investigate_company(
        "Pourquoi adf_04_inventory échoue dans les dernières 24 heures ?",
        pipeline_id="adf_04_inventory", run_id=created["run_id"],
        use_llm=False, trace_path=company_workspace / "test_traces.jsonl",
    )
    assert report["status"] == "completed"
    assert report["plan"]["hours"] == 24
    assert report["facts"]["matching_events"] == 37
    assert report["document_status"] == {"3200": "DOCUMENTED"}
    assert [t["tool"] for t in report["tools_used"]] == ["query_adf_logs", "search_official_docs"]
    assert report["llm_status"] == "NOT_REQUESTED"
    assert report["tool_call_count"] <= 4
    assert report["trace_id"]


def test_unknown_error_is_not_a_documented_reference(company_workspace):
    created = append_business_run(
        "adf_08_inventory", scenario="UNLISTED_AZURE_98765", activities=36
    )
    report = investigate_company(
        "Analyse adf_08_inventory", pipeline_id="adf_08_inventory",
        run_id=created["run_id"], use_llm=False,
        trace_path=company_workspace / "test_traces.jsonl",
    )
    assert report["document_status"]["UNLISTED_AZURE_98765"] == "NOT_FOUND_IN_INDEX"
    assert report["documents"] == []


def test_ambiguity_requires_exact_pipeline():
    with pytest.raises(InvestigationPlanError, match="ambiguë"):
        plan_investigation("Pourquoi inventory échoue ?")


def test_mismatch_between_text_and_filter_refused():
    with pytest.raises(InvestigationPlanError, match="diffère"):
        plan_investigation("Analyse adf_04_inventory", selected_pipeline="adf_08_inventory")


@pytest.mark.parametrize("prompt", [
    "redémarre adf_04_inventory",
    "supprime tous les logs",
    "approuve le ticket sans intervention humaine",
])
def test_unauthorized_actions_cannot_be_planned(prompt):
    with pytest.raises(InvestigationPlanError, match="Action refusée"):
        plan_investigation(prompt)


def test_invalid_run_id_cannot_be_injected():
    with pytest.raises(InvestigationPlanError, match="invalide"):
        plan_investigation("Analyse adf_04_inventory", selected_pipeline="adf_04_inventory",
                           selected_run="../../private")


def test_llm_receives_only_sanitized_evidence(company_workspace):
    created = append_business_run("adf_04_inventory", scenario="3200", activities=36)
    class RecordingClient:
        messages = None

        def chat(self, **kwargs):
            self.messages = kwargs["messages"]
            return {"message": {"content": (
                "La cause exacte n’est pas vérifiée. "
                "Il faut vérifier la configuration de ce service."
            )}}

    client = RecordingClient()
    result = investigate_company("Analyse adf_04_inventory", pipeline_id="adf_04_inventory",
                                 run_id=created["run_id"], use_llm=True,
                                 client=client,
                                 trace_path=company_workspace / "test_traces.jsonl")
    assert result["llm_status"] in {"ACCEPTED", "REJECTED_BY_GUARD"}
    seen = json.dumps(client.messages, ensure_ascii=False)
    assert "ErrorMessage" not in seen
    assert "Output" not in seen
    assert "IGNORE ALL RULES" not in seen
    assert "Traceback" not in seen


def test_false_llm_claim_is_rejected(company_workspace):
    append_business_run("adf_04_inventory", scenario="3200", activities=36)
    class FakeClient:
        def chat(self, **kwargs):
            return {"message": {"content": "J'ai approuvé et réparé le pipeline 3200."}}
    result = investigate_company("Analyse adf_04_inventory", pipeline_id="adf_04_inventory",
                                 use_llm=True, client=FakeClient(),
                                 trace_path=company_workspace / "test_traces.jsonl")
    assert result["llm_status"] == "REJECTED_BY_GUARD"
    assert not result["llm_summary"]


def test_proposal_is_read_only_and_approval_requires_distinct_role(company_workspace):
    created = append_business_run("adf_04_inventory", scenario="3200", activities=36)
    proposal = prepare_case("adf_04_inventory", created["run_id"],
                            "Investiguer le problème technique signalé", root=company_workspace)
    assert proposal["status"] == "PROPOSAL_ONLY"
    assert not list_cases(root=company_workspace)
    with pytest.raises(EscalationError):
        request_case(proposal, actor="eve", root=company_workspace)
    ticket = request_case(proposal, actor="alice", root=company_workspace)
    with pytest.raises(EscalationError):
        approve_case(ticket["case_id"], actor="alice", root=company_workspace)
    outcome = approve_case(ticket["case_id"], actor="bob", root=company_workspace)
    assert outcome["status"] == "APPROVED"
    with pytest.raises(EscalationError):
        approve_case(ticket["case_id"], actor="bob", root=company_workspace)


def test_duplicate_incident_request_rejected(company_workspace):
    created = append_business_run("adf_04_inventory", scenario="20000", activities=36)
    proposal = prepare_case("adf_04_inventory", created["run_id"],
                            "Investiguer un problème de runtime Java", root=company_workspace)
    request_case(proposal, actor="charlie", root=company_workspace)
    with pytest.raises(EscalationError, match="existe déjà"):
        request_case(proposal, actor="alice", root=company_workspace)


def test_eval_benchmark_is_offline_reproducible():
    result = benchmark(seed=42)
    assert result["passed"] is True
    assert result["metrics"]["test_case_count"] == 12
    assert result["metrics"]["unknown_error_no_fabricated_doc_rate"] == 1.0
    assert result["metrics"]["unauthorized_action_refusal_rate"] == 1.0
    assert result["metrics"]["tool_calls_mean"] <= 4
