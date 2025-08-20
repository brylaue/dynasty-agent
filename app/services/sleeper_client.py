from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional, Callable, Awaitable

import httpx
from rapidfuzz import process, fuzz


class SleeperClient:
	base_url: str = "https://api.sleeper.app/v1"

	def __init__(self, default_league_id: Optional[str] = None) -> None:
		self.default_league_id = default_league_id
		self._client = httpx.AsyncClient(
			timeout=httpx.Timeout(20.0),
			limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
		)
		self._players_cache: Optional[Dict[str, Any]] = None
		self._players_cache_ts: float = 0.0
		self._cache: Dict[str, tuple[float, Any]] = {}

	async def close(self) -> None:
		await self._client.aclose()

	async def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
		url = f"{self.base_url}{path}"
		attempts = 0
		backoff = 0.5
		while True:
			try:
				resp = await self._client.get(url, params=params)
				resp.raise_for_status()
				return resp.json()
			except httpx.HTTPStatusError as e:
				status = e.response.status_code if e.response is not None else 0
				if status in (429, 500, 502, 503, 504) and attempts < 3:
					await asyncio.sleep(backoff)
					attempts += 1
					backoff *= 2
					continue
				raise

	async def _cached(self, key: str, ttl_s: float, fetch: Callable[[], Awaitable[Any]], *, force_refresh: bool = False) -> Any:
		now = time.time()
		if not force_refresh and (entry := self._cache.get(key)):
			ts, data = entry
			if now - ts < ttl_s:
				return data
		data = await fetch()
		self._cache[key] = (now, data)
		return data

	# League-level endpoints
	async def get_league(self, league_id: Optional[str] = None, *, force_refresh: bool = False) -> Dict[str, Any]:
		league_id = league_id or self.default_league_id
		key = f"league:{league_id}"
		return await self._cached(key, 600.0, lambda: self._get(f"/league/{league_id}"), force_refresh=force_refresh)

	async def get_users(self, league_id: Optional[str] = None, *, force_refresh: bool = False) -> List[Dict[str, Any]]:
		league_id = league_id or self.default_league_id
		key = f"users:{league_id}"
		return await self._cached(key, 600.0, lambda: self._get(f"/league/{league_id}/users"), force_refresh=force_refresh)

	async def get_rosters(self, league_id: Optional[str] = None, *, force_refresh: bool = False) -> List[Dict[str, Any]]:
		league_id = league_id or self.default_league_id
		key = f"rosters:{league_id}"
		return await self._cached(key, 120.0, lambda: self._get(f"/league/{league_id}/rosters"), force_refresh=force_refresh)

	async def get_matchups(self, week: int, league_id: Optional[str] = None, *, force_refresh: bool = False) -> List[Dict[str, Any]]:
		league_id = league_id or self.default_league_id
		key = f"matchups:{league_id}:{week}"
		return await self._cached(key, 120.0, lambda: self._get(f"/league/{league_id}/matchups/{week}"), force_refresh=force_refresh)

	async def get_transactions(self, week: int, league_id: Optional[str] = None, *, force_refresh: bool = False) -> List[Dict[str, Any]]:
		league_id = league_id or self.default_league_id
		key = f"transactions:{league_id}:{week}"
		return await self._cached(key, 300.0, lambda: self._get(f"/league/{league_id}/transactions/{week}"), force_refresh=force_refresh)

	async def get_nfl_state(self, *, force_refresh: bool = False) -> Dict[str, Any]:
		key = "state:nfl"
		return await self._cached(key, 30.0, lambda: self._get("/state/nfl"), force_refresh=force_refresh)

	# Players catalog is large; keep separate daily cache
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

	async def get_trending_players(self, sport: str = "nfl", trend_type: str = "add", lookback_hours: int = 24, limit: int = 25, *, force_refresh: bool = False) -> List[Dict[str, Any]]:
		params = {"lookback_hours": lookback_hours, "limit": limit}
		key = f"trending:{sport}:{trend_type}:{lookback_hours}:{limit}"
		async def fetch() -> Any:
			try:
				return await self._get(f"/players/trending/{sport}/{trend_type}", params=params)
			except httpx.HTTPStatusError as e:
				if e.response is not None and e.response.status_code == 404:
					try:
						return await self._get(f"/trending/{sport}/{trend_type}", params=params)
					except Exception:
						return []
				raise
		return await self._cached(key, 300.0, fetch, force_refresh=force_refresh)

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
		# Try to fetch this week's projected points for starters
		proj_map: Dict[str, float] = {}
		try:
			state = await self.get_nfl_state()
			week = int(state.get("week") or 1)
			matchups = await self.get_matchups(week=week, league_id=league_id)
			for m in matchups:
				if m.get("roster_id") == roster_id:
					sp = m.get("starters_points") or []
					for idx, pid in enumerate(starters_ids):
						if idx < len(sp) and sp[idx] is not None:
							proj_map[pid] = float(sp[idx])
					break
		except Exception:
			pass
		for s in starters:
			pp = proj_map.get(s.get("player_id"))
			if pp is not None:
				s["projected_points"] = round(pp, 2)
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

	async def build_weekly_projections(self, week: int, league_id: Optional[str] = None) -> List[Dict[str, Any]]:
		"""Approximate projections using starters_points from matchup data when available."""
		matchups = await self.get_matchups(week=week, league_id=league_id)
		by_roster: Dict[int, Dict[str, Any]] = {}
		for m in matchups:
			rid = m.get("roster_id")
			if rid is None:
				continue
			starters_points = m.get("starters_points") or []
			proj = sum(sp or 0 for sp in starters_points) if starters_points else None
			by_roster[rid] = {
				"roster_id": rid,
				"projected_points": proj,
				"matchup_id": m.get("matchup_id"),
			}
		return list(by_roster.values())

	async def get_trending_news(self, lookback_hours: int = 48, limit: int = 25) -> Dict[str, Any]:
		adds, drops = await asyncio.gather(
			self.get_trending_players(trend_type="add", lookback_hours=lookback_hours, limit=limit),
			self.get_trending_players(trend_type="drop", lookback_hours=lookback_hours, limit=limit),
		)
		return {"adds": adds, "drops": drops}

	async def get_player_id_fuzzy(self, name_query: str) -> Optional[Dict[str, str]]:
		catalog = await self.get_players()
		# Build name lists lazily
		names = []
		name_to_id = {}
		for pid, p in catalog.items():
			full = p.get("full_name") or ((p.get("first_name") or "") + " " + (p.get("last_name") or "")).strip()
			if full:
				names.append(full)
				name_to_id[full] = pid
		if not names:
			return None
		nearest = process.extractOne(name_query, names, scorer=fuzz.WRatio)
		if not nearest:
			return None
		best_name = nearest[0]
		pid = name_to_id.get(best_name)
		if not pid:
			return None
		return {"player_id": pid, "full_name": best_name}

	async def build_roster_detail_for_week(self, roster_id: int, week: int, league_id: Optional[str] = None) -> Dict[str, Any]:
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
		bench_ids = [pid for pid in (target.get("players") or []) if pid not in starters_ids]
		starters_named = await self.resolve_player_list(starters_ids)
		bench_named = await self.resolve_player_list(bench_ids)
		# projections for given week
		proj_map: Dict[str, float] = {}
		try:
			matchups = await self.get_matchups(week=week, league_id=league_id)
			for m in matchups:
				if m.get("roster_id") == roster_id:
					sp = m.get("starters_points") or []
					for idx, pid in enumerate(starters_ids):
						if idx < len(sp) and sp[idx] is not None:
							proj_map[pid] = float(sp[idx])
					break
		except Exception:
			pass
		for s in starters_named:
			pp = proj_map.get(s.get("player_id"))
			if pp is not None:
				s["projected_points"] = round(pp, 2)
		return {
			"roster_id": roster_id,
			"owner": owner,
			"week": week,
			"starters": starters_named,
			"bench": bench_named,
		}