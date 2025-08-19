from __future__ import annotations

import httpx
from typing import Any, Dict, List
from langchain_core.tools import tool
from tavily import TavilyClient
import os

_tavily = None

def _get_tavily():
	global _tavily
	if _tavily is None:
		api_key = os.getenv('TAVILY_API_KEY')
		_tavily = TavilyClient(api_key=api_key) if api_key else None
	return _tavily

@tool("web_search", return_direct=False)
async def web_search(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
	"""Search the web for recent news using Tavily (if configured). Returns a list of {'title','url','content'}.
	If Tavily is not available, returns empty list."""
	tc = _get_tavily()
	if not tc:
		return []
	resp = tc.search(query=query, max_results=max_results)
	results = resp.get('results', []) if isinstance(resp, dict) else []
	return results

@tool("web_fetch", return_direct=False)
async def web_fetch(url: str) -> Dict[str, Any]:
	"""Fetch the content of a URL and return text (best-effort)."""
	try:
		async with httpx.AsyncClient(timeout=10.0) as client:
			resp = await client.get(url)
			resp.raise_for_status()
			text = resp.text
			return {"url": url, "text": text[:10000]}
	except Exception as e:
		return {"url": url, "error": str(e)}