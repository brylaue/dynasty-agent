import os
import json
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Query, Response, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List, Dict, Any

from app.agents.graph import create_research_graph
from app.services.sleeper_client import SleeperClient
from app.services.memory import MemoryStore, UserPreferences
from app.services.providers import ProviderRouter, LeagueProvider
from app.services.yahoo_client import YahooClient
from app.services.news_aggregator import gather_all_news, filter_news_by_names
from app.services.auth import verify_jwt_and_get_user_id
from app.services.user_memory import append_chat, append_event, build_profile_summary

load_dotenv()

LEAGUE_ID = os.getenv("SLEEPER_LEAGUE_ID", "1180244317552857088")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

app = FastAPI(title="Fantasy Research Agent")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=500)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

provider_router = ProviderRouter(default_league_id=LEAGUE_ID)
sleeper_client = provider_router.sleeper
research_graph = create_research_graph(sleeper_client=sleeper_client)
memory_store = MemoryStore()

YAHOO_ENABLED = (
    os.getenv("YAHOO_ENABLED", "false").lower() == "true" or (
        (os.getenv("YAHOO_CLIENT_ID") or os.getenv("YAHOO_CONSUMER_KEY")) and (os.getenv("YAHOO_CLIENT_SECRET") or os.getenv("YAHOO_CONSUMER_SECRET"))
    )
)

# Simple response cache
_RESPONSE_CACHE: Dict[str, Dict[str, Any]] = {}


class QueryBody(BaseModel):
    question: str
    user_id: str | None = "default"
    league_id: str | None = None
    provider: str | None = LeagueProvider.SLEEPER


@app.get("/api/yahoo/auth")
async def yahoo_auth_start():
    try:
        if not os.getenv("YAHOO_CLIENT_ID") or not os.getenv("YAHOO_CLIENT_SECRET"):
            return JSONResponse(status_code=400, content={"error": "Yahoo client credentials not configured (YAHOO_CLIENT_ID/SECRET)."})
        yc = YahooClient()
        token = await yc.get_request_token()
        url = yc.get_authorize_url(token)
        return RedirectResponse(url)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Yahoo auth init failed: {str(e)}"})


@app.get("/api/yahoo/callback")
async def yahoo_auth_callback(oauth_verifier: str = Query(default=None)):
    try:
        if not oauth_verifier:
            return JSONResponse(status_code=400, content={"error": "Missing oauth_verifier in callback."})
        yc = YahooClient()
        token = await yc.fetch_access_token(oauth_verifier)
        provider_router.yahoo = YahooClient(token=token)
        return RedirectResponse("/app")
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Yahoo auth callback failed: {str(e)}"})


@app.get("/api/health")
async def api_health():
    return {
        "ok": True,
        "league_id": LEAGUE_ID,
        "openai_configured": bool(OPENAI_API_KEY),
        "model": OPENAI_MODEL,
        "providers": [LeagueProvider.SLEEPER] + ([LeagueProvider.YAHOO] if YAHOO_ENABLED else []),
    }


@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/app", response_class=HTMLResponse)
async def app_page(request: Request):
    return templates.TemplateResponse("app.html", {"request": request})


