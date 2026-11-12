"""Create ONE metadata-only generic-orchestrator trace without contacting Ollama.

Uses the existing read-only simulated get_pipeline_status tool.
No Azure call, pipeline modification, or ticket creation.
"""

from types import SimpleNamespace

from app.agent.orchestrator import run_agent


class SimulatedModelClient:
    def __init__(self):
        self.calls = 0

    def chat(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            tool = SimpleNamespace(function=SimpleNamespace(
                name="get_pipeline_status",
                arguments={"pipeline_id": "etl_orders_daily"},
            ))
            return SimpleNamespace(message=SimpleNamespace(
                content="", tool_calls=[tool]
            ))
        return SimpleNamespace(message=SimpleNamespace(
            content="Vérification terminée.", tool_calls=[]
        ))


def main() -> int:
    result = run_agent("Peux-tu examiner ce processus ?", client=SimulatedModelClient())
    print("OpsGuard AI — contrôle de trace générique sans Ollama")
    print("  appels d'outils :", result["tool_call_count"])
    print("  identifiant de trace présent :", bool(result.get("trace_id")))
    print("  aucune opération Azure exécutée")
    return 0 if result["tool_call_count"] == 1 and result.get("trace_id") else 1


if __name__ == "__main__":
    raise SystemExit(main())
