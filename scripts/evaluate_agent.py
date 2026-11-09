
"""Evaluate local MLOps agent tool-selection quality."""

import json
from pathlib import Path

from app.agent.orchestrator import run_agent

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "agent_eval_cases.json"
REPORT = ROOT / "outputs" / "agent_evaluation.json"


def main() -> None:
    """Evaluate the agent on predefined synthetic cases."""

    cases = json.loads(
        DATASET.read_text(encoding="utf-8")
    )

    results = []

    for case in cases:
        print(f"\nRunning {case['id']} - {case['name']}")

        response = run_agent(case["question"])

        successful_tools = {
            item["tool"]
            for item in response["tools_used"]
            if item["ok"]
        }

        expected_tools = set(case["expected_tools"])
        missing = sorted(expected_tools - successful_tools)

        passed = (
            response["status"] == "completed"
            and not missing
        )

        item = {
            "case_id": case["id"],
            "passed": passed,
            "status": response["status"],
            "expected_tools": sorted(expected_tools),
            "successful_tools": sorted(successful_tools),
            "missing_tools": missing,
            "latency_ms": response["latency_ms"],
            "trace_id": response["trace_id"],
        }

        results.append(item)

        print(
            f"Result: {'PASS' if passed else 'FAIL'}"
        )
        print(f"Tools: {sorted(successful_tools)}")
        print(f"Missing: {missing}")

    passed_count = sum(
        item["passed"] for item in results
    )

    total = len(results)

    report = {
        "model": "qwen3:1.7b",
        "total_cases": total,
        "passed_cases": passed_count,
        "tool_selection_accuracy": round(
            passed_count / total, 4
        ) if total else 0,
        "results": results,
    }

    REPORT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    REPORT.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print("\n" + "=" * 45)
    print("OpsGuard AI - Evaluation Summary")
    print("=" * 45)
    print(f"Passed: {passed_count}/{total}")
    print(
        "Tool selection accuracy: "
        f"{report['tool_selection_accuracy']:.1%}"
    )
    print(f"Report: {REPORT}")


if __name__ == "__main__":
    main()