@app.get("/api/rosters")
async def api_rosters(league_id: str | None = None, provider: str | None = LeagueProvider.SLEEPER):
    try:
        client = provider_router.get_client(provider or LeagueProvider.SLEEPER)
        if provider == LeagueProvider.SLEEPER and league_id:
            client = SleeperClient(default_league_id=league_id)
        return await client.build_roster_summaries(league_id=league_id)
    except Exception as e:  # pragma: no cover
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/rosters/{roster_id}")
async def api_roster_detail(roster_id: int, league_id: str | None = None, provider: str | None = LeagueProvider.SLEEPER):
    try:
        client = provider_router.get_client(provider or LeagueProvider.SLEEPER)
        return await client.build_roster_detail(roster_id, league_id=league_id)
    except Exception as e:  # pragma: no cover
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/projections")
async def api_projections(week: int | None = None, league_id: str | None = None, provider: str | None = LeagueProvider.SLEEPER):
    try:
        client = provider_router.get_client(provider or LeagueProvider.SLEEPER)
        if week is None and hasattr(client, "get_nfl_state"):
            state = await client.get_nfl_state()
            week = int(state.get("week") or 1)
        week = week or 1
        return {"week": week, "projections": await client.build_weekly_projections(week=week, league_id=league_id)}
    except Exception as e:  # pragma: no cover
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/news")
async def api_news(lookback_hours: int = 48, limit: int = 25, provider: str | None = LeagueProvider.SLEEPER, user_id: str = "default", league_id: str | None = None):
    try:
        # Try to use authenticated user
        try:
            user_from_token = verify_jwt_and_get_user_id()
            user_id = user_from_token
        except Exception:
            user_id = user_id or "default"
        prefs = memory_store.get_preferences(user_id=user_id)
        if not prefs.roster_owner_name:
            return JSONResponse(status_code=400, content={"error": "Select your team first (My Team) to enable the news feed."})
        client = provider_router.get_client(provider or LeagueProvider.SLEEPER)
        rosters = await client.build_roster_summaries(league_id=league_id)
        my_roster = next((r for r in rosters if (r.get('owner') or '').lower() == (prefs.roster_owner_name or '').lower()), None)
        team_players = set((my_roster or {}).get('players', []) or [])
        catalog = await client.get_players() if hasattr(client, 'get_players') else {}
        names = []
        for pid in team_players:
            p = catalog.get(pid)
            if p:
                names.append(p.get('full_name') or ((p.get('first_name') or '') + ' ' + (p.get('last_name') or '')).strip())
        # Gather many sources and filter to roster names
        items = await gather_all_news()
        filtered = filter_news_by_names(items, names)
        # Only link-based items with TL;DR
        filtered = [{"title": it.get("title"), "link": it.get("link"), "tldr": it.get("tldr"), "source": it.get("source"), "domain": it.get("domain") } for it in filtered if it.get("link")]
        return {"rss": filtered[: limit]}
    except Exception as e:  # pragma: no cover
        return JSONResponse(status_code=500, content={"error": str(e)})


class SetTeamBody(BaseModel):
    owner_name: str | None = None
    roster_id: int | None = None
    user_id: str | None = "default"


@app.options("/api/my-team")
async def options_my_team():
    return Response(status_code=204)


@app.get("/api/my-team")
async def set_my_team_get(owner_name: str | None = None, roster_id: int | None = None, user_id: str = "default"):
    prefs = memory_store.get_preferences(user_id=user_id or "default")
    if owner_name:
        prefs.roster_owner_name = owner_name
    if roster_id is not None:
        setattr(prefs, "roster_id", roster_id)
    memory_store.set_preferences(prefs, user_id=user_id or "default")
    return {"ok": True}


@app.post("/api/my-team")
async def set_my_team(body: SetTeamBody):
    prefs = memory_store.get_preferences(user_id=body.user_id or "default")
    if body.owner_name:
        prefs.roster_owner_name = body.owner_name
    if body.roster_id is not None:
        # store roster_id as an ad-hoc field on prefs
        setattr(prefs, "roster_id", body.roster_id)
    memory_store.set_preferences(prefs, user_id=body.user_id or "default")
    return {"ok": True}


