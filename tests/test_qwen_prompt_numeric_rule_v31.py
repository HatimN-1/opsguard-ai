"""Prevent V3 documentation improvements from deleting the counter-safety rule."""

from app.adf_monitor.enterprise_agent import _chat_analysis


class PromptCaptureClient:
    def __init__(self):
        self.system_prompt = ""

    def chat(self, **kwargs):
        self.system_prompt = kwargs["messages"][0]["content"]
        return {"message": {"content": (
            "Le pipeline adf_11_payments est réussi sur cette exécution. "
            "Aucune erreur structurée n'est observée dans les preuves."
        )}}


def test_qwen_v3_preserves_counter_rule_on_successful_run():
    facts = {
        "pipeline_name": "adf_11_payments",
        "run_id": "run-test",
        "distinct_pipeline_run_count": 1,
        "pipeline_status_counts": {"Succeeded": 1},
        "failed_pipeline_run_count": 0,
        "errors": [],
        "evidence_events": [],
    }
    client = PromptCaptureClient()
    accepted, reason = _chat_analysis("Ce pipeline a-t-il échoué ?", facts, [], client)
    assert "AUCUN nombre" in client.system_prompt
    assert "documentation_retrieved" in client.system_prompt
    assert accepted
    assert reason is None
