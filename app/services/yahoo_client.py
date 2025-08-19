from __future__ import annotations

import os
from typing import Any, Dict, Optional

import httpx
from authlib.integrations.httpx_client import OAuth1Client


class YahooClient:
	"""Yahoo Fantasy Sports API client (OAuth1).

	Env:
	- YAHOO_CLIENT_ID or YAHOO_CONSUMER_KEY
	- YAHOO_CLIENT_SECRET or YAHOO_CONSUMER_SECRET
	- YAHOO_REDIRECT_URI (e.g., https://your-backend/api/yahoo/callback)
	"""

	base_url: str = "https://fantasysports.yahooapis.com/fantasy/v2"
	auth_url: str = "https://api.login.yahoo.com/oauth/v2/request_auth"
	request_token_url: str = "https://api.login.yahoo.com/oauth/v2/get_request_token"
	access_token_url: str = "https://api.login.yahoo.com/oauth/v2/get_token"

	def __init__(self, token: Optional[Dict[str, Any]] = None) -> None:
		client_id = os.getenv("YAHOO_CLIENT_ID") or os.getenv("YAHOO_CONSUMER_KEY")
		client_secret = os.getenv("YAHOO_CLIENT_SECRET") or os.getenv("YAHOO_CONSUMER_SECRET")
		redirect_uri = os.getenv("YAHOO_REDIRECT_URI", "http://localhost:8000/api/yahoo/callback")
		if not client_id or not client_secret:
			raise RuntimeError("Yahoo credentials not configured: set YAHOO_CLIENT_ID/SECRET or YAHOO_CONSUMER_KEY/SECRET")
		self.client_id = client_id
		self.client_secret = client_secret
		self.redirect_uri = redirect_uri
		self._oauth = OAuth1Client(
			client_id=self.client_id,
			client_secret=self.client_secret,
			callback_uri=self.redirect_uri,
			token=token or {},
		)

	async def get_request_token(self) -> Dict[str, str]:
		resp = await self._oauth.fetch_request_token(self.request_token_url)
		return resp

	def get_authorize_url(self, request_token: Dict[str, str]) -> str:
		return f"{self.auth_url}?oauth_token={request_token['oauth_token']}"

	async def fetch_access_token(self, oauth_verifier: str) -> Dict[str, str]:
		return await self._oauth.fetch_access_token(self.access_token_url, verifier=oauth_verifier)

	async def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
		url = f"{self.base_url}{path}"
		async with httpx.AsyncClient() as client:
			resp = await self._oauth.get(url, params=params, client=client)
			resp.raise_for_status()
			return resp.text  # Yahoo returns XML by default; parsing to be added

	# TODO: Implement XML parsing to JSON for leagues/teams/rosters