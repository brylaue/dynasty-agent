from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


LOG_PATH = "/workspace/data/logs.jsonl"


def append_agent_log(
	question: str,
	intent: Optional[str],
	preferences: Optional[Dict[str, Any]],
	sources: List[Dict[str, Any]],
	timings: Dict[str, float],
	meta: Optional[Dict[str, Any]] = None,
) -> None:
	Path(os.path.dirname(LOG_PATH)).mkdir(parents=True, exist_ok=True)
	entry = {
		"ts": time.time(),
		"question": question,
		"intent": intent,
		"preferences": preferences or {},
		"sources": sources,
		"timings_ms": {k: int(v * 1000) for k, v in (timings or {}).items()},
	}
	if meta:
		entry["meta"] = meta
	with open(LOG_PATH, "a", encoding="utf-8") as f:
		f.write(json.dumps(entry, ensure_ascii=False) + "\n")