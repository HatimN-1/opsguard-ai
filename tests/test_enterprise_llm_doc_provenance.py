"""Regression: documented official sources must not be denied by Qwen prose."""

import pytest

from app.adf_monitor.llm_guard import validate_llm_summary

FACTS = {
    "pipeline_name": "adf_04_inventory",
    "pipeline_names": ["adf_04_inventory"],
    "errors": [{"error_code": "3200", "run_id": "run-1"}],
    "evidence_events": [{"error_code": "3200", "run_id": "run-1"}],
}
DOCS = [{
    "doc_id": "MS-ADF-3200",
    "matched_error_code": "3200",
    "title": "Échec d'accès à Azure Databricks",
    "summary_fr": "Erreur 3200 liée à l'authentification Databricks.",
    "checks_fr": ["Vérifier les identifiants du service lié."],
}]


@pytest.mark.parametrize("statement", [
    "Aucune documentation officielle n'a été trouvée pour ce code.",
    "Aucune documentation officielle n'a été trouvée pour le code 3200.",
    "Aucune documentation officielle n'est pas disponible pour ce code.",
    "Aucune documentation officielle n'a été retrouvée pour cette erreur.",
])
def test_retrieved_docs_cannot_be_denied(statement):
    accepted, reason = validate_llm_summary(statement, FACTS, DOCS)
    assert accepted == ""
    assert reason == "CONTRADICTS_RETRIEVED_DOCUMENTATION"


def test_missing_docs_can_be_reported_as_not_found_in_local_search():
    statement = "Aucune documentation officielle n'a été trouvée pour ce code."
    assert validate_llm_summary(statement, FACTS, []) == (statement, None)


def test_documentation_present_statement_remains_accepted():
    statement = "La documentation officielle du code 3200 est retrouvée."
    assert validate_llm_summary(statement, FACTS, DOCS) == (statement, None)


def test_mixed_errors_negative_claim_about_other_unknown_code_is_allowed():
    facts = {
        **FACTS,
        "errors": [
            {"error_code": "3200", "run_id": "run-1"},
            {"error_code": "98765", "run_id": "run-2"},
        ],
    }
    statement = "Aucune documentation officielle n'a été trouvée pour le code 98765."
    assert validate_llm_summary(statement, facts, DOCS) == (statement, None)


def test_mixed_errors_negative_claim_about_documented_code_rejected():
    facts = {**FACTS, "errors": [
        {"error_code": "3200", "run_id": "run-1"},
        {"error_code": "98765", "run_id": "run-2"},
    ]}
    statement = "Aucune documentation officielle n'a été trouvée pour le code 3200."
    assert validate_llm_summary(statement, facts, DOCS)[1] == "CONTRADICTS_RETRIEVED_DOCUMENTATION"
