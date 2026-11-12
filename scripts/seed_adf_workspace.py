"""Create external synthetic Azure Data Factory logs without cloud credentials."""

import argparse
import json

from app.adf_monitor.seed import seed_external_adf_workspace


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pipelines", type=int, default=12)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--activities", type=int, default=60)
    parser.add_argument("--seed", type=int, default=21)
    parser.add_argument(
        "--reset", action="store_true",
        help="Remplace uniquement les deux exports ADF du workspace externe de démo.",
    )
    args = parser.parse_args()
    result = seed_external_adf_workspace(
        pipelines=args.pipelines,
        runs_per_pipeline=args.runs,
        activities_per_run=args.activities,
        seed=args.seed,
        reset=args.reset,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("ATTENTION : événements synthétiques au format inspiré d'ADF.")


if __name__ == "__main__":
    main()
