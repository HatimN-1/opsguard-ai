
"""Evaluate language and factual coverage of agent responses."""

import json
from collections.abc import Callable
from pathlib import Path

from app.agent.orchestrator import run_agent
from app.agent.response_quality import score_response

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "agent_eval_cases.json"
REPORT = ROOT / "outputs" / "response_quality.json"

# Reference facts from the project's simulated datasets.
# Alternatives allow French/English status labels
# and common numeric formatting variations.
EXPECTED_FACTS = {
    "EVAL-001": {
        "pipeline_id": [
            "etl_orders_daily",
        ],
        "pipeline_failed": [
            "FAILED", "échoué", "échec",
            "en erreur",
        ],
        "error_code": [
            "SCHEMA_VALIDATION_ERROR",
        ],
        "runbook_id": [
            "RB-001",
        ],
    },
    "EVAL-002": {
        "pipeline_id": [
            "etl_customers_daily",
        ],
        "pipeline_success": [
            "SUCCESS", "succès", "réussi",
            "sans erreur",
        ],
    },
    "EVAL-003": {
        "model_id": [
            "fraud_detection_v1",
            "Fraud Detection",
        ],
        "error_rate": [
            "4.5%", "4,5%",
            "4.5 %", "4,5 %",
        ],
        "invalid_input_rate": [
            "8%", "8 %",
        ],
    },
}


def evaluate_cases(
    cases: list[dict],
    *,
    agent_runner: Callable[[str], dict] = run_agent,
) -> dict:
    """Evaluate answers without retaining their text."""

    if not cases:
        raise ValueError("Evaluation dataset cannot be empty")

    results = []

    for case in cases:
        case_id = case["id"]

        if case_id not in EXPECTED_FACTS:
            raise ValueError(
                f"No reference facts for {case_id}"
            )

        print(f"\nRunning {case_id}")

        response = agent_runner(
            case["question"]
        )

        quality = score_response(
            response.get("answer", ""),
            EXPECTED_FACTS[case_id],
        )

        passed = (
            response.get("status") == "completed"
            and quality["passed"]
        )

        result = {
            "case_id": case_id,
            "passed": passed,
            "status": response.get("status"),
            "trace_id": response.get("trace_id"),
            "latency_ms": response.get("latency_ms"),
            "detected_language": quality[
                "detected_language"
            ],
            "language_ok": quality["language_ok"],
            "fact_coverage": quality["fact_coverage"],
            "missing_facts": quality["missing_facts"],
        }

        results.append(result)

        print("Result:", "PASS" if passed else "FAIL")
        print(
            "Detected language:",
            result["detected_language"],
        )
        print(
            "Fact coverage:",
            f"{result['fact_coverage']:.0%}",
        )
        print(
            "Missing facts:",
            result["missing_facts"],
        )

    passed_count = sum(
        item["passed"]
        for item in results
    )

    return {
        "model": "qwen3:1.7b",
        "total_cases": len(results),
        "passed_cases": passed_count,
        "quality_pass_rate": round(
            passed_count / len(results),
            4,
        ),
        "results": results,
    }


def main() -> None:
    """Run response quality evaluation on local Qwen3."""

    cases = json.loads(
        DATASET.read_text(
            encoding="utf-8"
        )
    )

    report = evaluate_cases(cases)

    REPORT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    REPORT.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\n" + "=" * 45)
    print("OpsGuard AI - Response Quality")
    print("=" * 45)

    print(
        f"Passed: {report['passed_cases']}"
        f"/{report['total_cases']}"
    )

    print(
        "Quality pass rate: "
        f"{report['quality_pass_rate']:.1%}"
    )

    print(f"Report: {REPORT}")


if __name__ == "__main__":
    main()