@app.post("/api/events")
async def add_event(kind: str, payload: str = "{}", user_id: str = "default"):
    try:
        try:
            user_id = verify_jwt_and_get_user_id()
        except Exception:
            user_id = user_id or "default"
        append_event(user_id, kind=kind, payload=json.loads(payload))
        return {"ok": True}
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@app.get("/api/profile")
async def get_profile(user_id: str = "default"):
    try:
        try:
            user_id = verify_jwt_and_get_user_id()
        except Exception:
            user_id = user_id or "default"
        prefs = memory_store.get_preferences(user_id=user_id).model_dump(exclude_none=True)
        return {"user_id": user_id, "summary": build_profile_summary(user_id, prefs)}
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@app.post("/api/ask")
async def ask_agent(body: QueryBody):
    try:
        if not OPENAI_API_KEY:
            return JSONResponse(status_code=400, content={"error": "OPENAI_API_KEY is not configured on the server."})
        try:
            user_id = verify_jwt_and_get_user_id()
        except Exception:
            user_id = body.user_id or "default"
        prefs = memory_store.get_preferences(user_id=user_id).model_dump(exclude_none=True)
        profile = build_profile_summary(user_id, prefs)
        cache_key = json.dumps({"q": body.question, "prefs": prefs, "profile": profile, "league": body.league_id}, sort_keys=True)
        global _RESPONSE_CACHE
        if cache_key in _RESPONSE_CACHE:
            return _RESPONSE_CACHE[cache_key]
        append_chat(user_id, role="user", content=body.question)
        if body.league_id:
            temp_client = SleeperClient(default_league_id=body.league_id)
            temp_graph = create_research_graph(sleeper_client=temp_client)
            result = await temp_graph.ainvoke({"question": body.question, "preferences": {**prefs, "profile": profile}})
        else:
            result = await research_graph.ainvoke({"question": body.question, "preferences": {**prefs, "profile": profile}})
        intent = result.get("intent")
        sources = result.get("sources", [])
        if intent not in ("trending", "news"):
            sources = []
        else:
            sources = [s for s in (sources or []) if isinstance(s, dict) and s.get("url")]
        response = {"answer": result.get("answer", "No answer produced."), "sources": sources, "intent": intent, "data_keys": list((result.get("data") or {}).keys())}
        append_chat(user_id, role="assistant", content=response["answer"])
        _RESPONSE_CACHE[cache_key] = response
        return response
    except Exception as e:  # pragma: no cover
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/ask/stream")
async def ask_agent_stream(question: str, user_id: str = "default", league_id: str | None = None):
    async def event_gen():
        try:
            if not OPENAI_API_KEY:
                yield "event: error\n"
                yield f"data: {json.dumps({'error': 'OPENAI_API_KEY is not configured on the server.'})}\n\n"
                yield "event: end\n\n"
                return
            prefs = memory_store.get_preferences(user_id=user_id).model_dump(exclude_none=True)
            yield f"data: {json.dumps({'status': 'planning'})}\n\n"
            if league_id:
                temp_client = SleeperClient(default_league_id=league_id)
                temp_graph = create_research_graph(sleeper_client=temp_client)
                result = await temp_graph.ainvoke({"question": question, "preferences": prefs})
            else:
                result = await research_graph.ainvoke({"question": question, "preferences": prefs})
            answer = result.get("answer", "")
            intent = result.get("intent")
            sources = result.get("sources", [])
            # Filter sources same as JSON path
            if intent not in ("trending", "news"):
                sources = []
            else:
                sources = [s for s in (sources or []) if isinstance(s, dict) and s.get("url")]
            chunk_size = 200
            for i in range(0, len(answer), chunk_size):
                chunk = {"token": answer[i:i+chunk_size]}
                yield f"data: {json.dumps(chunk)}\n\n"
            yield f"event: sources\n"
            yield f"data: {json.dumps(sources)}\n\n"
            yield "event: end\n\n"
        except Exception as e:  # pragma: no cover
            yield "event: error\n"
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            yield "event: end\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@app.get("/api/me")
async def api_me(user_id: str = Depends(verify_jwt_and_get_user_id)):
    return {"user_id": user_id}


@app.get("/api/prefs")
async def get_prefs(user_id: str = "default"):
    try:
        user_from_token = verify_jwt_and_get_user_id()
        user_id = user_from_token
    except Exception:
        user_id = user_id or "default"
    return memory_store.get_preferences(user_id=user_id).model_dump(exclude_none=True)


