import os
import json
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.agents.graph import create_research_graph
from app.services.sleeper_client import SleeperClient
from app.services.memory import MemoryStore, UserPreferences

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

sleeper_client = SleeperClient(default_league_id=LEAGUE_ID)
research_graph = create_research_graph(sleeper_client=sleeper_client)
memory_store = MemoryStore()


class QueryBody(BaseModel):
    question: str
    user_id: str | None = "default"
    league_id: str | None = None


@app.get("/healthz")
async def healthz():
    return {"ok": True}


@app.get("/api/health")
async def api_health():
    return {
        "ok": True,
        "league_id": LEAGUE_ID,
        "openai_configured": bool(OPENAI_API_KEY),
        "model": OPENAI_MODEL,
    }


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "league_id": LEAGUE_ID},
    )


@app.get("/start", response_class=HTMLResponse)
async def start(request: Request):
    return templates.TemplateResponse("landing.html", {"request": request})


@app.get("/api/rosters")
async def api_rosters(league_id: str | None = None):
    try:
        if league_id:
            temp_client = SleeperClient(default_league_id=league_id)
            return await temp_client.build_roster_summaries()
        summaries = await sleeper_client.build_roster_summaries()
        return summaries
    except Exception as e:  # pragma: no cover
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/rosters/{roster_id}")
async def api_roster_detail(roster_id: int, league_id: str | None = None):
    try:
        if league_id:
            temp_client = SleeperClient(default_league_id=league_id)
            return await temp_client.build_roster_detail(roster_id, league_id=league_id)
        detail = await sleeper_client.build_roster_detail(roster_id)
        return detail
    except Exception as e:  # pragma: no cover
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/projections")
async def api_projections(week: int | None = None, league_id: str | None = None):
    try:
        if week is None:
            state = await sleeper_client.get_nfl_state()
            week = int(state.get("week") or 1)
        client = sleeper_client if not league_id else SleeperClient(default_league_id=league_id)
        proj = await client.build_weekly_projections(week=week, league_id=league_id)
        return {"week": week, "projections": proj}
    except Exception as e:  # pragma: no cover
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/news")
async def api_news(lookback_hours: int = 48, limit: int = 25):
    try:
        news = await sleeper_client.get_trending_news(lookback_hours=lookback_hours, limit=limit)
        return news
    except Exception as e:  # pragma: no cover
        return JSONResponse(status_code=500, content={"error": str(e)})


class SetTeamBody(BaseModel):
    owner_name: str
    user_id: str | None = "default"


@app.post("/api/my-team")
async def set_my_team(body: SetTeamBody):
    prefs = memory_store.get_preferences(user_id=body.user_id or "default")
    prefs.roster_owner_name = body.owner_name
    memory_store.set_preferences(prefs, user_id=body.user_id or "default")
    return {"ok": True}


@app.post("/api/ask")
async def ask_agent(body: QueryBody):
    try:
        if not OPENAI_API_KEY:
            return JSONResponse(status_code=400, content={"error": "OPENAI_API_KEY is not configured on the server."})
        prefs = memory_store.get_preferences(user_id=body.user_id or "default").model_dump(exclude_none=True)
        if body.league_id:
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