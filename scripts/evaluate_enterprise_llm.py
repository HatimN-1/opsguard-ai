"""Evaluate Northstar ADF retrieval and, optionally, the real local Qwen3 model.

Examples:
  python -m scripts.evaluate_enterprise_llm --smoke --check
  python -m scripts.evaluate_enterprise_llm --live --smoke --export-review
  python -m scripts.evaluate_enterprise_llm --live --repetitions 2 --export-review
"""

import argparse
import csv
import json
import sys
from pathlib import Path

from app.adf_monitor.llm_evaluation import run_evaluation

ROOT = Path(__file__).resolve().parents[1]
FIELDS = (
    "case_id", "repetition", "pipeline_id", "expected_error_code",
    "expected_document_status", "llm_status", "response", "review_flags",
    "fidelity", "cautious_causality", "safe_actions", "appropriate_french",
    "review_notes",
)


def write_review(path: Path, rows: list[dict], *, overwrite: bool = False) -> None:
    """Export model text only when explicitly requested by the local operator."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation protects annotations from accidental reruns.
    mode = "w" if overwrite else "x"
    with path.open(mode, encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            safe = dict(row)
            response = safe.get("response", "")
            if isinstance(response, str) and response.lstrip().startswith(("=", "+", "-", "@")):
                safe["response"] = "'" + response
            writer.writerow(safe)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Call Ollama/Qwen3 on each scenario")
    parser.add_argument("--smoke", action="store_true", help="Use three representative cases")
    parser.add_argument("--case", help="Select one EVAL-XX case")
    parser.add_argument("--max-cases", type=int, default=None)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--check", action="store_true", help="Fail on retrieval/security regression"
    )
    parser.add_argument(
        "--export-review", action="store_true", help="Save model text for human review"
    )
    parser.add_argument("--overwrite-review", action="store_true")
    parser.add_argument("--output", type=Path, help="Override report JSON location")
    parser.add_argument("--review-path", type=Path, help="Override optional review CSV location")
    args = parser.parse_args()

    if args.export_review and not args.live:
        parser.error("--export-review requires --live")
    if args.overwrite_review and not args.export_review:
        parser.error("--overwrite-review requires --export-review")
    if args.review_path and not args.export_review:
        parser.error("--review-path requires --export-review")

    mode = "live" if args.live else "baseline"
    report, review = run_evaluation(
        mode=mode, smoke=args.smoke, only=args.case,
        max_cases=args.max_cases, repetitions=args.repetitions, seed=args.seed,
    )
    output_path = args.output or ROOT / "outputs" / (
        "enterprise_llm_evaluation.json" if args.live else "enterprise_retrieval_evaluation.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("\nOpsGuard AI — Northstar ADF Experiment")
    print("Mode:", report["evaluation_mode"])
    print("Cases:", report["selected_cases"], "Repetitions:", report["repetitions"])
    print("Retrieval/security checks:", "PASS" if report["checks_passed"] else "FAIL")
    for name, value in report["metrics"].items():
        print(f"  {name}: {value}")
    print("Report (metadata only):", output_path)
    print("Semantic factual fidelity: NOT automatically scored; human review required")
    if args.export_review:
        review_path = args.review_path or ROOT / "outputs" / "enterprise_llm_manual_review.csv"
        try:
            write_review(review_path, review, overwrite=args.overwrite_review)
        except FileExistsError:
            print("Review file already exists; use --review-path or --overwrite-review.")
            sys.exit(2)
        print("Manual review (contains model text — keep private):", review_path)
    if args.check and not report["checks_passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
