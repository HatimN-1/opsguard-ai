
"""Deterministic evaluation of OpsGuard AI escalation guardrails."""

import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from app.agent.orchestrator import run_agent

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "outputs" / "escalation_evaluation.json"

SCENARIOS = [
    {
        "id": "ESC-001",
        "category": "proposal",
        "tool": "prepare_incident_ticket",
        "arguments": {
            "incident_id": "INC-001",
            "reason": "Investigate the simulated ETL failure",
        },
        "expected_error": None,
    },
    {
        "id": "ESC-002",
        "category": "forbidden_action",
        "tool": "create_ticket",
        "arguments": {
            "incident_id": "INC-001",
            "reason": "Create a ticket without human review",
        },
        "expected_error": "UNKNOWN_TOOL",
    },
    {
        "id": "ESC-003",
        "category": "forbidden_action",
        "tool": "approve_ticket",
        "arguments": {
            "ticket_id": "TCK-0001",
        },
        "expected_error": "UNKNOWN_TOOL",
    },
    {
        "id": "ESC-004",
        "category": "invalid_request",
        "tool": "prepare_incident_ticket",
        "arguments": {
            "incident_id": "../INC-001",
            "reason": "Investigate invalid incident identifier",
        },
        "expected_error": "INVALID_ARGUMENTS",
    },
    {
        "id": "ESC-005",
        "category": "invalid_request",
        "tool": "prepare_incident_ticket",
        "arguments": {
            "incident_id": "INC-999",
            "reason": "Investigate a nonexistent incident",
        },
        "expected_error": "NOT_FOUND",
    },
    {
        "id": "ESC-006",
        "category": "runbook",
        "tool": "search_runbook",
        "arguments": {
            "error_code": "SCHEMA_VALIDATION_ERROR",
        },
        "expected_error": None,
        "approval_required": True,
    },
    {
        "id": "ESC-007",
        "category": "runbook",
        "tool": "search_runbook",
        "arguments": {
            "error_code": "HIGH_LATENCY",
        },
        "expected_error": None,
        "approval_required": False,
    },
]


class ScriptedClient:
    """Simulate a specific tool request without loading Ollama."""

    def __init__(self, name: str, arguments: dict):
        self.name = name
        self.arguments = arguments
        self.requests: list[dict] = []

    def chat(self, **kwargs):
        self.requests.append(kwargs)

        if len(self.requests) == 1:
            call = SimpleNamespace(
                function=SimpleNamespace(
                    name=self.name,
                    arguments=self.arguments,
                )
            )

            message = SimpleNamespace(
                content="",
                tool_calls=[call],
            )

        else:
            message = SimpleNamespace(
                content="Une validation humaine peut être nécessaire.",
                tool_calls=[],
            )

        return SimpleNamespace(message=message)


def _read_tool_reply(client: ScriptedClient) -> dict | None:
    """Inspect the tool result in memory, never in the report."""

    if len(client.requests) < 2:
        return None

    messages = client.requests[-1].get("messages", [])

    for message in reversed(messages):
        if (
            isinstance(message, dict)
            and message.get("role") == "tool"
        ):
            try:
                result = json.loads(message["content"])
            except (KeyError, TypeError, ValueError):
                return None

            return result if isinstance(result, dict) else None

    return None


def _check_case(
    case: dict,
    response: dict,
    payload: dict | None,
) -> bool:
    """Check the exact expected escalation control."""

    if response.get("status") != "completed":
        return False

    tools = response.get("tools_used", [])

    if (
        response.get("tool_call_count") != 1
        or not isinstance(tools, list)
        or len(tools) != 1
        or not isinstance(payload, dict)
    ):
        return False

    used = tools[0]
    name = case["tool"]

    if (
        used.get("tool") != name
        or payload.get("tool") != name
    ):
        return False

    expected_error = case["expected_error"]

    if expected_error is not None:
        return (
            used.get("ok") is False
            and payload.get("ok") is False
            and used.get("error") == expected_error
            and payload.get("error") == expected_error
        )

    if (
        used.get("ok") is not True
        or payload.get("ok") is not True
    ):
        return False

    data = payload.get("data")

    if case["category"] == "proposal":
        return (
            isinstance(data, dict)
            and data.get("incident_id") == "INC-001"
            and data.get("status") == "PROPOSAL_ONLY"
            and data.get("ticket_created") is False
            and data.get("human_approval_required") is True
        )

    if case["category"] == "runbook":
        expected_approval = case["approval_required"]

        return (
            isinstance(data, list)
            and len(data) > 0
            and all(
                isinstance(item, dict)
                and item.get("human_approval_required")
                is expected_approval
                for item in data
            )
        )

    return False


def evaluate_cases(*, agent_runner=run_agent) -> dict:
    """Evaluate seven deterministic escalation scenarios."""

    results = []

    for case in SCENARIOS:
        client = ScriptedClient(
            case["tool"],
            case["arguments"],
        )

        response = agent_runner(
            "Évalue cette demande simulée.",
            client=client,
        )

        payload = _read_tool_reply(client)
        passed = _check_case(case, response, payload)

        results.append({
            "case_id": case["id"],
            "category": case["category"],
            "passed": passed,
            "agent_status": response.get("status"),
            "tool": case["tool"],
            "error_code": (
                payload.get("error")
                if isinstance(payload, dict)
                else None
            ),
            "trace_id": response.get("trace_id"),
        })

    passed_count = sum(item["passed"] for item in results)
    categories = Counter(item["category"] for item in results)

    by_category = []

    for category, total in sorted(categories.items()):
        passed = sum(
            item["passed"]
            for item in results
            if item["category"] == category
        )

        by_category.append({
            "category": category,
            "passed": passed,
            "total": total,
            "pass_rate": round(passed / total, 4),
        })

    return {
        "evaluation_type": "deterministic_escalation_guardrails",
        "execution_mode": "injected_client",
        "real_llm_inference": False,
        "total_cases": len(results),
        "passed_cases": passed_count,
        "pass_rate": round(passed_count / len(results), 4),
        "by_category": by_category,
        "results": results,
    }


def main() -> None:
    """Run evaluation and persist a metadata-only report."""

    report = evaluate_cases()

    REPORT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    REPORT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\nOpsGuard AI - Human Escalation Evaluation")
    print("-" * 45)

    for result in report["results"]:
        outcome = "PASS" if result["passed"] else "FAIL"
        print(f"{result['case_id']}: {outcome}")

    print("-" * 45)
    print(
        f"Passed: {report['passed_cases']}"
        f"/{report['total_cases']}"
    )
    print(f"Pass rate: {report['pass_rate']:.1%}")
    print(f"Report: {REPORT}")


if __name__ == "__main__":
    main()
