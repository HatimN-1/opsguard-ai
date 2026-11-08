
"""Monitoring des modèles ML à partir de données simulées."""

import json
from math import ceil
from pathlib import Path

DATA_FILE = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "model_metrics.json"
)


def get_model_metrics(model_id: str) -> dict | None:
    """Retourner les métriques d'un modèle ML."""

    with DATA_FILE.open(encoding="utf-8") as file:
        models = json.load(file)

    for model in models:
        if model["model_id"] != model_id:
            continue

        total = model["requests_total"]
        failures = model["failed_requests"]
        invalid = model["invalid_input_requests"]

        latencies = sorted(model["latencies_ms"])
        sample_size = len(latencies)

        if total > 0:
            error_rate = round(100 * failures / total, 2)
            invalid_rate = round(100 * invalid / total, 2)
        else:
            error_rate = None
            invalid_rate = None

        if sample_size > 0:
            avg_latency = round(
                sum(latencies) / sample_size, 2
            )
            p95_index = ceil(0.95 * sample_size) - 1
            p95_latency = latencies[p95_index]
        else:
            avg_latency = None
            p95_latency = None

        return {
            "model_id": model["model_id"],
            "model_name": model["model_name"],
            "version": model["version"],
            "window_start": model["window_start"],
            "window_end": model["window_end"],
            "requests_total": total,
            "failed_requests": failures,
            "invalid_input_requests": invalid,
            "error_rate_pct": error_rate,
            "invalid_input_rate_pct": invalid_rate,
            "latency_avg_ms": avg_latency,
            "latency_p95_ms": p95_latency,
            "latency_sample_size": sample_size,
            "data_mode": "simulated",
        }

    return None
