"""B01-C03 regression tests from real Northstar business UI failures."""

import pytest

from app.adf_monitor.business_catalog import known_business_ids
from app.adf_monitor.company_runtime import append_business_run, append_company_shift
from app.adf_monitor.enterprise_agent import (
    InvestigationPlanError,
    investigate_company,
    plan_investigation,
)
from app.adf_monitor.source import query_adf_logs


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    root = tmp_path / "adf-company-workspace"
    monkeypatch.setenv("OPSGUARD_ADF_SOURCE", "external_demo")
    monkeypatch.setenv("OPSGUARD_ADF_EXTERNAL_DIR", str(root))
    return root


def test_b01_latest_twelve_returns_one_row_per_pipeline_without_docs(workspace):
    append_company_shift(activities=36, seed=19)
    result = investigate_company(
        "Pour chacun des 12 pipelines, affiche uniquement sa dernière exécution : "
        "pipeline, Run ID, date UTC et statut exact.",
        hours=72, use_llm=False, trace_path=workspace / "traces.jsonl",
    )
    report = result["business_report"]
    assert result["status"] == "completed"
    assert result["plan"]["intent"] == "LATEST_STATUS"
    assert len(report["rows"]) == 12
    assert {r["pipeline_name"] for r in report["rows"]} == set(known_business_ids())
    assert all(r["run_id"] != "—" and r["timestamp_utc"] != "—" for r in report["rows"])
    assert result["tool_call_count"] == 1
    assert result["documents"] == []


def test_b02_only_code_3200_is_really_filtered(workspace):
    append_business_run("adf_04_inventory", scenario="3200", activities=36)
    append_business_run("adf_04_inventory", scenario="20000", activities=36)
    question = ("Analyse uniquement le pipeline adf_04_inventory et uniquement l'erreur "
                "3200. N'inclus pas les erreurs 20000 des autres exécutions.")
    result = investigate_company(question, use_llm=False, trace_path=workspace / "t.jsonl")
    assert result["plan"]["error_codes"] == ["3200"]
    assert result["plan"]["excluded_error_codes"] == ["20000"]
    assert result["facts"]["matching_events"] == 2
    assert {e["error_code"] for e in result["facts"]["errors"]} == {"3200"}
    assert len(result["facts"]["errors"][0]["failing_activities"]) == 1
    assert result["document_status"] == {"3200": "DOCUMENTED"}
    assert all(d["matched_error_code"] == "3200" for d in result["documents"])


def test_c01_exclusion_with_intervening_words(workspace):
    plan = plan_investigation(
        "Analyse exclusivement les événements portant le code d'erreur 3200. "
        "Exclue du rapport les événements et documents du code 20000.",
        selected_pipeline="adf_04_inventory",
    )
    assert plan["error_codes"] == ["3200"]
    assert plan["excluded_error_codes"] == ["20000"]


def test_b04_two_requested_codes_but_no_unrelated_document(workspace):
    append_business_run("adf_04_inventory", scenario="3200", activities=36)
    append_business_run("adf_04_inventory", scenario="20000", activities=36)
    append_business_run("adf_04_inventory", scenario="2200", activities=36)
    result = investigate_company(
        "Quelles causes racines des erreurs 3200 et 20000 sont confirmées ?",
        pipeline_id="adf_04_inventory", use_llm=False,
        trace_path=workspace / "t.jsonl",
    )
    assert result["facts"]["matching_events"] == 4
    assert set(result["document_status"]) == {"3200", "20000"}
    assert result["tool_call_count"] == 3


def test_b03_four_recent_runs_sorted_with_statuses(workspace):
    for scenario in ("SUCCESS", "20000", "3200", "3200"):
        append_business_run("adf_04_inventory", scenario=scenario, activities=36)
    result = investigate_company(
        "Compare les quatre dernières exécutions de adf_04_inventory. "
        "Pour chaque Run ID, donne le statut exact et le code d'erreur. "
        "Indique combien de runs distincts présentent le code 3200.",
        use_llm=True, trace_path=workspace / "t.jsonl",
    )
    rows = result["business_report"]["rows"]
    assert result["plan"]["intent"] == "RUN_COMPARISON"
    assert result["plan"]["error_codes"] == []
    assert result["plan"]["focus_error_codes"] == ["3200"]
    assert len(rows) == 4
    assert len({r["run_id"] for r in rows}) == 4
    assert [r["timestamp_utc"] for r in rows] == sorted(
        (r["timestamp_utc"] for r in rows), reverse=True
    )
    assert {r["status"] for r in rows} == {"Succeeded", "Failed"}
    assert result["business_report"]["recurrence_by_code"] == {"3200": 2}
    assert result["llm_status"] == "NOT_REQUESTED"
    assert result["tool_call_count"] == 1


