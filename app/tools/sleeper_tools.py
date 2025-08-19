from __future__ import annotations

from typing import Any, Dict, List, Optional

from langchain_core.tools import tool

from app.services.sleeper_client import SleeperClient

_sleeper_client: Optional[SleeperClient] = None


def set_sleeper_client(client: SleeperClient) -> None:
    global _sleeper_client
    _sleeper_client = client


@tool("get_league_info", return_direct=False)
async def get_league_info() -> Dict[str, Any]:
    """Fetch basic info for the configured Sleeper league: scoring settings, roster positions, status."""
    assert _sleeper_client is not None, "Sleeper client not set"
    league = await _sleeper_client.get_league()
    return {
        "league_id": league.get("league_id"),
        "name": league.get("name"),
        "season": league.get("season"),
        "status": league.get("status"),
        "total_rosters": league.get("total_rosters"),
        "roster_positions": league.get("roster_positions"),
        "scoring_settings": league.get("scoring_settings"),
    }


@tool("get_rosters", return_direct=False)
async def get_rosters() -> List[Dict[str, Any]]:
    """Fetch roster summaries for each team in the league, including owner display name, starters, and FP totals."""
    assert _sleeper_client is not None, "Sleeper client not set"
    return await _sleeper_client.build_roster_summaries()


@tool("get_matchups", return_direct=False)
async def get_matchups(week: int) -> List[Dict[str, Any]]:
    """Fetch raw matchup objects for a given NFL week (int)."""
    assert _sleeper_client is not None, "Sleeper client not set"
    return await _sleeper_client.get_matchups(week=week)


@tool("search_players", return_direct=False)
async def search_players(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Search Sleeper NFL players by name prefix. Returns up to 'limit' basic player entries."""
    assert _sleeper_client is not None, "Sleeper client not set"
    catalog = await _sleeper_client.get_players()
    q = (query or "").lower()
    results: List[Dict[str, Any]] = []
    for player_id, p in catalog.items():
        name = (p.get("full_name") or p.get("first_name") or "") + " " + (p.get("last_name") or "")
        if q in name.lower():
            results.append(
                {
                    "player_id": player_id,
                    "full_name": p.get("full_name") or name.strip(),
                    "position": p.get("position"),
                    "team": p.get("team"),
                    "status": p.get("status"),
                    "age": p.get("age"),
                }
            )
        if len(results) >= limit:
            break
    return results


@tool("get_nfl_state", return_direct=False)
async def get_nfl_state() -> Dict[str, Any]:
    """Fetch current NFL season/week state from Sleeper."""
    assert _sleeper_client is not None, "Sleeper client not set"
    return await _sleeper_client.get_nfl_state()


@tool("get_trending_players", return_direct=False)
async def get_trending_players(trend_type: str = "add", lookback_hours: int = 24, limit: int = 25) -> List[Dict[str, Any]]:
    """Fetch trending players on Sleeper for the last N hours, either 'add' or 'drop'."""
    assert _sleeper_client is not None, "Sleeper client not set"
    return await _sleeper_client.get_trending_players(trend_type=trend_type, lookback_hours=lookback_hours, limit=limit)