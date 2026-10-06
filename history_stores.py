"""
history_stores.py — OWNED BY: Person 8 (App Orchestration & Persistence)
==========================================================================

SearchHistory saves every search to a local JSON file so users can view
their history later (file handling). build_entry() turns one finished
search into the dictionary that gets saved.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import cast

from models import Medication


# ---------------------------------------------------------------------------
# SearchHistory (OOP + file handling)
# ---------------------------------------------------------------------------

class SearchHistory:
    """Persists search results to a local JSON file."""

    def __init__(self, filepath: str = "search_history.json"):
        self.filepath: Path = Path(filepath)
        if not self.filepath.exists():
            self._write([])

    def _read(self) -> list[dict[str, object]]:
        try:
            with self.filepath.open("r", encoding="utf-8") as f:
                loaded = cast(object, json.load(f))
        except (json.JSONDecodeError, FileNotFoundError):
            return []

        if not isinstance(loaded, list):
            return []

        entries: list[dict[str, object]] = []
        for entry in cast(list[object], loaded):
            if isinstance(entry, dict):
                entries.append(cast(dict[str, object], entry))
        return entries

    def _write(self, entries: list[dict[str, object]]) -> None:
        with self.filepath.open("w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)

    def add(self, entry: dict[str, object]) -> None:
        entries = self._read()
        entries.insert(0, entry)  # newest first
        self._write(entries[:100])  # cap history size

    def get_all(self) -> list[dict[str, object]]:
        return self._read()

    def clear(self) -> None:
        self._write([])


def build_entry(
    drug_name: str,
    medication: Medication,
    recalls: list[dict[str, str]],
    simplified: dict[str, str],
) -> dict[str, object]:
    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "query": drug_name,
        "generic_name": medication.generic_name,
        "brand_names": medication.brand_names,
        "recall_found": bool(recalls),
        "recall_count": len(recalls),
        "simplified": simplified,
    }