class PrefsBody(BaseModel):
    favorite_team: str | None = None
    roster_owner_name: str | None = None
    risk_tolerance: str | None = None
    user_id: str | None = "default"


@app.post("/api/prefs")
async def set_prefs(body: PrefsBody):
    try:
        user_id = verify_jwt_and_get_user_id()
    except Exception:
        user_id = body.user_id or "default"
    prefs = UserPreferences(
        favorite_team=body.favorite_team,
        roster_owner_name=body.roster_owner_name,
        risk_tolerance=body.risk_tolerance,
    )
    memory_store.set_preferences(prefs, user_id=user_id)
    return {"ok": True}


@app.get("/api/players/search")
async def api_players_search(q: str, limit: int = 10, provider: str | None = LeagueProvider.SLEEPER):
    try:
        client = provider_router.get_client(provider or LeagueProvider.SLEEPER)
        # Sleeper-only for now
        if hasattr(client, "get_players"):
            catalog = await client.get_players()
            query = (q or "").lower()
            results: List[Dict[str, Any]] = []
            for pid, p in catalog.items():
                name = (p.get("full_name") or ((p.get("first_name") or "") + " " + (p.get("last_name") or "")).strip()).lower()
                if query in name:
                    results.append({
                        "player_id": pid,
                        "full_name": p.get("full_name") or name.title(),
                        "position": p.get("position"),
                        "team": p.get("team"),
                    })
                if len(results) >= limit:
                    break
            return results
        return []
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


class TradeEvalBody(BaseModel):
    teamA: List[str]
    teamB: List[str]
    league_id: str | None = None
    provider: str | None = LeagueProvider.SLEEPER


@app.post("/api/trade/evaluate")
async def api_trade_evaluate(body: TradeEvalBody):
    try:
        client = provider_router.get_client(body.provider or LeagueProvider.SLEEPER)
        # Build simple value map from players catalog
        catalog = await client.get_players() if hasattr(client, "get_players") else {}
        pos_base = {"QB": 60, "RB": 70, "WR": 60, "TE": 45, "K": 10, "DEF": 15}
        def value_for(pid: str) -> float:
            p = catalog.get(pid, {})
            v = float(pos_base.get(p.get("position"), 25))
            return v
        totalA = sum(value_for(pid) for pid in (body.teamA or []))
        totalB = sum(value_for(pid) for pid in (body.teamB or []))
        diff = round(totalA - totalB, 1)
        verdict = "Fair"
        if diff > 10:
            verdict = "Favors Team A"
        elif diff < -10:
            verdict = "Favors Team B"
        narrative = f"Team A total value {totalA:.1f} vs Team B {totalB:.1f}. {verdict}."
        return {"teamA_total": totalA, "teamB_total": totalB, "diff": diff, "verdict": verdict, "narrative": narrative}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/my-team/week")
async def my_team_week(week: int | None = None, league_id: str | None = None, user_id: str = "default"):
    try:
        # Determine week
        if week is None:
            state = await sleeper_client.get_nfl_state()
            week = int(state.get("week") or 1)
        # Determine my team roster_id
        prefs = memory_store.get_preferences(user_id=user_id)
        roster_id = getattr(prefs, 'roster_id', None)
        if roster_id is None:
            # try lookup by owner name
            rosters = await sleeper_client.build_roster_summaries(league_id=league_id)
            owner_name = (prefs.roster_owner_name or '').lower()
            for r in rosters:
                if (r.get('owner') or '').lower() == owner_name:
                    roster_id = r.get('roster_id')
                    break
        if roster_id is None:
            return JSONResponse(status_code=400, content={"error": "Select your team first in the roster drawer."})
        detail = await sleeper_client.build_roster_detail_for_week(roster_id=int(roster_id), week=int(week), league_id=league_id)
        return detail
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/state")
async def api_state():
    try:
        return await sleeper_client.get_nfl_state()
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


