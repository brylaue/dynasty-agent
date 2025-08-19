from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.sleeper_client import SleeperClient
from app.services.yahoo_client import YahooClient


class LeagueProvider:
	SLEEPER = "sleeper"
	YAHOO = "yahoo"


class ProviderRouter:
	def __init__(self, default_league_id: Optional[str] = None) -> None:
		self.sleeper = SleeperClient(default_league_id=default_league_id)
		self.yahoo = None  # constructed after OAuth

	def get_client(self, provider: str) -> Any:
		if provider == LeagueProvider.SLEEPER or not provider:
			return self.sleeper
		if provider == LeagueProvider.YAHOO:
			if not self.yahoo:
				self.yahoo = YahooClient()
			return self.yahoo
		raise ValueError(f"Unknown provider: {provider}")