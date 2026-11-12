"""Administrator-only local log simulator for the fixed 12-pipeline company."""

import argparse
import json

from app.adf_monitor.business_catalog import known_business_ids
from app.adf_monitor.company_runtime import (
    append_business_run,
    append_company_shift,
    available_scenarios,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--pipeline", choices=known_business_ids())
    selection.add_argument("--all", action="store_true")
    parser.add_argument("--scenario", choices=available_scenarios(), default="RANDOM")
    parser.add_argument("--activities", type=int, default=90)
    parser.add_argument("--seed", type=int)
    args = parser.parse_args()
    if args.all:
        if args.scenario != "RANDOM":
            parser.error("--scenario can only be specified with --pipeline")
        rows = append_company_shift(activities=args.activities, seed=args.seed)
    else:
        rows = [append_business_run(args.pipeline, scenario=args.scenario,
                                    activities=args.activities, seed=args.seed)]
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    print("SYNTHÉTIQUE : aucune exécution ADF réelle ni modification de pipeline.")


if __name__ == "__main__":
    main()