def _eligible_positions(slot: str) -> set:
    s = slot.upper()
    if s in {"QB","RB","WR","TE","K","DEF"}:
        return {s}
    if s in {"FLEX","WRRB","WRRBTE"}:
        return {"RB","WR","TE"}
    if s in {"SUPER_FLEX","QBRBWRTE"}:
        return {"QB","RB","WR","TE"}
    return set()

def _optimal_projected_total(roster: Dict[str, Any], players_points: Dict[str, float], roster_positions: List[str], catalog: Dict[str, Any]) -> float:
    # Build candidate list: (player_id, position, projected_points)
    candidates = []
    for pid in (roster.get('players') or []):
        p = catalog.get(pid) or {}
        pos = (p.get('position') or '').upper()
        pts = float(players_points.get(pid) or 0.0)
        candidates.append({"player_id": pid, "pos": pos, "pts": pts})
    used = set()
    total = 0.0
    for slot in roster_positions:
        if slot.upper() == 'BN':
            continue
        eligible = _eligible_positions(slot)
        best = None; best_pts = -1.0
        for c in candidates:
            if c['player_id'] in used:
                continue
            if c['pos'] in eligible and c['pts'] > best_pts:
                best_pts = c['pts']; best = c
        if best is not None:
            used.add(best['player_id'])
            total += best['pts']
    return round(total, 2)

@app.get("/api/league/projections")
async def league_projections(league_id: str | None = None, start_week: int | None = None, end_week: int | None = None):
    try:
        # League profile for roster_positions
        league = await sleeper_client.get_league(league_id)
        roster_positions = league.get('roster_positions') or []
        state = await sleeper_client.get_nfl_state()
        current_week = int(state.get("week") or 1)
        start_w = int(start_week or current_week)
        end_w = int(end_week or 17)
        rosters = await sleeper_client.build_roster_summaries(league_id=league_id)
        standings = {r['roster_id']: {"roster_id": r['roster_id'], "owner": r['owner'], "proj_wins": 0, "proj_losses": 0, "proj_ties": 0} for r in rosters}
        catalog = await sleeper_client.get_players()
        for w in range(start_w, end_w + 1):
            matchups = await sleeper_client.get_matchups(week=w, league_id=league_id)
            by_mid = {}
            roster_to_pp: Dict[int, Dict[str,float]] = {}
            for m in matchups:
                rid = m.get('roster_id')
                if rid is not None:
                    roster_to_pp[rid] = m.get('players_points') or {}
                mid = m.get('matchup_id')
                if mid is None: continue
                by_mid.setdefault(mid, []).append(m)
            for mid, games in by_mid.items():
                if len(games) != 2: continue
                a, b = games
                ra = a.get('roster_id'); rb = b.get('roster_id')
                ta = next((r for r in rosters if r['roster_id']==ra), None)
                tb = next((r for r in rosters if r['roster_id']==rb), None)
                if not ta or not tb: continue
                sa = _optimal_projected_total(ta, roster_to_pp.get(ra, {}), roster_positions, catalog)
                sb = _optimal_projected_total(tb, roster_to_pp.get(rb, {}), roster_positions, catalog)
                if sa > sb:
                    standings[ra]['proj_wins'] += 1; standings[rb]['proj_losses'] += 1
                elif sb > sa:
                    standings[rb]['proj_wins'] += 1; standings[ra]['proj_losses'] += 1
                else:
                    standings[ra]['proj_ties'] += 1; standings[rb]['proj_ties'] += 1
        table = list(standings.values())
        table.sort(key=lambda x: (x['proj_wins'], -x['proj_losses']), reverse=True)
        leader = table[0] if table else None
        return {"weeks": list(range(start_w, end_w+1)), "standings": table, "likely_winner": leader}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/public/config")
async def public_config():
    return {
        "supabase_url": os.getenv("SUPABASE_URL", ""),
        "supabase_anon": os.getenv("SUPABASE_ANON", ""),
    }