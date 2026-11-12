"""Regression tests against real failure phrases seen in the enterprise UI."""

import pytest

from app.adf_monitor.llm_guard import validate_llm_summary

FIRST_RUN = "8b69cf4a-bd32-4100-a345-34d1968eb78f"
SECOND_RUN = "866e8618-7c0f-5411-8d0f-88cd0a7f2d0d"
FACTS = {
    "pipeline_name": "adf_04_inventory",
    "pipeline_names": ["adf_04_inventory"],
    "errors": [
        {"pipeline_name": "adf_04_inventory", "error_code": "3200", "run_id": FIRST_RUN},
        {"pipeline_name": "adf_04_inventory", "error_code": "3200", "run_id": SECOND_RUN},
    ],
    "run_records": [{"run_id": FIRST_RUN}, {"run_id": SECOND_RUN}],
    "evidence_events": [],
}
DOCS = [{
    "doc_id": "MS-ADF-3200",
    "matched_error_code": "3200",
    "title": "Échec d'accès à Azure Databricks (403)",
    "summary_fr": "Le code 3200 peut signaler un problème d'accès Databricks.",
}]


@pytest.mark.parametrize("response", [
    "Il n'y a pas de documentation officielle pour ce code.",
    "Il n’y a pas de documentation officielle pour le code 3200.",
    "Pas de documentation officielle pour ce code.",
    "La documentation officielle est introuvable pour ce code.",
    "Aucune documentation officielle n'a été trouvée pour ce code.",
])
def test_denial_of_existing_document_is_rejected(response):
    summary, reason = validate_llm_summary(response, FACTS, DOCS)
    assert summary == ""
    assert reason == "CONTRADICTS_RETRIEVED_DOCUMENTATION"


def test_denial_specific_to_unretrieved_code_remains_possible():
    facts = {**FACTS, "errors": [
        *FACTS["errors"],
        {"pipeline_name": "adf_04_inventory", "error_code": "98765", "run_id": SECOND_RUN},
    ]}
    response = "Il n'y a pas de documentation officielle pour le code 98765."
    assert validate_llm_summary(response, facts, DOCS) == (response, None)


def test_denial_when_no_documents_were_retrieved_remains_possible():
    response = "Il n'y a pas de documentation officielle pour ce code."
    assert validate_llm_summary(response, FACTS, []) == (response, None)


@pytest.mark.parametrize("response", [
    "Les Run IDs concernés sont run_id_12345 et run_id_67890.",
    "Le Run ID est run_id_12345.",
])
def test_fabricated_pseudo_run_ids_are_rejected(response):
    summary, reason = validate_llm_summary(response, FACTS, DOCS)
    assert summary == ""
    assert reason == "UNVERIFIED_RUN_ID"


def test_an_actual_uuid_in_evidence_is_allowed():
    response = (
        f"L'exécution {FIRST_RUN} présente le code 3200. "
        "Une vérification humaine reste nécessaire avant toute correction."
    )
    assert validate_llm_summary(response, FACTS, DOCS) == (response, None)


def test_other_uuid_is_still_rejected():
    response = (
        "L'exécution 00000000-0000-0000-0000-000000000000 a échoué. "
        "Une vérification humaine reste nécessaire avant toute correction."
    )
    assert validate_llm_summary(response, FACTS, DOCS)[1] == "UNVERIFIED_RUN_ID"


def test_denial_of_observed_repeat_code_is_rejected():
    response = "Il n'y a pas de récurrence confirmée."
    assert validate_llm_summary(response, FACTS, DOCS)[1] == (
        "CONTRADICTS_RECORDED_RECURRENCE"
    )


def test_absence_of_repeated_root_cause_is_not_a_denial_of_repeated_code():
    response = "Une cause racine identique n'est pas confirmée par les journaux."
    assert validate_llm_summary(response, FACTS, DOCS) == (response, None)


def test_no_repeat_in_single_run_does_not_trigger_rule():
    facts = {**FACTS, "errors": [FACTS["errors"][0]]}
    response = "Il n'y a pas de récurrence confirmée."
    assert validate_llm_summary(response, facts, DOCS) == (response, None)


def test_repeated_code_across_different_pipelines_is_not_a_recurrence():
    facts = {**FACTS, "pipeline_name": None, "errors": [
        {"pipeline_name": "adf_01_orders", "error_code": "3200", "run_id": FIRST_RUN},
        {"pipeline_name": "adf_02_customers", "error_code": "3200", "run_id": SECOND_RUN},
    ]}
    response = "Il n'y a pas de récurrence confirmée."
    assert validate_llm_summary(response, facts, DOCS) == (response, None)


def test_exact_rejected_ui_response_due_to_document_contradiction():
    response = (
        "Le pipeline adf_04_inventory a été analysé pour l'erreur 3200. "
        "Les run IDs concernés sont run_id_12345 et run_id_67890. "
        "Les activités échouées sont EnrichDeltaTable_Batch_003 et "
        "FailedDatabricksNotebook_110. Le code 3200 est associé à un échec "
        "d'accès à Databricks, probablement lié à un jeton expiré. "
        "Il n'y a pas de documentation officielle pour ce code, "
        "et il n'y a pas de récurrence confirmée."
    )
    assert validate_llm_summary(response, FACTS, DOCS) == (
        "", "CONTRADICTS_RETRIEVED_DOCUMENTATION"
    )
