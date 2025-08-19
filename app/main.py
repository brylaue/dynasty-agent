import os
import json
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.agents.graph import create_research_graph
from app.services.sleeper_client import SleeperClient
from app.services.memory import MemoryStore, UserPreferences

load_dotenv()

LEAGUE_ID = os.getenv("SLEEPER_LEAGUE_ID", "1180244317552857088")

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


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "league_id": LEAGUE_ID},
    )


@app.post("/api/ask")
async def ask_agent(body: QueryBody):
    prefs = memory_store.get_preferences(user_id=body.user_id or "default").model_dump(exclude_none=True)
    result = await research_graph.ainvoke({"question": body.question, "preferences": prefs})
    return {
        "answer": result.get("answer", "No answer produced."),
        "sources": result.get("sources", []),
        "intent": result.get("intent"),
        "data_keys": list((result.get("data") or {}).keys()),
    }


@app.get("/api/ask/stream")
async def ask_agent_stream(question: str, user_id: str = "default"):
    prefs = memory_store.get_preferences(user_id=user_id).model_dump(exclude_none=True)

    async def event_gen():
        yield f"data: {json.dumps({"status": "planning"})}\n\n"
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