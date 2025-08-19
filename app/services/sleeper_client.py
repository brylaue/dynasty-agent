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

    async def get_player_lookup(self) -> Dict[str, Any]:
        return await self.get_players()

    @staticmethod
    def _player_view(p: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "player_id": p.get("player_id") or p.get("player_id"),
            "full_name": p.get("full_name") or (f"{p.get('first_name','')} {p.get('last_name','')}").strip(),
            "position": p.get("position"),
            "team": p.get("team"),
            "status": p.get("status"),
            "age": p.get("age"),
        }

    async def resolve_player_list(self, player_ids: List[str]) -> List[Dict[str, Any]]:
        catalog = await self.get_player_lookup()
        resolved: List[Dict[str, Any]] = []
        for pid in player_ids or []:
            p = catalog.get(pid)
            if p:
                v = dict(self._player_view(p))
                v["player_id"] = pid
                resolved.append(v)
            else:
                resolved.append({"player_id": pid, "full_name": pid})
        return resolved

    async def build_roster_detail(self, roster_id: int, league_id: Optional[str] = None) -> Dict[str, Any]:
        rosters = await self.get_rosters(league_id)
        target = None
        for r in rosters:
            if r.get("roster_id") == roster_id:
                target = r
                break
        if not target:
            return {"error": "roster not found", "roster_id": roster_id}
        users = await self.get_user_id_to_display_name(league_id)
        owner_id = target.get("owner_id")
        owner = users.get(owner_id, owner_id)
        starters_ids = target.get("starters", []) or []
        player_ids = target.get("players", []) or []
        bench_ids = [pid for pid in player_ids if pid not in starters_ids]
        starters = await self.resolve_player_list(starters_ids)
        bench = await self.resolve_player_list(bench_ids)
        return {
            "roster_id": roster_id,
            "owner": owner,
            "starters": starters,
            "bench": bench,
            "record": {
                "wins": target.get("settings", {}).get("wins"),
                "losses": target.get("settings", {}).get("losses"),
                "ties": target.get("settings", {}).get("ties"),
            },
        }