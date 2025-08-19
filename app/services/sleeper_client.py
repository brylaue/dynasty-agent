from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional

import httpx


class SleeperClient:
    base_url: str = "https://api.sleeper.app/v1"

    def __init__(self, default_league_id: Optional[str] = None) -> None:
        self.default_league_id = default_league_id
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(20.0))
        self._players_cache: Optional[Dict[str, Any]] = None
        self._players_cache_ts: float = 0.0

    async def close(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self.base_url}{path}"
        resp = await self._client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    async def get_league(self, league_id: Optional[str] = None) -> Dict[str, Any]:
        league_id = league_id or self.default_league_id
        return await self._get(f"/league/{league_id}")

    async def get_users(self, league_id: Optional[str] = None) -> List[Dict[str, Any]]:
        league_id = league_id or self.default_league_id
        return await self._get(f"/league/{league_id}/users")

    async def get_rosters(self, league_id: Optional[str] = None) -> List[Dict[str, Any]]:
        league_id = league_id or self.default_league_id
        return await self._get(f"/league/{league_id}/rosters")

    async def get_matchups(self, week: int, league_id: Optional[str] = None) -> List[Dict[str, Any]]:
        league_id = league_id or self.default_league_id
        return await self._get(f"/league/{league_id}/matchups/{week}")

    async def get_nfl_state(self) -> Dict[str, Any]:
        return await self._get("/state/nfl")

    async def get_players(self, force_refresh: bool = False) -> Dict[str, Any]:
        now = time.time()
        if not force_refresh and self._players_cache and (now - self._players_cache_ts) < 24 * 3600:
            return self._players_cache
        data = await self._get("/players/nfl")
        # Cache full catalog; it is large. Consider disk caching in production.
        self._players_cache = data
        self._players_cache_ts = now
        return data

    async def get_user_id_to_display_name(self, league_id: Optional[str] = None) -> Dict[str, str]:
        users = await self.get_users(league_id)
        return {u.get("user_id"): (u.get("display_name") or u.get("username") or u.get("user_id")) for u in users}

    async def build_roster_summaries(self, league_id: Optional[str] = None) -> List[Dict[str, Any]]:
        rosters, user_map = await asyncio.gather(self.get_rosters(league_id), self.get_user_id_to_display_name(league_id))
        summaries: List[Dict[str, Any]] = []
        for r in rosters:
            owner_id = r.get("owner_id")
            summaries.append(
                {
                    "roster_id": r.get("roster_id"),
                    "owner_id": owner_id,
                    "owner": user_map.get(owner_id, owner_id),
                    "players": r.get("players", []),
                    "starters": r.get("starters", []),
                    "wins": r.get("settings", {}).get("wins"),
                    "losses": r.get("settings", {}).get("losses"),
                    "ties": r.get("settings", {}).get("ties"),
                    "fpts": r.get("settings", {}).get("fpts"),
                }
            )
        return summaries

    async def get_trending_players(self, sport: str = "nfl", trend_type: str = "add", lookback_hours: int = 24, limit: int = 25) -> List[Dict[str, Any]]:
        params = {"lookback_hours": lookback_hours, "limit": limit}
        return await self._get(f"/players/trending/{sport}/{trend_type}", params=params)