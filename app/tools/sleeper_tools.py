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


@tool("find_player", return_direct=False)
async def find_player(player_name: str) -> Dict[str, Any]:
    """Fuzzy search a player by name and return {'player_id','full_name'}. Use this to convert names to ids when needed."""
    assert _sleeper_client is not None, "Sleeper client not set"
    match = await _sleeper_client.get_player_id_fuzzy(player_name)
    return match or {}

@tool("get_player_news", return_direct=False)
async def get_player_news(player_name: str, limit: int = 3) -> Dict[str, Any]:
    """Get recent news about a player by name. Returns {'player':'Name','items':[{'title','description','url'}]}.
    Sources may include Sleeper trending and RSS aggregator. """
    assert _sleeper_client is not None, "Sleeper client not set"
    match = await _sleeper_client.get_player_id_fuzzy(player_name)
    if not match:
        return {"player": player_name, "items": []}
    # For now, reuse trending adds/drops and filter by name; RSS handled in /api/news.
    adds = await _sleeper_client.get_trending_players(trend_type="add", lookback_hours=72, limit=50)
    drops = await _sleeper_client.get_trending_players(trend_type="drop", lookback_hours=72, limit=50)
    items: List[Dict[str, Any]] = []
    needle = (match["full_name"] or player_name).lower()
    for blob in adds + drops:
        if needle in (str(blob).lower()):
            items.append({"title": f"Trending: {blob.get('player_id')}", "description": str(blob)[:280]})
        if len(items) >= limit:
            break
    return {"player": match["full_name"], "items": items}

@tool("resolve_players", return_direct=False)
async def resolve_players(player_ids: List[str]) -> List[Dict[str, Any]]:
    """Resolve a list of Sleeper player_ids into [{'player_id','full_name','position','team'}]."""
    assert _sleeper_client is not None, "Sleeper client not set"
    return await _sleeper_client.resolve_player_list(player_ids or [])