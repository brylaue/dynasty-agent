from __future__ import annotations

from typing import Any, Dict, List, Tuple


async def suggest_start_sit(rosters: List[Dict[str, Any]]) -> Dict[str, Any]:
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


async def build_matchup_previews(matchups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # Group matchups by roster_id -> points
    previews: List[Dict[str, Any]] = []
    by_roster: Dict[int, Dict[str, Any]] = {}
    for m in matchups:
        rid = m.get("roster_id")
        if rid is None:
            continue
        by_roster[rid] = {
            "roster_id": rid,
            "points": m.get("points", 0),
            "players": m.get("players", []),
            "starters": m.get("starters", []),
            "matchup_id": m.get("matchup_id"),
        }
    # Pair into head-to-head previews using matchup_id
    by_matchup: Dict[int, List[Dict[str, Any]]] = {}
    for item in by_roster.values():
        mid = item.get("matchup_id")
        if mid is None:
            continue
        by_matchup.setdefault(mid, []).append(item)
    for mid, teams in by_matchup.items():
        if len(teams) == 2:
            a, b = teams
            previews.append(
                {
                    "matchup_id": mid,
                    "team_a": {"roster_id": a["roster_id"], "points": a["points"]},
                    "team_b": {"roster_id": b["roster_id"], "points": b["points"]},
                    "favored_roster_id": a["roster_id"] if a["points"] >= b["points"] else b["roster_id"],
                    "projected_margin": abs((a.get("points") or 0) - (b.get("points") or 0)),
                }
            )
    return previews


async def recommend_waivers(trending_adds: List[Dict[str, Any]], limit: int = 10) -> List[Dict[str, Any]]:
    # Simple: bubble up the top trending adds with counts
    results: List[Dict[str, Any]] = []
    for t in trending_adds[: limit * 2]:
        results.append({
            "player_id": t.get("player_id"),
            "count": t.get("count", t.get("adds", 1)),
            "team": t.get("team"),
            "position": t.get("position"),
        })
        if len(results) >= limit:
            break
    return results