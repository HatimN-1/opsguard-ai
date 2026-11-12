"""Qwen grounding V3: strict guard stays enforced; retry is bounded."""

import json

from app.adf_monitor.enterprise_agent import _chat_analysis, _llm_evidence_context
from app.adf_monitor.llm_evaluation import CaptureClient

FACTS = {
    "pipeline_name": "adf_04_inventory",
    "pipeline_names": ["adf_04_inventory"],
    "run_id": "run-a1",
    "distinct_pipeline_run_count": 1,
    "pipeline_status_counts": {"Failed": 1},
    "failed_pipeline_run_count": 1,
    "errors": [{"error_code": "3200", "run_id": "run-a1"}],
    "evidence_events": [{"error_code": "3200", "activity_name": "EnrichDeltaTable_Batch_003"}],
}
DOCS = [{
    "matched_error_code": "3200",
    "title": "Échec Databricks 403",
    "summary_fr": "Le code 3200 peut correspondre à un refus d'accès Databricks.",
    "checks_fr": ["Vérifier le jeton", "Contrôler les autorisations"],
}]
DENIAL = (
    "Il n'y a pas de documentation officielle pour le code 3200. "
    "Il faut vérifier les données."
)
SAFE = (
    "Le pipeline adf_04_inventory signale le code 3200 observé. "
    "La documentation Microsoft Learn recommande de vérifier les autorisations, "
    "sans confirmer la cause racine."
)
UNSAFE = (
    "Le code 9999 a été observé. Il faut vérifier les données."
)


class SequencedClient:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        assert kwargs["think"] is False
        assert kwargs["options"]["temperature"] == 0.0
        return {"message": {"content": self.answers[len(self.calls) - 1]}}


def test_documentation_positive_anchor_is_explicit():
    ctx = _llm_evidence_context(FACTS, DOCS)
    assert ctx["documentation_retrieved"] is True
    assert ctx["documented_error_codes"] == ["3200"]
    assert ctx["pipeline_execution_status"] == "Failed"
    assert "raw_message" not in json.dumps(ctx)


def test_one_retry_resolves_document_denial_with_same_guard():
    client = SequencedClient(DENIAL, SAFE)
    accepted, reason = _chat_analysis("Pourquoi adf_04_inventory échoue ?", FACTS, DOCS, client)
    assert (accepted, reason) == (SAFE, None)
    assert len(client.calls) == 2
    assert "documented_error_codes" in client.calls[0]["messages"][1]["content"]
    assert "documentaire" in client.calls[1]["messages"][0]["content"]
    assert DENIAL not in client.calls[1]["messages"][1]["content"]


def test_good_first_answer_never_retries():
    client = SequencedClient(SAFE)
    assert _chat_analysis("Analyse adf_04_inventory", FACTS, DOCS, client) == (SAFE, None)
    assert len(client.calls) == 1


def test_rejected_retry_stays_rejected():
    client = SequencedClient(DENIAL, DENIAL)
    accepted, reason = _chat_analysis("Analyse adf_04_inventory", FACTS, DOCS, client)
    assert accepted == ""
    assert reason == "CONTRADICTS_RETRIEVED_DOCUMENTATION"
    assert len(client.calls) == 2


def test_unrelated_guard_failure_never_retries():
    client = SequencedClient(UNSAFE)
    accepted, reason = _chat_analysis("Analyse adf_04_inventory", FACTS, DOCS, client)
    assert accepted == ""
    assert reason == "UNVERIFIED_NUMBER"
    assert len(client.calls) == 1


def test_retry_error_keeps_original_rejection():
    class FailingSecond(SequencedClient):
        def chat(self, **kwargs):
            if len(self.calls) == 1:
                raise TimeoutError("Offline retry failure")
            return super().chat(**kwargs)
    client = FailingSecond(DENIAL)
    accepted, reason = _chat_analysis("Analyse adf_04_inventory", FACTS, DOCS, client)
    assert (accepted, reason) == ("", "CONTRADICTS_RETRIEVED_DOCUMENTATION")


def test_capture_client_tracks_final_answer_only():
    client = CaptureClient(SequencedClient(DENIAL, SAFE))
    accepted, reason = _chat_analysis("Analyse adf_04_inventory", FACTS, DOCS, client)
    assert (accepted, reason) == (SAFE, None)
    assert client.calls == 2
    assert client.raw == SAFE


def test_no_document_anchor_is_false():
    ctx = _llm_evidence_context(FACTS, [])
    assert ctx["documentation_retrieved"] is False
    assert ctx["documented_error_codes"] == []
