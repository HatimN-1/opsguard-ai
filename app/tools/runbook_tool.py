
"""Search versioned technical runbooks by error code."""

import json
from pathlib import Path

DATA_FILE = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "runbooks.json"
)


def search_runbook(error_code: str) -> list[dict]:
    """Find documented procedures matching an error code."""

    normalized_code = error_code.upper()

    with DATA_FILE.open(encoding="utf-8") as file:
        runbooks = json.load(file)

    return [
        runbook
        for runbook in runbooks
        if runbook["error_code"] == normalized_code
    ]
