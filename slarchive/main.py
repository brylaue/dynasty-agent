from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .db import get_db, init_db, search_messages
from .ingest import worker
from .config import SLACK_BOT_TOKEN
from slack_sdk.web.async_client import AsyncWebClient


app = FastAPI(title="slarchive")

templates_dir = Path(__file__).parent / "templates"
static_dir = Path(__file__).parent / "static"
templates_dir.mkdir(exist_ok=True)
static_dir.mkdir(exist_ok=True)

env = Environment(
    loader=FileSystemLoader(str(templates_dir)),
    autoescape=select_autoescape(["html", "xml"]),
)


@app.on_event("startup")
async def startup():
    await init_db()
    asyncio.create_task(worker.start())
    # Log which Slack workspace the token is tied to (if configured)
    async def _log_auth_test():
        if not SLACK_BOT_TOKEN:
            return
        try:
            client = AsyncWebClient(token=SLACK_BOT_TOKEN)
            resp = await client.auth_test()
            team = resp.get("team")
            url = resp.get("url")
            print(f"Slack auth: connected to team='{team}' url='{url}'")
        except Exception as e:
            print(f"Slack auth_test failed: {e}")
    asyncio.create_task(_log_auth_test())


@app.get("/healthz")
async def healthz():
    return {"ok": True}


@app.get("/api/search")
async def api_search(
    q: str = Query(""),
    channel_id: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    start_ts: Optional[str] = Query(None),
    end_ts: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    async with (await get_db()) as db:
        rows = await search_messages(db, q, channel_id, user_id, start_ts, end_ts, limit, offset)
    return JSONResponse(content={"results": rows})


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, q: str = ""):
    template = env.get_template("index.html")
    html = template.render(q=q)
    return HTMLResponse(html)


@app.get("/api/slack/workspace")
async def slack_workspace_info():
    if not SLACK_BOT_TOKEN:
        return JSONResponse(status_code=400, content={"error": "SLACK_BOT_TOKEN not set"})
    try:
        client = AsyncWebClient(token=SLACK_BOT_TOKEN)
        resp = await client.auth_test()
        return JSONResponse(
            content={
                "ok": True,
                "team_id": resp.get("team_id"),
                "team": resp.get("team"),
                "url": resp.get("url"),
                "user_id": resp.get("user_id"),
            }
        )
    except Exception as e:
        return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})

