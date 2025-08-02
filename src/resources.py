"""Utility helpers for loading bundled resources."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_SCENARIO_PATH = Path(__file__).resolve().parent.parent / "scenario.json"


def load_scenario() -> list[dict[str, Any]]:
    """Return the scenario description bundled with the package."""
    with _SCENARIO_PATH.open(encoding="utf-8") as f:
        return json.load(f)
