
"""Repeated evaluation of OpsGuard AI tool selection and arguments."""

import argparse
import json
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from statistics import mean

from app.agent.orchestrator import run_agent

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "agent_eval_cases.json"
REPORT = ROOT / "outputs" / "agent_evaluation_repeated.json"


def evaluate_cases(
    cases: list[dict],
    repeats: int,
    *,
    agent_runner: Callable[..., dict] = run_agent,
) -> dict:
    """Evaluate tool selection and argument accuracy across runs."""

    if not 1 <= repeats <= 5:
        raise ValueError("Repeats must be between 1 and 5")

    if not cases:
        raise ValueError("Evaluation dataset cannot be empty")

    results = []

    for case in cases:
        expected = Counter(case["expected_tools"])

        for attempt in range(1, repeats + 1):
            print(
                f"\n{case['id']} - "
                f"Run {attempt}/{repeats}"
            )

            # Observe tool arguments in memory only.
            # Never persist them in the evaluation report.
            observed_calls: list[tuple[str, dict]] = []
            expected_arguments = case.get(
                "expected_arguments"
            )

            if expected_arguments is None:
                response = agent_runner(
                    case["question"]
                )
            else:

                def observe(
                    name: str,
                    arguments: dict,
                    *,
                    calls: list[tuple[str, dict]] = observed_calls,
                ) -> None:
                    calls.append(
                        (name, arguments.copy())
                    )

                response = agent_runner(
                    case["question"],
                    tool_observer=observe,
                )

            calls = response.get("tools_used", [])

            # Count every tool call, including duplicates.
            actual = Counter(
                item["tool"]
                for item in calls
            )

            # Count successful tool calls only.
            successful = Counter(
                item["tool"]
                for item in calls
                if item.get("ok") is True
            )

            # Detect required tools that were not
            # executed successfully.
            missing = sorted(
                name
                for name, count in expected.items()
                if successful[name] < count
            )

            # Detect unexpected tool names.
            unexpected = sorted(
                name
                for name in actual
                if name not in expected
            )

            # Detect excessive calls to a tool.
            duplicates = sorted(
                name
                for name, count in actual.items()
                if count > expected[name]
            )

            # Detect failed tool executions.
            failed = [
                item["tool"]
                for item in calls
                if item.get("ok") is not True
            ]

            # Verify the exact expected arguments.
            # Only failing tool names are saved.
            incorrect_arguments = sorted(
                name
                for name, wanted in (
                    expected_arguments or {}
                ).items()
                if (name, wanted) not in observed_calls
            )

            # An evaluation passes only when:
            # - the agent completed its response,
            # - tool names and counts match,
            # - all tool executions succeeded,
            # - expected arguments match.
            passed = (
                response.get("status") == "completed"
                and actual == expected
                and not failed
                and not incorrect_arguments
            )

            item = {
                "case_id": case["id"],
                "attempt": attempt,
                "passed": passed,
                "status": response.get("status"),
                "expected_tools": sorted(
                    case["expected_tools"]
                ),
                "actual_tools": sorted(
                    actual.elements()
                ),
                "missing_tools": missing,
                "unexpected_tools": unexpected,
                "duplicate_tools": duplicates,
                "failed_tools": failed,
                "arguments_match": (
                    not incorrect_arguments
                ),
                "incorrect_argument_tools": (
                    incorrect_arguments
                ),
                "latency_ms": response.get(
                    "latency_ms"
                ),
                "trace_id": response.get(
                    "trace_id"
                ),
            }

            results.append(item)

            print(
                "Result:",
                "PASS" if passed else "FAIL",
            )
            print(
                "Actual tools:",
                item["actual_tools"],
            )
            print("Missing:", missing)
            print("Unexpected:", unexpected)
            print("Duplicates:", duplicates)
            print("Failed tools:", failed)
            print(
                "Incorrect arguments:",
                incorrect_arguments,
            )

    passed_count = sum(
        item["passed"]
        for item in results
    )

    durations = [
        item["latency_ms"]
        for item in results
        if isinstance(
            item["latency_ms"],
            (int, float),
        )
    ]

    by_case = []

    for case in cases:
        case_results = [
            item
            for item in results
            if item["case_id"] == case["id"]
        ]

        case_passes = sum(
            item["passed"]
            for item in case_results
        )

        by_case.append({
            "case_id": case["id"],
            "passed": case_passes,
            "total": len(case_results),
            "pass_rate": round(
                case_passes / len(case_results),
                4,
            ),
        })

    return {
        "model": "qwen3:1.7b",
        "repeats_per_case": repeats,
        "total_runs": len(results),
        "passed_runs": passed_count,
        "exact_tool_match_rate": round(
            passed_count / len(results),
            4,
        ),
        "mean_latency_ms": (
            round(mean(durations), 2)
            if durations
            else None
        ),
        "by_case": by_case,
        "results": results,
    }


def main() -> None:
    """Run the evaluation and save a JSON report."""

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--repeats",
        type=int,
        default=2,
        help="Runs per case (1 to 5)",
    )

    args = parser.parse_args()

    cases = json.loads(
        DATASET.read_text(
            encoding="utf-8"
        )
    )

    report = evaluate_cases(
        cases,
        repeats=args.repeats,
    )

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
    print("OpsGuard AI - Repeated Evaluation")
    print("=" * 45)

    print(
        f"Passed: {report['passed_runs']}"
        f"/{report['total_runs']}"
    )

    print(
        "Exact tool and argument match rate: "
        f"{report['exact_tool_match_rate']:.1%}"
    )

    print(
        "Mean latency (ms):",
        report["mean_latency_ms"],
    )

    for item in report["by_case"]:
        print(
            f"{item['case_id']}: "
            f"{item['passed']}/{item['total']}"
        )

    print(f"Report: {REPORT}")


if __name__ == "__main__":
    main()