def test_t04_same_code_different_runs_not_confirmed_root_cause(workspace):
    append_business_run("adf_04_inventory", scenario="3200", activities=36)
    append_business_run("adf_04_inventory", scenario="3200", activities=36)
    result = investigate_company(
        "Compare les dernières exécutions de adf_04_inventory. "
        "Est-ce que le même incident se répète ?",
        use_llm=False, trace_path=workspace / "t.jsonl",
    )
    assert result["plan"]["intent"] == "RECURRENCE"
    assert result["business_report"]["recurrence_by_code"] == {"3200": 2}
    assert "ne confirme pas la même cause racine" in result["business_report"]["summary"]


def test_global_selected_pipeline_is_not_silently_inferred():
    with pytest.raises(InvestigationPlanError, match="Sélectionner un pipeline précis"):
        plan_investigation("Pour le pipeline sélectionné, analyse le code 3200.")


def test_selected_run_pronoun_without_selection_is_not_global():
    with pytest.raises(InvestigationPlanError, match="Run ID précis"):
        plan_investigation("Analyse uniquement cette exécution.")


def test_unknown_business_pipeline_not_broadly_interpreted():
    with pytest.raises(InvestigationPlanError, match="Pipeline inconnu"):
        plan_investigation("Analyse le pipeline adf_99_unknown.")


def test_contextual_followup_inherits_exact_prior_pipeline():
    plan = plan_investigation(
        "Pour cette erreur Databricks, quelles vérifications sont recommandées ?",
        context_pipeline="adf_04_inventory",
    )
    assert plan["pipeline_id"] == "adf_04_inventory"


def test_direct_source_filter_is_bounded_and_validated(workspace):
    append_business_run("adf_04_inventory", scenario="3200", activities=36)
    append_business_run("adf_04_inventory", scenario="20000", activities=36)
    records = query_adf_logs("adf_04_inventory", error_codes=["3200"])
    assert records["matching_events"] == 2
    assert {x["error_code"] for x in records["events"]} == {"3200"}
    with pytest.raises(ValueError, match="Invalid error code filter"):
        query_adf_logs("adf_04_inventory", error_codes=["3200; drop table"])


def test_no_documentation_for_run_history_even_if_run_failed(workspace):
    append_business_run("adf_04_inventory", scenario="3200", activities=36)
    result = investigate_company(
        "Quels sont les Run IDs des quatre dernières exécutions du pipeline sélectionné ? "
        "N'ajoute aucune analyse de cause ou documentation Microsoft.",
        pipeline_id="adf_04_inventory", use_llm=False,
        trace_path=workspace / "t.jsonl",
    )
    assert result["plan"]["intent"] == "RUN_COMPARISON"
    assert result["documents"] == []
    assert result["tool_call_count"] == 1


def test_hallucinated_in_progress_status_rejected(workspace):
    from app.adf_monitor.llm_guard import validate_llm_summary
    append_business_run("adf_04_inventory", scenario="3200", activities=36)
    facts = query_adf_logs("adf_04_inventory")
    text = "Plusieurs exécutions en cours ont été observées dans ce pipeline."
    assert validate_llm_summary(text, facts, [])[1] == "UNSUPPORTED_IN_PROGRESS_CLAIM"


def test_human_confirmation_is_not_inferred_from_logs(workspace):
    from app.adf_monitor.llm_guard import validate_llm_summary
    append_business_run("adf_04_inventory", scenario="3200", activities=36)
    facts = query_adf_logs("adf_04_inventory")
    text = "Une vérification humaine a confirmé la cause racine de cette erreur."
    assert validate_llm_summary(text, facts, [])[1] == "UNVERIFIED_HUMAN_ACTION"


