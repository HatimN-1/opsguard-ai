"""CLI for explicitly simulated, bounded MLOps execution logs.

Example: python -m scripts.generate_simulated_logs --pipeline etl_orders_daily \
    --scenario schema_error
"""

import argparse
import json

from app.simulation.log_generator import generate_simulated_run
from app.simulation.log_store import ALLOWED_SCENARIOS, _known_pipeline_ids


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a SIMULATED journal; no ETL execution occurs."
    )
    parser.add_argument("--pipeline", required=True, choices=sorted(_known_pipeline_ids()))
    parser.add_argument("--scenario", required=True, choices=sorted(ALLOWED_SCENARIOS))
    arguments = parser.parse_args()
    data = generate_simulated_run(arguments.pipeline, arguments.scenario)
    summary = {key: value for key, value in data.items() if key != "events"}
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print("Attention : journal SIMULÉ, aucun pipeline réel n'a été exécuté.")


if __name__ == "__main__":
    main()
