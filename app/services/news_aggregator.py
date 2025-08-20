from __future__ import annotations

import re
import time
from typing import Any, Dict, List
from urllib.parse import urlparse

import httpx
from xml.etree import ElementTree as ET


RSS_SOURCES = [
	{"name": "ESPN NFL", "url": "https://www.espn.com/espn/rss/nfl/news"},
	{"name": "NFL.com", "url": "https://www.nfl.com/rss/rsslanding?searchString=home"},
	{"name": "Yahoo NFL", "url": "https://sports.yahoo.com/nfl/rss/"},
]

HTML_SOURCES = [
	{"name": "RotoBaller", "url": "https://www.rotoballer.com/player-news?sport=nfl"},
	{"name": "The Huddle", "url": "https://tools.thehuddle.com/nfl-fantasy-football-player-news/?feed=0"},
]


def _domain(url: str) -> str:
	try:
		return urlparse(url).hostname or ""
	except Exception:
		return ""


def _tl_dr(text: str, max_len: int = 180) -> str:
	text = (text or "").strip()
	if not text:
		return ""
	# first sentence heuristic
	m = re.split(r"(?<=[.!?])\s+", text)
	first = (m[0] if m else text)
	res = first if len(first) <= max_len else (first[: max_len - 1] + "…")
	return res


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
						"tldr": _tl_dr(desc or title),
						"domain": _domain(link),
					})
			except Exception:
				continue
	return items


async def fetch_html_news(timeout_s: float = 10.0) -> List[Dict[str, Any]]:
	items: List[Dict[str, Any]] = []
	async with httpx.AsyncClient(timeout=timeout_s) as client:
		for src in HTML_SOURCES:
			try:
				r = await client.get(src["url"])  # type: ignore
				r.raise_for_status()
				html = r.text
				# Naive extraction of article links and titles
				for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>([^<]{8,120})</a>', html, flags=re.IGNORECASE):
					link = m.group(1)
					title = re.sub(r"\s+", " ", m.group(2)).strip()
					if not title or not link: continue
					if not link.startswith('http'):
						# best-effort absolute link
						base = src["url"]
						u = urlparse(base)
						link = f"{u.scheme}://{u.hostname}{link}"
					# build short snippet by grabbing 140 chars around the anchor
					start = max(0, m.start() - 200); end = min(len(html), m.end() + 200)
					snippet = re.sub(r"<[^>]+>", " ", html[start:end])
					snippet = re.sub(r"\s+", " ", snippet).strip()
					items.append({
						"source": src["name"],
						"title": title,
						"link": link,
						"description": snippet[:240],
						"published": "",
						"tldr": _tl_dr(snippet or title),
						"domain": _domain(link),
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


async def gather_all_news() -> List[Dict[str, Any]]:
	# Merge RSS and HTML sources
	rss = await fetch_rss_news()
	html = await fetch_html_news()
	# Deduplicate by link
	seen = set()
	out: List[Dict[str, Any]] = []
	for it in rss + html:
		lk = it.get("link") or it.get("url")
		if lk and lk in seen: continue
		seen.add(lk)
		out.append(it)
	return out