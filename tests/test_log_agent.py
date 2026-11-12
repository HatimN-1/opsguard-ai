"""Integration and security regression tests for log-based agent requests."""

from app.agent.intent_router import mentioned_log_run_id, wants_pipeline_logs
from app.agent.orchestrator import _run_agent_impl
from app.agent.tool_registry import execute_tool
from app.simulation.log_generator import generate_simulated_run


class NoLLMClient:
    def chat(self, **kwargs):
        raise AssertionError("This path must not send raw log content to an LLM")


def test_log_intent_requires_a_log_related_word():
    assert wants_pipeline_logs("Analyse les logs du pipeline etl_orders_daily")
    assert wants_pipeline_logs("Montre le journal de etl_orders_daily")
    assert not wants_pipeline_logs("Analyse le pipeline etl_orders_daily")


def test_structured_run_id_validation():
    assert mentioned_log_run_id("run SIM-aabbccddeeff") == "SIM-aabbccddeeff"
    assert mentioned_log_run_id("run ../secrets") is None


def test_unknown_run_does_not_fabricate_an_incident():
    result = _run_agent_impl(
        "Analyse les logs du pipeline etl_orders_daily pour "
        "l'exécution SIM-000000000000.",
        client=NoLLMClient(),
    )
    assert "Aucun journal simulé valide" in result["answer"]
    assert result["tools_used"][0]["tool"] == "get_pipeline_logs"
    assert result["tools_used"][0]["error"] == "NOT_FOUND"


def test_agent_can_diagnose_run_and_lookup_existing_runbook(tmp_path, monkeypatch):
    import app.simulation.log_store as store

    monkeypatch.setattr(store, "SIMULATED_LOG_DIR", tmp_path)
    created = generate_simulated_run(
        "etl_orders_daily", "schema_error", directory=tmp_path
    )
    result = _run_agent_impl(
        f"Analyse les logs du pipeline etl_orders_daily "
        f"pour l'exécution {created['run_id']} et cherche la procédure.",
        client=NoLLMClient(),
    )
    assert result["status"] == "completed"
    assert result["tool_call_count"] == 2
    assert [item["tool"] for item in result["tools_used"]] == [
        "get_pipeline_logs", "search_runbook"
    ]
    assert "SCHEMA_VALIDATION_ERROR" in result["answer"]
    assert "colonne customer_id" in result["answer"]
    assert "L3" in result["answer"]
    assert "RB-001" in result["answer"]
    assert "SIMULÉS" in result["answer"]
    assert "validation humaine" in result["answer"]


def test_unknown_error_runbook_is_not_fabricated(tmp_path, monkeypatch):
    import app.simulation.log_store as store

    monkeypatch.setattr(store, "SIMULATED_LOG_DIR", tmp_path)
    created = generate_simulated_run(
        "etl_orders_daily", "unknown_error", directory=tmp_path
    )
    result = _run_agent_impl(
        f"Analyse les logs du pipeline etl_orders_daily "
        f"pour l'exécution {created['run_id']}.",
        client=NoLLMClient(),
    )
    assert result["tool_call_count"] == 2
    assert result["tools_used"][1]["error"] == "NOT_FOUND"
    assert "Aucun runbook disponible" in result["answer"]
    assert "cause exacte" in result["answer"]


def test_no_logs_available_requires_generation(tmp_path, monkeypatch):
    import app.simulation.log_store as store

    monkeypatch.setattr(store, "SIMULATED_LOG_DIR", tmp_path)
    result = _run_agent_impl(
        "Analyse les logs du pipeline etl_customers_daily.", client=NoLLMClient()
    )
    assert result["status"] == "completed"
    assert "Lance un scénario" in result["answer"]


def test_log_tool_rejects_path_traversal_and_extra_args():
    result = execute_tool(
        "get_pipeline_logs",
        {"pipeline_id": "../../../etc", "run_id": "latest"},
    )
    assert result["error"] == "INVALID_ARGUMENTS"
    result = execute_tool(
        "get_pipeline_logs",
        {"pipeline_id": "etl_orders_daily", "run_id": "../secret"},
    )
    assert result["error"] == "INVALID_ARGUMENTS"
    result = execute_tool(
        "get_pipeline_logs",
        {"pipeline_id": "etl_orders_daily", "extra": "surprise"},
    )
    assert result["error"] == "INVALID_ARGUMENTS"


def test_logs_without_pipeline_id_ask_for_clarification():
    result = _run_agent_impl("Analyse les logs de la dernière exécution.", client=NoLLMClient())
    assert "précise un pipeline connu" in result["answer"]
    assert result["tool_call_count"] == 0
