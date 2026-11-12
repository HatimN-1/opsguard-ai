"""Regression tests for a user asking about a fictitious error code."""

from app.agent.intent_router import mentioned_error_code
from app.agent.orchestrator import _run_agent_impl


class NoLLMClient:
    def chat(self, **kwargs):
        raise AssertionError("An explicit runbook lookup must not call Ollama")


def test_unknown_error_code_is_extracted():
    question = (
        "Mon pipeline ETL rencontre une erreur critique "
        "DISTRIBUTED_MEMORY_CORRUPTION_XYZ_999. "
        "Recherche la procédure de résolution correspondante."
    )
    assert mentioned_error_code(question) == "DISTRIBUTED_MEMORY_CORRUPTION_XYZ_999"


def test_generic_pipeline_question_has_no_error_code():
    assert mentioned_error_code("Analyse le pipeline etl_orders_daily.") is None
    assert mentioned_error_code("Cherche la procédure de l'incident INC-001") is None


def test_unknown_runbook_is_reported_without_hallucination(monkeypatch):
    calls = []

    def fake_tool(name, arguments):
        calls.append((name, arguments))
        return {"ok": False, "tool": name, "error": "NOT_FOUND"}

    monkeypatch.setattr("app.agent.orchestrator.execute_tool", fake_tool)
    question = (
        "Mon pipeline ETL rencontre une erreur critique "
        "DISTRIBUTED_MEMORY_CORRUPTION_XYZ_999. "
        "Les données semblent corrompues. Recherche la procédure de résolution."
    )
    result = _run_agent_impl(question, client=NoLLMClient())

    assert result["status"] == "completed"
    assert calls == [("search_runbook", {
        "error_code": "DISTRIBUTED_MEMORY_CORRUPTION_XYZ_999",
    })]
    assert result["tool_call_count"] == 1
    assert result["tools_used"][0]["error"] == "NOT_FOUND"
    assert result["tools_used"][0]["selection_source"] == "deterministic"
    assert "Aucune procédure documentée" in result["answer"]
    assert "cause exacte" in result["answer"]
    assert "investigation humaine" in result["answer"]
    assert "get_pipeline_status" not in str(result)


def test_known_runbook_is_retrieved(monkeypatch):
    def fake_tool(name, arguments):
        assert name == "search_runbook"
        assert arguments == {"error_code": "SCHEMA_VALIDATION_ERROR"}
        return {"ok": True, "tool": name, "data": [{
            "runbook_id": "RB-001",
            "human_approval_required": True,
            "diagnostic_steps": ["Compare source and expected schemas."],
        }]}

    monkeypatch.setattr("app.agent.orchestrator.execute_tool", fake_tool)
    result = _run_agent_impl(
        "L'erreur SCHEMA_VALIDATION_ERROR est survenue. "
        "Recherche la procédure correspondante.",
        client=NoLLMClient(),
    )
    assert result["status"] == "completed"
    assert result["tools_used"][0]["ok"] is True
    assert "RB-001" in result["answer"]
    assert "validation humaine" in result["answer"]


def test_runbook_technical_failure_not_confused_with_not_found(monkeypatch):
    def fake_tool(name, arguments):
        return {"ok": False, "tool": name, "error": "TOOL_EXECUTION_ERROR"}

    monkeypatch.setattr("app.agent.orchestrator.execute_tool", fake_tool)
    result = _run_agent_impl(
        "Erreur DIST_FAIL_123. Recherche le runbook.",
        client=NoLLMClient(),
    )
    assert "consultation des procédures a échoué" in result["answer"]
    assert "Aucune procédure documentée n'a été trouvée" not in result["answer"]
