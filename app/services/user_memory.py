from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

USER_DATA_ROOT = "/workspace/data/users"


def _user_dir(user_id: str) -> Path:
    p = Path(USER_DATA_ROOT) / user_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def append_chat(user_id: str, role: str, content: str) -> None:
    d = _user_dir(user_id)
    fp = d / "chat_history.jsonl"
    with open(fp, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.time(), "role": role, "content": content}, ensure_ascii=False) + "\n")


def append_event(user_id: str, kind: str, payload: Dict[str, Any]) -> None:
    d = _user_dir(user_id)
    fp = d / "events.jsonl"
    with open(fp, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.time(), "kind": kind, "data": payload}, ensure_ascii=False) + "\n")


def read_recent_chat(user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    d = _user_dir(user_id)
    fp = d / "chat_history.jsonl"
    if not fp.exists():
        return []
    lines = fp.read_text(encoding="utf-8").splitlines()[-limit:]
    return [json.loads(x) for x in lines if x.strip()]


def read_recent_events(user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    d = _user_dir(user_id)
    fp = d / "events.jsonl"
    if not fp.exists():
        return []
    lines = fp.read_text(encoding="utf-8").splitlines()[-limit:]
    return [json.loads(x) for x in lines if x.strip()]


def build_profile_summary(user_id: str, prefs: Dict[str, Any]) -> str:
    chats = read_recent_chat(user_id, limit=8)
    events = read_recent_events(user_id, limit=50)
    recent_topics = []
    for c in chats:
        if c.get("role") == "user":
            recent_topics.append(c.get("content", "")[:120])
    event_kinds = {}
    for e in events:
        k = e.get("kind")
        if k:
            event_kinds[k] = event_kinds.get(k, 0) + 1
    parts = []
    if prefs:
        parts.append(f"prefs={prefs}")
    if recent_topics:
        parts.append(f"recent_questions={recent_topics}")
    if event_kinds:
        parts.append(f"events={event_kinds}")
    return "; ".join(parts)