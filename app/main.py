import os
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.agents.graph import create_research_graph
from app.services.sleeper_client import SleeperClient

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


class QueryBody(BaseModel):
    question: str


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "league_id": LEAGUE_ID},
    )


@app.post("/api/ask")
async def ask_agent(body: QueryBody):
    result = await research_graph.ainvoke({"question": body.question})
    return {
        "answer": result.get("answer", "No answer produced."),
        "sources": result.get("sources", []),
    }