"""Verify only NEW OpsGuard tool events after a marker; never print payloads.

Does not touch existing agent logs, source code, or model responses.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

SELECTION_FIELDS = (
    "selection_source", "selection_reason", "selection_category",
    "tool_selection_reason", "tool_selection_source", "source", "reason",
)
DURATION_FIELDS = ("duration_ms", "latency_ms", "elapsed_ms", "tool_duration_ms")


def _count_lines(path: Path) -> int:
    with path.open("rb") as fh:
        return sum(1 for _ in fh)


def _has_nonempty_string(obj: dict[str, Any], names: tuple[str, ...]) -> bool:
    return any(isinstance(obj.get(k), str) and bool(obj[k].strip()) for k in names)


def _has_duration(obj: dict[str, Any]) -> bool:
    for key in DURATION_FIELDS:
        value = obj.get(key)
        if (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
            and value >= 0
        ):
            return True
    return False


def mark(source: Path, marker: Path) -> int:
    if not source.is_file():
        print("ERREUR: fichier de traces introuvable.")
        return 2
    lines = _count_lines(source)
    marker.parent.mkdir(parents=True, exist_ok=True)
    # Only store counts/file size, never trace contents or secrets.
    marker.write_text(
        json.dumps({"lines": lines, "size_bytes": source.stat().st_size}, indent=2),
        encoding="utf-8",
    )
    print(f"POINT DE DEPART ENREGISTRE : {lines} ligne(s).")
    print("Effectuer une investigation dans l'interface puis lancer --check.")
    return 0


def check(source: Path, marker: Path) -> int:
    if not source.is_file() or not marker.is_file():
        print("ERREUR: traces ou marqueur introuvables; executer --mark d'abord.")
        return 2
    try:
        meta = json.loads(marker.read_text(encoding="utf-8"))
        baseline = meta["lines"]
        old_size = meta["size_bytes"]
        if not isinstance(baseline, int) or baseline < 0 or not isinstance(old_size, int):
            raise ValueError("invalid marker")
    except (ValueError, OSError, KeyError, TypeError):
        print("ERREUR: marqueur invalide.")
        return 2
    if source.stat().st_size < old_size:
        print("INCONCLUSIF : fichier de traces tronque/remplace depuis --mark.")
        return 2
    counts = {
        "new_trace_rows": 0,
        "invalid_json_rows": 0,
        "rows_without_events": 0,
        "tool_requested": 0,
        "tool_completed": 0,
        "selection_present": 0,
        "duration_present": 0,
    }
    with source.open("r", encoding="utf-8-sig") as fh:
        for n, line in enumerate(fh, start=1):
            if n <= baseline or not line.strip():
                continue
            counts["new_trace_rows"] += 1
            try:
                record = json.loads(line)
            except (ValueError, TypeError):
                counts["invalid_json_rows"] += 1
                continue
            events = record.get("events") if isinstance(record, dict) else None
            if not isinstance(events, list):
                counts["rows_without_events"] += 1
                continue
            for event in events:
                if not isinstance(event, dict):
                    continue
                kind = event.get("event_type")
                if kind == "TOOL_REQUESTED":
                    counts["tool_requested"] += 1
                    counts["selection_present"] += _has_nonempty_string(event, SELECTION_FIELDS)
                elif kind == "TOOL_COMPLETED":
                    counts["tool_completed"] += 1
                    counts["duration_present"] += _has_duration(event)

    print("VERIFICATION DES TRACES NOUVELLES — lecture seule")
    for key, value in counts.items():
        print(f"  {key}: {value}")
    if counts["new_trace_rows"] == 0 or counts["tool_requested"] == 0:
        print("INCONCLUSIF: aucune nouvelle investigation avec appel d'outil observee.")
        return 2
    passed = (
        counts["invalid_json_rows"] == 0
        and counts["rows_without_events"] == 0
        and counts["tool_requested"] == counts["tool_completed"]
        and counts["selection_present"] == counts["tool_requested"]
        and counts["duration_present"] == counts["tool_completed"]
    )
    print("RESULTAT : " + ("PASS (champs presents)" if passed else "FAIL (metadonnees manquantes)"))
    print("Note: PASS verifie la presence des champs, pas l'exactitude des valeurs ni la confidentialite globale.")
    return 0 if passed else 1


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    modes = ap.add_mutually_exclusive_group(required=True)
    modes.add_argument("--mark", action="store_true")
    modes.add_argument("--check", action="store_true")
    ap.add_argument("--source", type=Path, default=Path("logs/agent_traces.jsonl"))
    ap.add_argument("--marker", type=Path, default=Path("outputs/fresh_trace_probe_marker.json"))
    args = ap.parse_args()
    raise SystemExit(mark(args.source, args.marker) if args.mark else check(args.source, args.marker))


if __name__ == "__main__":
    main()
