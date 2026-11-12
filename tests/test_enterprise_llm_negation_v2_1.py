"""Regression tests for negated failure statements on successful ADF runs."""

import pytest

from app.adf_monitor.company_runtime import append_business_run
from app.adf_monitor.llm_guard import validate_llm_summary
from app.adf_monitor.source import query_adf_logs


@pytest.fixture
def successful_run(tmp_path, monkeypatch):
    monkeypatch.setenv("OPSGUARD_ADF_SOURCE", "external_demo")
    monkeypatch.setenv("OPSGUARD_ADF_EXTERNAL_DIR", str(tmp_path))
    created = append_business_run(
        "adf_11_payments", scenario="SUCCESS", activities=36, root=tmp_path
    )
    return query_adf_logs("adf_11_payments", run_id=created["run_id"], root=tmp_path)


@pytest.mark.parametrize("statement", [
    (
        'La exécution du pipeline adf_11_payments a été réussie, '
        'avec un statut de "Succeeded" et aucun code d\'erreur structuré observé. '
        "Il n'y a pas d'échec détecté dans les activités ou dans le pipeline parent.\n\n."
    ),
    (
        "Le pipeline adf_11_payments est réussi. "
        "Aucun échec détecté dans les journaux de cette exécution."
    ),
    (
        "Le pipeline adf_11_payments est réussi. "
        "Il n'y a pas d'incident confirmé dans les preuves."
    ),
    (
        "Le pipeline adf_11_payments est réussi. "
        "Sans panne observée dans les logs de cette exécution."
    ),
])
def test_accepts_directly_negated_failure_observations(successful_run, statement):
    accepted, reason = validate_llm_summary(statement, successful_run, [])
    assert accepted == statement.strip()
    assert reason is None


@pytest.mark.parametrize("statement", [
    (
        "Il n'y a pas d'échec détecté sur le pipeline adf_11_payments. "
        "Pourtant le pipeline a échoué."
    ),
    (
        "Aucun incident détecté dans les logs. "
        "Mais un échec confirmé a eu lieu sur adf_11_payments."
    ),
    (
        "Le pipeline adf_11_payments est en échec. "
        "Aucune erreur détectée ailleurs."
    ),
])
def test_does_not_hide_separate_affirmative_failure(successful_run, statement):
    accepted, reason = validate_llm_summary(statement, successful_run, [])
    assert accepted == ""
    assert reason == "UNSUPPORTED_FAILURE_CLAIM"


def test_still_rejects_unsupported_run_counts(successful_run):
    text = (
        "Le pipeline adf_11_payments est réussi avec 37 exécutions. "
        "Il n'y a pas d'échec détecté."
    )
    accepted, reason = validate_llm_summary(text, successful_run, [])
    assert accepted == ""
    assert reason == "UNSUPPORTED_COUNT_CLAIM"
