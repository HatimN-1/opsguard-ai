"""Semantic V2 regressions: counters, successful runs, and verified citations."""

import json

import pytest

from app.adf_monitor.company_runtime import append_business_run
from app.adf_monitor.enterprise_agent import (
    LLM_CONTEXT_VERSION,
    investigate_company,
)
from app.adf_monitor.llm_evaluation import run_evaluation
from app.adf_monitor.llm_guard import LLM_GUARD_VERSION, validate_llm_summary
from app.adf_monitor.source import query_adf_logs


@pytest.fixture
def env(tmp_path, monkeypatch):
    workspace = tmp_path / "fixed-company-demo"
    monkeypatch.setenv("OPSGUARD_ADF_SOURCE", "external_demo")
    monkeypatch.setenv("OPSGUARD_ADF_EXTERNAL_DIR", str(workspace))
    return workspace


class ReplyClient:
    def __init__(self, message):
        self.message = message
        self.user_context = ""
        self.system_prompt = ""

    def chat(self, **kwargs):
        self.system_prompt = kwargs["messages"][0]["content"]
        self.user_context = kwargs["messages"][1]["content"]
        return {"message": {"content": self.message}}


@pytest.mark.parametrize(("scenario", "pipeline", "expected_counts"), [
    ("SUCCESS", "adf_11_payments", ("Succeeded", 1, 0, 36, 0)),
    ("2200", "adf_07_payments", ("Failed", 0, 1, 35, 1)),
])
def test_separates_pipeline_and_activity_outcomes(env, scenario, pipeline, expected_counts):
    run = append_business_run(pipeline, scenario=scenario, activities=36, root=env)
    facts = query_adf_logs(pipeline, run_id=run["run_id"], root=env)
    status, runs_ok, runs_failed, acts_ok, acts_failed = expected_counts
    assert facts["matching_events"] == 37
    assert facts["pipeline_status_counts"].get("Succeeded", 0) == runs_ok
    assert facts["pipeline_status_counts"].get("Failed", 0) == runs_failed
    assert facts["activity_status_counts"].get("Succeeded", 0) == acts_ok
    assert facts["activity_status_counts"].get("Failed", 0) == acts_failed
    assert facts["distinct_pipeline_run_count"] == 1
    assert facts["failed_pipeline_run_count"] == runs_failed
    assert facts["pipeline_run_count"] == 1
    assert facts["activity_run_count"] == 36
    assert sum(facts["pipeline_status_counts"].values()) == 1
    assert status in facts["pipeline_status_counts"]


def test_context_for_success_exposes_one_succeeded_run_not_37_executions(env):
    run = append_business_run("adf_11_payments", scenario="SUCCESS", activities=36, root=env)
    client = ReplyClient(
        "Cette exécution du pipeline adf_11_payments est réussie. "
        "Aucune erreur structurée n'est observée, sans action de réparation."
    )
    result = investigate_company(
        "Le pipeline adf_11_payments présente-t-il un échec ?",
        pipeline_id="adf_11_payments", run_id=run["run_id"], client=client,
        trace_path=env / "test_traces.jsonl",
    )
    prompt_context = json.loads(client.user_context.split("Contexte vérifié : ", 1)[1])
    assert prompt_context["pipeline_execution_status"] == "Succeeded"
    assert prompt_context["scope"] == "ONE_RUN"
    assert prompt_context["observed_error_codes"] == []
    assert prompt_context["failing_activities"] == []
    assert "status_counts" not in prompt_context
    assert "matching_events" not in prompt_context
    assert "37 étapes" not in client.user_context
    assert "AUCUN nombre" in client.system_prompt
    assert result["llm_status"] == "ACCEPTED"
    assert result["llm_context_version"] == LLM_CONTEXT_VERSION


def test_context_for_failed_run_includes_only_failing_activity_not_parent(env):
    run = append_business_run("adf_07_payments", scenario="2200", activities=36, root=env)
    client = ReplyClient(
        "Le code 2200 apparaît lors d'une activité de copie du pipeline. "
        "Il faut vérifier les paramètres réseau et les connexions."
    )
    result = investigate_company(
        "Quelle est l'erreur observée dans adf_07_payments ?",
        pipeline_id="adf_07_payments", run_id=run["run_id"], client=client,
        trace_path=env / "test_traces.jsonl",
    )
    context = json.loads(client.user_context.split("Contexte vérifié : ", 1)[1])
    assert context["pipeline_execution_status"] == "Failed"
    assert context["observed_error_codes"] == ["2200"]
    assert len(context["failing_activities"]) == 1
    assert context["failing_activities"][0]["type"] == "Copy"
    assert result["llm_status"] == "ACCEPTED"
    assert result["llm_validation_reason"] is None


@pytest.mark.parametrize("message", [
    "Le pipeline présente 2 échecs et 35 succès. Il faut vérifier les connexions.",
    "Le pipeline présente 2 échecs et 35 succès sur les activités. Il faut vérifier.",
    "Le pipeline a réussi avec 37 étapes réussies parmi 49320337 exécutions.",
    "Il y a 37 étapes réussies et aucune erreur signalée dans les logs.",
    "Le pipeline est réussi pour 37 des exécutions sans problèmes détectés.",
    "Le pipeline est réussi pour 37 des exécutions sans panne observée.",
])
def test_rejects_the_six_observed_counter_claims(env, message):
    is_failed = "2 échecs" in message
    scenario = "2200" if is_failed else "SUCCESS"
    pipeline = "adf_07_payments" if is_failed else "adf_11_payments"
    run = append_business_run(pipeline, scenario=scenario, activities=36, root=env)
    facts = query_adf_logs(pipeline, run_id=run["run_id"], root=env)
    accepted, reason = validate_llm_summary(message, facts, [])
    assert accepted == ""
    assert reason == "UNSUPPORTED_COUNT_CLAIM"


