from __future__ import annotations

from typing import Any, Dict, List


async def suggest_start_sit(rosters: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Heuristic placeholder: select starters already listed, and flag bench RB/WR with high-level slots
    suggestions: Dict[str, Any] = {}
    for r in rosters[:10]:
        starters = r.get("starters", [])
        bench = [p for p in (r.get("players") or []) if p not in starters]
        suggestions[r.get("owner", r.get("roster_id"))] = {
            "starters": starters[:8],
            "bench_candidates": bench[:5],
        }
    return suggestions


async def suggest_trade_targets(rosters: List[Dict[str, Any]], trending: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Heuristic placeholder: recommend trending adds not already on rosters
    owned = set()
    for r in rosters:
        for p in r.get("players", []) or []:
            owned.add(p)
    recs = []
    for t in trending:
        pid = t.get("player_id") or t.get("player_id")
        if pid and pid not in owned:
            recs.append(t)
        if len(recs) >= 10:
            break
    return {"trending_targets": recs}