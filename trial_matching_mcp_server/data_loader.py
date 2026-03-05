"""Load trial-matching patient dataset."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

PACKAGE_ROOT = Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def load_dataset() -> Dict[str, Any]:
    path = PACKAGE_ROOT / "patients.json"
    with path.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def list_patients() -> List[Dict[str, Any]]:
    return load_dataset().get("patients", [])
