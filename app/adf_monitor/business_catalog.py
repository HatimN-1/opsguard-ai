"""Fixed 12-pipeline ADF company scenario. Pipeline definitions never mutate at runtime."""

import hashlib
import json
import re
from pathlib import Path

CATALOG_PATH = Path(__file__).resolve().parents[2] / "data" / "company_adf_catalog.json"
ID_PATTERN = re.compile(r"adf_(?:0[1-9]|1[0-2])_(?:orders|customers|payments|inventory)\Z")


class CatalogError(ValueError):
    """The versioned business scenario is invalid or was unexpectedly modified."""


def catalog_version() -> str:
    """Expose a stable revision that can be attached to evaluation artifacts."""
    return load_catalog()["catalog_version"]


def catalog_fingerprint() -> str:
    return hashlib.sha256(CATALOG_PATH.read_bytes()).hexdigest()[:16]


def load_catalog() -> dict:
    """Validate the fixed business configuration before any operational use."""
    data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    items = data.get("pipelines", [])
    if data.get("immutable_pipeline_count") != 12 or not isinstance(items, list):
        raise CatalogError("Expected exactly twelve immutable ADF pipelines")
    ids = [item.get("pipeline_id") for item in items if isinstance(item, dict)]
    if len(ids) != 12 or len(set(ids)) != 12:
        raise CatalogError("Duplicate or missing fixed pipeline")
    if any(not isinstance(pid, str) or not ID_PATTERN.fullmatch(pid) for pid in ids):
        raise CatalogError("Invalid company pipeline identifier")
    expected = [
        f"adf_{n:02d}_{('orders', 'customers', 'payments', 'inventory')[(n - 1) % 4]}"
        for n in range(1, 13)
    ]
    if ids != expected:
        raise CatalogError("Company pipeline IDs cannot be changed")
    for item in items:
        workflow = item.get("workflow", [])
        if not isinstance(workflow, list) or len(workflow) != 9:
            raise CatalogError("Each company workflow must have nine fixed stages")
        if not all(
            isinstance(stage, dict) and stage.get("name") and stage.get("activity_type")
            for stage in workflow
        ):
            raise CatalogError("Invalid workflow stage")
    return data


def known_business_ids() -> tuple[str, ...]:
    return tuple(item["pipeline_id"] for item in load_catalog()["pipelines"])


def require_business_pipeline(pipeline_id: str) -> dict:
    for item in load_catalog()["pipelines"]:
        if item["pipeline_id"] == pipeline_id:
            return item
    raise CatalogError("Unknown pipeline: outside the company's twelve fixed assets")
