
"""Conservative contradiction checks for generated MLOps answers."""

import math
import re

from app.agent.response_quality import normalize_text


def detect_contradictions(
    answer: str,
    tool_results: list[dict],
) -> list[str]:
    """Detect simple claims conflicting with verified tool results."""

    text = normalize_text(answer)
    issues = set()

    status_conflicts = {
        "FAILED": r"\b(success|succes|reussi|running)\b|\ben cours\b",
        "SUCCESS": r"\b(failed|echec|echoue|running)\b|\ben cours\b",
        "RUNNING": r"\b(failed|echec|echoue|success|succes|reussi)\b",
    }

    for result in tool_results:
        if result.get("ok") is not True:
            continue

        name = result.get("tool")
        data = result.get("data")

        if not isinstance(data, dict):
            continue

        if name == "get_pipeline_status":
            status = data.get("status")
            pattern = status_conflicts.get(status)

            if pattern and re.search(pattern, text):
                issues.add("PIPELINE_STATUS_CONFLICT")

        elif name == "get_model_metrics":
            expected_rates = set()

            for key in (
                "error_rate_pct",
                "invalid_input_rate_pct",
            ):
                value = data.get(key)

                if (
                    isinstance(value, (int, float))
                    and not isinstance(value, bool)
                    and math.isfinite(value)
                ):
                    expected_rates.add(float(value))

            percentages = re.findall(
                r"(?<!\w)(\d+(?:[.,]\d+)?)\s*%",
                text,
            )

            for percentage in percentages:
                value = float(
                    percentage.replace(",", ".")
                )

                if value not in expected_rates:
                    issues.add("UNVERIFIED_PERCENTAGE")

    # The agent's tool registry cannot create or approve tickets.
    ticket_claim = (
        r"\b(?:ticket|incident)\b"
        r"[^\n.!?]{0,80}"
        r"\b(?:a ete|est)\s+(?:cree|approuve)\b"
    )

    if re.search(ticket_claim, text):
        issues.add("UNVERIFIED_TICKET_ACTION")

    return sorted(issues)
