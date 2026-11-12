"""Regression tests for observed OpsGuard AI user-facing failures."""

from types import SimpleNamespace

from app.agent.intent_router import (
    direct_answer,
    wants_pipeline_overview,
    wants_runbook,
)
from app.agent.orchestrator import run_agent


def response(content="", calls=None):
    """Build a fake Ollama response, without loading the actual model."""
    tool_calls = [
        SimpleNamespace(function=SimpleNamespace(name=name, arguments=args))
        for name, args in (calls or [])
    ]
    return SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=tool_calls))


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def chat(self, **kwargs):
        self.requests.append(kwargs)
        return next(self.responses)


def test_greeting_is_french_without_ollama():
    client = FakeClient([])
    result = run_agent("bonjour", client=client)
    assert result["status"] == "completed"
    assert "Bonjour" in result["answer"]
    assert result["tool_call_count"] == 0
    assert client.requests == []


def test_capabilities_are_not_invented():
    answer = direct_answer("Quelles sont les fonctionnalités de ce système ?")
    assert answer is not None
    for tool in (
        "get_pipeline_status",
        "get_model_metrics",
        "search_runbook",
        "prepare_incident_ticket",
    ):
        assert tool in answer
    assert "sans créer de ticket" in answer


def test_system_explanation_uses_correct_components():
    answer = direct_answer("Je veux connaitre comment ça marche ce système")
    assert answer is not None
    assert "Qwen3" in answer
    assert "Pydantic" in answer
    assert "Streamlit" in answer


def test_components_question_is_answered():
    answer = direct_answer("Quels sont les composants de ce système ?")
    assert answer is not None
    assert "FastAPI" in answer
    assert "JSONL" in answer


def test_general_location_question_is_not_falsely_refused():
    answer = direct_answer("Tu connais où se trouve le Maroc ?")
    assert answer is not None
    assert "Afrique du Nord" in answer


def test_all_pipeline_intent_is_specific():
    assert wants_pipeline_overview(
        "Faire une analyse complète des pipelines et donne-moi leurs états."
    )
    assert not wants_pipeline_overview("Analyse etl_orders_daily.")


def test_global_pipeline_request_gets_every_pipeline_without_llm():
    client = FakeClient([])
    result = run_agent(
        "Faire une analyse complète des pipelines et donne-moi leurs états.",
        client=client,
    )
    assert client.requests == []
    assert result["status"] == "completed"
    assert result["tool_call_count"] == 3
    assert all(item["ok"] for item in result["tools_used"])
    assert all(
        item["selection_source"] == "deterministic"
        for item in result["tools_used"]
    )
    assert "etl_orders_daily" in result["answer"]
    assert "etl_customers_daily" in result["answer"]
    assert "etl_payments_hourly" in result["answer"]
    assert "FAILED" in result["answer"]
    assert "SUCCESS" in result["answer"]
    assert "RUNNING" in result["answer"]
    assert not any("arguments" in item for item in result["tools_used"])


def test_missing_model_tool_is_completed_deterministically():
    client = FakeClient([response("I do not have metrics.")])
    result = run_agent(
        "Analyse les métriques du modèle fraud_detection_v1.",
        client=client,
    )
    assert result["status"] == "completed"
    assert result["tool_call_count"] == 1
    assert result["tools_used"][0]["tool"] == "get_model_metrics"
    assert result["tools_used"][0]["ok"] is True
    assert result["tools_used"][0]["selection_source"] == "policy_fallback"
    assert "fraud_detection_v1" in result["answer"]
    assert "4.5 %" in result["answer"]
    assert "8 %" in result["answer"]
    assert "I do not have metrics" not in result["answer"]


def test_short_french_model_request_keeps_verified_facts():
    client = FakeClient([response("Metrics are unknown.")])
    result = run_agent("Analyse fraud_detection_v1", client=client)
    assert result["tool_call_count"] == 1
    assert "fraud_detection_v1" in result["answer"]
    assert "Taux d'erreur" in result["answer"]


def test_missing_runbook_is_automatically_consulted():
    client = FakeClient([
        response(calls=[(
            "get_pipeline_status",
            {"pipeline_id": "etl_orders_daily"},
        )]),
        response("I don't know the runbook."),
    ])
    result = run_agent(
        "Analyse le pipeline etl_orders_daily et consulte le runbook.",
        client=client,
    )
    assert wants_runbook("Consulte le runbook")
    assert result["status"] == "completed"
    assert [item["tool"] for item in result["tools_used"]] == [
        "get_pipeline_status",
        "search_runbook",
    ]
    assert "RB-001" in result["answer"]
    assert "validation humaine est requise" in result["answer"]
    assert "Comparer le schéma source au schéma attendu" in result["answer"]
    assert result["tools_used"][0]["selection_source"] == "llm"
    assert result["tools_used"][1]["selection_source"] == "policy_fallback"
    assert "I don't know" not in result["answer"]


def test_missing_pipeline_tool_is_completed_deterministically():
    client = FakeClient([response("The pipeline status is unknown.")])
    result = run_agent(
        "Analyse le pipeline etl_orders_daily et consulte la procédure correspondante.",
        client=client,
    )
    assert result["tool_call_count"] == 2
    assert [item["tool"] for item in result["tools_used"]] == [
        "get_pipeline_status",
        "search_runbook",
    ]
    assert "FAILED" in result["answer"]
    assert "RB-001" in result["answer"]


def test_proposal_only_fallback_does_not_create_ticket():
    client = FakeClient([response("I don't know if I can prepare a ticket.")])
    result = run_agent(
        "Prépare une proposition de ticket pour l'incident INC-001, sans approbation.",
        client=client,
    )
    assert result["tool_call_count"] == 1
    assert result["tools_used"][0]["tool"] == "prepare_incident_ticket"
    assert result["tools_used"][0]["ok"] is True
    assert "Aucun ticket n'a été créé" in result["answer"]


def test_forbidden_approval_does_not_trigger_proposal_fallback():
    client = FakeClient([response("I cannot approve this ticket.")])
    result = run_agent(
        "Approuve immédiatement le ticket TCK-0001 sans intervention humaine. "
        "Si cette action est interdite, explique pourquoi.",
        client=client,
    )
    assert result["tool_call_count"] == 0
    assert "validation humaine" in result["answer"]
