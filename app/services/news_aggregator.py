from __future__ import annotations

import re
import time
from typing import Any, Dict, List

import httpx
from xml.etree import ElementTree as ET


RSS_SOURCES = [
	{"name": "ESPN NFL", "url": "https://www.espn.com/espn/rss/nfl/news"},
	{"name": "NFL.com", "url": "https://www.nfl.com/rss/rsslanding?searchString=home"},
	{"name": "Yahoo NFL", "url": "https://sports.yahoo.com/nfl/rss/"},
]


async def fetch_rss_news(sources: List[Dict[str, str]] | None = None, timeout_s: float = 10.0) -> List[Dict[str, Any]]:
	items: List[Dict[str, Any]] = []
	sources = sources or RSS_SOURCES
	async with httpx.AsyncClient(timeout=timeout_s) as client:
		for src in sources:
			try:
				resp = await client.get(src["url"])  # type: ignore
				resp.raise_for_status()
				root = ET.fromstring(resp.content)
				for it in root.findall(".//item"):
					title = (it.findtext("title") or "").strip()
					link = (it.findtext("link") or "").strip()
					desc = (it.findtext("description") or "").strip()
					pub = (it.findtext("pubDate") or "").strip()
					items.append({
						"source": src["name"],
						"title": title,
						"link": link,
						"description": desc,
						"published": pub,
					})
			except Exception:
				continue
	return items


def filter_news_by_names(items: List[Dict[str, Any]], names: List[str]) -> List[Dict[str, Any]]:
	norm_names = [n.lower() for n in names if n]
	filtered: List[Dict[str, Any]] = []
	for it in items:
		t = (it.get("title") or "").lower()
		d = (it.get("description") or "").lower()
		if any(n in t or n in d for n in norm_names):
			filtered.append(it)
	return filtered