def test_wrong_uuid_is_rejected_even_if_pipeline_is_known(workspace):
    from app.adf_monitor.llm_guard import validate_llm_summary
    append_business_run("adf_04_inventory", scenario="3200", activities=36)
    facts = query_adf_logs("adf_04_inventory")
    text = (
        "L'exécution 11111111-1111-1111-1111-111111111111 a échoué. "
        "Il faut examiner les preuves."
    )
    assert validate_llm_summary(text, facts, [])[1] == "UNVERIFIED_RUN_ID"


def test_missing_docs_cannot_imply_no_official_docs_on_the_internet(workspace):
    from app.adf_monitor.llm_guard import validate_llm_summary
    append_business_run("adf_04_inventory", scenario="3200", activities=36)
    facts = query_adf_logs("adf_04_inventory")
    text = "Aucune documentation officielle n'existe pour cette erreur."
    assert validate_llm_summary(text, facts, [])[1] == "UNSUPPORTED_GLOBAL_DOCUMENTATION_CLAIM"


def test_false_negative_claim_for_observed_error_rejected(workspace):
    from app.adf_monitor.llm_guard import validate_llm_summary
    append_business_run("adf_04_inventory", scenario="3200", activities=36)
    facts = query_adf_logs("adf_04_inventory")
    text = "Aucune erreur structurée n'a été observée sur ce pipeline."
    assert validate_llm_summary(text, facts, [])[1] == "UNSUPPORTED_NO_ERROR_CLAIM"


def test_followup_with_one_previous_code_inherits_code_filter():
    plan = plan_investigation(
        "Pour cette erreur, retrouve les recommandations Microsoft.",
        context_pipeline="adf_04_inventory", context_error_codes=["3200"],
    )
    assert plan["pipeline_id"] == "adf_04_inventory"
    assert plan["error_codes"] == ["3200"]


def test_followup_with_two_codes_requests_explicit_disambiguation():
    with pytest.raises(InvestigationPlanError, match="Plusieurs codes"):
        plan_investigation(
            "Pour cette erreur Databricks, quelles vérifications ?",
            context_pipeline="adf_04_inventory", context_error_codes=["3200", "20000"],
        )


def test_explicit_run_id_is_a_real_query_constraint():
    sample = "866e8618-7c0f-5411-8d0f-88cd0a7f2d0d"
    plan = plan_investigation(
        f"Analyse adf_04_inventory run ID {sample} uniquement."
    )
    assert plan["run_id"] == sample


def test_selected_run_cannot_conflict_with_run_in_question():
    with pytest.raises(InvestigationPlanError, match="diffère"):
        plan_investigation(
            "Analyse adf_04_inventory run ID 866e8618-7c0f-5411-8d0f-88cd0a7f2d0d",
            selected_run="11111111-1111-1111-1111-111111111111",
        )


def test_pronoun_without_any_context_is_not_interpreted_as_all_pipelines():
    with pytest.raises(InvestigationPlanError, match="ambiguë"):
        plan_investigation("Pour cette erreur Databricks, donne la cause probable.")


@pytest.mark.parametrize(
    "question",
    [
        (
            "Pour chacun des 12 pipelines, affiche le dernier Run ID, le statut et la "
            "date UTC. Ne fournis pas une liste d'incidents historiques."
        ),
        "Affiche le dernier Run ID et le statut de tous les pipelines.",
        "Quel est le dernier Run ID et le statut de chaque pipeline ?",
        "Quel est le dernier Run ID et le statut des douze pipelines ?",
    ],
)
def test_global_latest_run_id_routes_to_twelve_pipeline_statuses(question):
    plan = plan_investigation(question)
    assert plan["intent"] == "LATEST_STATUS"
    assert plan["pipeline_id"] is None
    assert plan["search_documentation"] is False


def test_exact_ui_global_question_returns_twelve_rows_without_llm_or_docs(workspace):
    append_company_shift(activities=36, seed=19)
    result = investigate_company(
        "Pour chacun des 12 pipelines, affiche le dernier Run ID, le statut "
        "et la date UTC. Ne fournis pas une liste d'incidents historiques.",
        hours=72, use_llm=True, trace_path=workspace / "trace_latest_global.jsonl",
    )
    assert result["status"] == "completed"
    assert result["plan"]["intent"] == "LATEST_STATUS"
    assert len(result["business_report"]["rows"]) == 12
    assert result["llm_status"] == "NOT_REQUESTED"
    assert result["tool_call_count"] == 1
    assert result["documents"] == []
