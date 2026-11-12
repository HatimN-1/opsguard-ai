"""Score operator-reviewed Qwen3 explanations; never auto-judge semantic truth.

Fill fidelity, cautious_causality, safe_actions, appropriate_french
with yes or no in the optional evaluation review CSV.
"""

import argparse
import csv
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

REVIEW_FIELDS = (
    "fidelity", "cautious_causality", "safe_actions", "appropriate_french"
)
VALID = {"yes": True, "no": False, "oui": True, "non": False}


def score_reviews(path: Path) -> dict:
    """Count only fully annotated, accepted summaries as evaluated text."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not set(REVIEW_FIELDS).issubset(set(reader.fieldnames or [])):
            raise ValueError("Review CSV is missing required fields")
        if not {"case_id", "repetition", "llm_status"}.issubset(
            set(reader.fieldnames or [])
        ):
            raise ValueError("Review CSV lacks case identifiers")
        all_rows = list(reader)

    accepted = [row for row in all_rows if row.get("llm_status") == "ACCEPTED"]
    reviewed = []
    for row in accepted:
        values = [str(row.get(field, "")).strip().casefold() for field in REVIEW_FIELDS]
        if all(item in VALID for item in values):
            judgments = dict(zip(REVIEW_FIELDS, (VALID[v] for v in values), strict=True))
            reviewed.append((row, judgments))
    totals = Counter({field: 0 for field in REVIEW_FIELDS})
    all_valid = 0
    for _, judgment in reviewed:
        for field in REVIEW_FIELDS:
            totals[field] += judgment[field]
        all_valid += all(judgment.values())
    count = len(reviewed)
    return {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "method": "HUMAN_ANNOTATED_FOUR_DIMENSION_RUBRIC_V1",
        "reviewed_accepted_summaries": count,
        "accepted_summaries_total": len(accepted),
        "review_coverage": round(count / len(accepted), 4) if accepted else None,
        "rates": {
            key: round(totals[key] / count, 4) if count else None
            for key in REVIEW_FIELDS
        },
        "all_four_dimensions_pass_rate": round(all_valid / count, 4) if count else None,
        "limitations": [
            "Manual ratings can be subjective; report rubric and reviewer procedure",
            "Unreviewed answers are excluded, not silently considered correct",
            "Results apply to the annotated synthetic benchmark only",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, default=Path("outputs/enterprise_llm_manual_review.csv")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("outputs/enterprise_llm_review_scores.json")
    )
    args = parser.parse_args()
    result = score_reviews(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("OpsGuard AI — Manual factual review")
    print("Reviewed:", result["reviewed_accepted_summaries"], "/",
          result["accepted_summaries_total"])
    for name, value in result["rates"].items():
        print(f"  {name}: {value}")
    print("All dimensions:", result["all_four_dimensions_pass_rate"])
    print("Report (no model text):", args.output)


if __name__ == "__main__":
    main()
