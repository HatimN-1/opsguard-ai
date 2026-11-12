"""Unit and integration tests for bounded numeric provenance and rejection reasons."""

import json

import pytest

from app.adf_monitor.company_runtime import append_business_run
from app.adf_monitor.enterprise_agent import investigate_company
from app.adf_monitor.llm_guard import validate_llm_summary

FACTS = {
    "pipeline_name": "adf_04_inventory",
    "pipeline_names": ["adf_04_inventory"],
    "run_id": "run-a1",
    "errors": [{"error_code": "3200", "run_id": "run-a1"}],
    "evidence_events": [
        {"error_code": "3200", "activity_name": "FailedDatabricksNotebook_110"}
    ],
}
DOCS = [{
    "matched_error_code": "3200",
    "title": "Échec Databricks 403",
    "summary_fr": "Le code 3200 peut correspondre à un accès refusé (403).",
    "checks_fr": ["Vérifier les jetons", "Contrôler les droits"],
}]


@pytest.mark.parametrize("text", [
    "L'erreur 3200 observée suggère un souci d'accès. Une vérification humaine est nécessaire.",
    "Le code 403 documenté indique un accès refusé possible. Vérifier les autorisations.",
    "Le pipeline adf_04_inventory semble touché. Il faut examiner son authentification.",
])
def test_relevant_evidence_identifiers_are_accepted(text):
    accepted, reason = validate_llm_summary(text, FACTS, DOCS)
    assert accepted == text
    assert reason is None


@pytest.mark.parametrize(("text", "reason"), [
    ("Le code 9999 est confirmé. Il faut vérifier le service.", "UNVERIFIED_NUMBER"),
    ("Le code 32001 est confirmé. Il faut vérifier le service.", "UNVERIFIED_NUMBER"),
    ("Le code 3200 concerne adf_05_orders. Il faut vérifier.", "UNVERIFIED_PIPELINE"),
    ("J'ai approuvé le ticket 3200. La vérification est finie.", "FORBIDDEN_ACTION_CLAIM"),
    ("The system has failed. Please check the token.", "LANGUAGE"),
    ("La cause doit être vérifiée", "INVALID_FORMAT"),
    ("", "EMPTY_RESPONSE"),
])
def test_guard_rejects_unverified_or_unsafe_statements(text, reason):
    accepted, rejected_for = validate_llm_summary(text, FACTS, DOCS)
    assert accepted == ""
    assert rejected_for == reason


def test_question_does_not_authorize_arbitrary_numbers():
    accepted, reason = validate_llm_summary(
        "Le code 98765 est confirmé. Il faut examiner les logs.",
        FACTS, DOCS,
    )
    assert accepted == ""
    assert reason == "UNVERIFIED_NUMBER"


@pytest.fixture
def business_workspace(tmp_path, monkeypatch):
    root = tmp_path / "business-logs"
    monkeypatch.setenv("OPSGUARD_ADF_SOURCE", "external_demo")
    monkeypatch.setenv("OPSGUARD_ADF_EXTERNAL_DIR", str(root))
    return root


def test_investigation_accepts_qwen_code_and_does_not_log_raw_text(business_workspace):
    created = append_business_run("adf_04_inventory", scenario="3200", activities=36)

    class StubClient:
        def chat(self, **kwargs):
            return {"message": {"content": (
                "L'erreur 3200 observée suggère un souci d'authentification. "
                "Il faut vérifier les droits et la date d'expiration des jetons."
            )}}

    trace_file = business_workspace / "agent_traces.jsonl"
    report = investigate_company(
        "Pourquoi adf_04_inventory échoue ?",
        pipeline_id="adf_04_inventory", run_id=created["run_id"],
        client=StubClient(), use_llm=True, trace_path=trace_file,
    )
    assert report["llm_status"] == "ACCEPTED"
    assert report["llm_validation_reason"] is None
    assert "3200" in report["llm_summary"]
    trace = json.loads(trace_file.read_text(encoding="utf-8").splitlines()[-1])
    assert "L'erreur 3200" not in str(trace)
    assert "llm_summary" not in trace


def test_investigation_marks_unverified_number(business_workspace):
    created = append_business_run("adf_04_inventory", scenario="3200", activities=36)

    class StubClient:
        def chat(self, **kwargs):
            return {"message": {"content": (
                "Le code 9999 est un incident observé. "
                "Il faut vérifier les données."
            )}}

    report = investigate_company(
        "Analyse adf_04_inventory", pipeline_id="adf_04_inventory",
        run_id=created["run_id"], use_llm=True, client=StubClient(),
        trace_path=business_workspace / "trace.jsonl",
    )
    assert report["llm_status"] == "REJECTED_BY_GUARD"
    assert report["llm_validation_reason"] == "UNVERIFIED_NUMBER"
    assert report["llm_summary"] == ""
