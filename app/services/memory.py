from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

from pydantic import BaseModel


class UserPreferences(BaseModel):
    favorite_team: str | None = None
    roster_owner_name: str | None = None
    risk_tolerance: str | None = None  # low, medium, high
    roster_id: int | None = None


class MemoryStore:
    def __init__(self, filepath: str = "/workspace/data/memory.json") -> None:
        self.filepath = filepath
        Path(os.path.dirname(filepath)).mkdir(parents=True, exist_ok=True)
        if not os.path.exists(filepath):
            self._write({})

    def _read(self) -> Dict[str, Any]:
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _write(self, data: Dict[str, Any]) -> None:
        tmp_path = self.filepath + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, self.filepath)

    def get_preferences(self, user_id: str = "default") -> UserPreferences:
        data = self._read()
        raw = data.get(user_id, {})
        return UserPreferences(**raw)

    def set_preferences(self, prefs: UserPreferences, user_id: str = "default") -> None:
        data = self._read()
        data[user_id] = prefs.model_dump(exclude_none=True)
        self._write(data)