@pytest.mark.parametrize(("scenario", "pipeline", "claim", "expected"), [
    (
        "SUCCESS", "adf_11_payments",
        "Le pipeline adf_11_payments a échoué. Il faut le réparer.",
        "UNSUPPORTED_FAILURE_CLAIM",
    ),
    (
        "2200", "adf_07_payments",
        "Le pipeline adf_07_payments a réussi. Aucun problème n'est visible.",
        "UNSUPPORTED_SUCCESS_CLAIM",
    ),
    (
        "2200", "adf_07_payments",
        "Le code 2200 correspond à un problème récurrent de copie. Vérifier les connexions.",
        "UNSUPPORTED_RECURRENCE_CLAIM",
    ),
    (
        "SUCCESS", "adf_11_payments",
        "Le pipeline adf_11_payments est réussi avec 11 tâches. Il faut vérifier.",
        "UNSUPPORTED_COUNT_CLAIM",
    ),
    (
        "SUCCESS", "adf_11_payments",
        "Le pipeline adf_11_payments est réussi avec le code 11. Il faut vérifier.",
        "UNVERIFIED_NUMBER",
    ),
])
def test_rejects_semantic_misstatements(env, scenario, pipeline, claim, expected):
    run = append_business_run(pipeline, scenario=scenario, activities=36, root=env)
    facts = query_adf_logs(pipeline, run_id=run["run_id"], root=env)
    accepted, reason = validate_llm_summary(claim, facts, [])
    assert accepted == ""
    assert reason == expected


def test_accepts_no_failure_without_false_positive(env):
    run = append_business_run("adf_11_payments", scenario="SUCCESS", activities=36, root=env)
    facts = query_adf_logs("adf_11_payments", run_id=run["run_id"], root=env)
    text = (
        "Le pipeline adf_11_payments n'a pas échoué dans cette exécution. "
        "Aucun incident et aucune erreur n'ont été observés dans les preuves."
    )
    accepted, reason = validate_llm_summary(text, facts, [])
    assert accepted == text
    assert reason is None


def test_unknown_error_must_match_actual_code_not_invented_identifier(env):
    run = append_business_run(
        "adf_08_inventory", scenario="UNLISTED_AZURE_98765", activities=36, root=env
    )
    facts = query_adf_logs("adf_08_inventory", run_id=run["run_id"], root=env)
    bad, reason = validate_llm_summary(
        "Le code UNLISTED_AZURE_99999 est observé. Aucune documentation précise n'est disponible.",
        facts, [],
    )
    assert bad == ""
    assert reason == "UNVERIFIED_ERROR_CODE"
    good = (
        "Le code UNLISTED_AZURE_98765 est observé. "
        "Aucune procédure officielle n'est disponible dans l'index consulté."
    )
    accepted, reason = validate_llm_summary(good, facts, [])
    assert accepted == good
    assert reason is None


def test_repeated_claim_can_be_supported_only_by_distinct_error_runs(env):
    first = append_business_run("adf_04_inventory", scenario="3200", activities=36, root=env)
    second = append_business_run("adf_04_inventory", scenario="3200", activities=36, root=env)
    assert first["run_id"] != second["run_id"]
    facts = query_adf_logs("adf_04_inventory", hours=24, root=env)
    text = (
        "Le code 3200 apparaît de façon récurrente dans des exécutions distinctes. "
        "Une vérification humaine reste nécessaire."
    )
    accepted, reason = validate_llm_summary(text, facts, [])
    assert accepted == text
    assert reason is None


def test_report_declares_evidence_and_guard_versions(env):
    report, _ = run_evaluation(mode="baseline", only="EVAL-11")
    assert report["llm_context_version"] == LLM_CONTEXT_VERSION
    assert report["llm_guard_version"] == LLM_GUARD_VERSION
    assert report["metrics"]["retrieval_success_rate"] == 1.0


def test_documented_http_status_is_not_automatically_observed_log_error(env):
    run = append_business_run("adf_04_inventory", scenario="3200", activities=36, root=env)
    facts = query_adf_logs("adf_04_inventory", run_id=run["run_id"], root=env)
    docs = [{"matched_error_code": "3200", "title": "Databricks HTTP 403", "summary_fr": "403 possible", "checks_fr": []}]
    unsupported = (
        "Le code 403 est observé dans les logs du pipeline. "
        "Il faut confirmer la validité des jetons."
    )
    accepted, reason = validate_llm_summary(unsupported, facts, docs)
    assert accepted == ""
    assert reason == "UNOBSERVED_ERROR_CLAIM"
    prudent = (
        "Le code 3200 a été observé. La documentation évoque un code HTTP 403 possible. "
        "Vérifier les jetons avant toute conclusion."
    )
    accepted, reason = validate_llm_summary(prudent, facts, docs)
    assert accepted == prudent
    assert reason is None
