import os
import json
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Query, Response
from fastapi.middleware.cors import CORSMiddleware
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
from app.services.news_aggregator import fetch_rss_news, filter_news_by_names

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
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

provider_router = ProviderRouter(default_league_id=LEAGUE_ID)
sleeper_client = provider_router.sleeper
research_graph = create_research_graph(sleeper_client=sleeper_client)
memory_store = MemoryStore()


class QueryBody(BaseModel):
    question: str
    user_id: str | None = "default"
    league_id: str | None = None
    provider: str | None = LeagueProvider.SLEEPER


@app.get("/api/yahoo/auth")
async def yahoo_auth_start():
    yc = YahooClient()
    token = await yc.get_request_token()
    url = yc.get_authorize_url(token)
    return RedirectResponse(url)


@app.get("/api/yahoo/callback")
async def yahoo_auth_callback(oauth_verifier: str = Query(...)):
    yc = YahooClient()
    token = await yc.fetch_access_token(oauth_verifier)
    # TODO: persist token (session/db) and set provider_router.yahoo
    provider_router.yahoo = YahooClient(token=token)
    return RedirectResponse("/app")


@app.get("/api/health")
async def api_health():
    return {
        "ok": True,
        "league_id": LEAGUE_ID,
        "openai_configured": bool(OPENAI_API_KEY),
        "model": OPENAI_MODEL,
        "providers": [LeagueProvider.SLEEPER, LeagueProvider.YAHOO],
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
        prefs = memory_store.get_preferences(user_id=user_id)
        if not prefs.roster_owner_name:
            return JSONResponse(status_code=400, content={"error": "Select your team first (My Team) to enable the news feed."})
        client = provider_router.get_client(provider or LeagueProvider.SLEEPER)
        # Get rosters and find the user's team players
        rosters = await client.build_roster_summaries(league_id=league_id)
        my_roster = next((r for r in rosters if (r.get('owner') or '').lower() == prefs.roster_owner_name.lower()), None)
        team_players = set((my_roster or {}).get('players', []) or [])
        # Pull trending adds/drops (proxy for FA chatter) and RSS, then filter by player names
        trending = await client.get_trending_news(lookback_hours=lookback_hours, limit=limit) if hasattr(client, 'get_trending_news') else {"adds": [], "drops": []}
        rss_items = await fetch_rss_news()
        # Build name list from catalog
        catalog = await client.get_players() if hasattr(client, 'get_players') else {}
        names = []
        for pid in team_players:
            p = catalog.get(pid)
            if p:
                names.append(p.get('full_name') or ((p.get('first_name') or '') + ' ' + (p.get('last_name') or '')).strip())
        # Also include top trending free agent names
        for t in (trending.get('adds') or [])[:10]:
            pid = t.get('player_id')
            p = catalog.get(pid) if pid else None
            if p:
                names.append(p.get('full_name') or '')
        filtered_rss = filter_news_by_names(rss_items, names)
        return {"rss": filtered_rss[: limit], "trending": trending}
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


@app.post("/api/ask")
async def ask_agent(body: QueryBody):
    try:
        if not OPENAI_API_KEY:
            return JSONResponse(status_code=400, content={"error": "OPENAI_API_KEY is not configured on the server."})
        prefs = memory_store.get_preferences(user_id=body.user_id or "default").model_dump(exclude_none=True)
        if body.league_id and body.provider == LeagueProvider.SLEEPER:
            temp_client = SleeperClient(default_league_id=body.league_id)
            temp_graph = create_research_graph(sleeper_client=temp_client)
            result = await temp_graph.ainvoke({"question": body.question, "preferences": prefs})
        else:
            result = await research_graph.ainvoke({"question": body.question, "preferences": prefs})
        return {
            "answer": result.get("answer", "No answer produced."),
            "sources": result.get("sources", []),
            "intent": result.get("intent"),
            "data_keys": list((result.get("data") or {}).keys()),
        }
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
            sources = result.get("sources", [])
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


@app.get("/api/prefs")
async def get_prefs(user_id: str = "default"):
    return memory_store.get_preferences(user_id=user_id).model_dump(exclude_none=True)


class PrefsBody(BaseModel):
    favorite_team: str | None = None
    roster_owner_name: str | None = None
    risk_tolerance: str | None = None
    user_id: str | None = "default"


@app.post("/api/prefs")
async def set_prefs(body: PrefsBody):
    prefs = UserPreferences(
        favorite_team=body.favorite_team,
        roster_owner_name=body.roster_owner_name,
        risk_tolerance=body.risk_tolerance,
    )
    memory_store.set_preferences(prefs, user_id=body.user_id or "default")
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