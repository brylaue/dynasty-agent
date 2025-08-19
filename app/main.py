import os
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
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
        "intent": result.get("intent"),
        "data_keys": list((result.get("data") or {}).keys()),
    }


@app.get("/api/ask/stream")
async def ask_agent_stream(question: str):
    async def event_gen():
        # Coarse-grained streaming: chunk in 4 phases
        yield f"data: planning...\n\n"
        result = await research_graph.ainvoke({"question": question})
        answer = result.get("answer", "")
        sources = result.get("sources", [])
        # Stream the answer in chunks
        chunk_size = 200
        for i in range(0, len(answer), chunk_size):
            yield f"data: {answer[i:i+chunk_size]}\n\n"
        # Final sources
        yield f"data: \n\n"
        yield f"event: sources\n"
        yield f"data: {sources}\n\n"
        yield "event: end\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")