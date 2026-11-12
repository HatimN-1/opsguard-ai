"""Run an evidence-grounded Azure Data Factory investigation from PowerShell."""

import argparse

from app.agent.orchestrator import run_agent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "question",
        nargs="?",
        default="Analyse les erreurs récentes dans les logs Azure ADF.",
    )
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Add a clearly unverified Qwen3 interpretation (requires Ollama)",
    )
    args = parser.parse_args()
    result = run_agent(args.question, adf_llm=args.llm)
    print(result["answer"])
    print("\nTrace:", result.get("trace_id"))
    print("Outils:", result.get("tools_used"))


if __name__ == "__main__":
    main()
