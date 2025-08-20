from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Dict, Optional

from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.aiohttp import AsyncSocketModeHandler
from slack_sdk.web.async_client import AsyncWebClient

from .config import SLACK_APP_TOKEN, SLACK_BOT_TOKEN
from .db import get_db, init_db, insert_message, insert_file, upsert_channel


class SlackIngestWorker:
    def __init__(self) -> None:
        self.app = AsyncApp(token=SLACK_BOT_TOKEN)
        self.client: AsyncWebClient = self.app.client
        self._handler: Optional[AsyncSocketModeHandler] = None
        self._started = False

        # Register listeners
        self.app.event("message")(self._on_message)
        self.app.event("file_shared")(self._on_file_event)
        self.app.event("file_change")(self._on_file_event)

    async def _on_message(self, body: Dict[str, Any], say, logger) -> None:  # type: ignore[no-untyped-def]
        event = body.get("event", {})
        channel_id = event.get("channel")
        subtype = event.get("subtype")
        if subtype in {"message_changed", "message_deleted", "channel_join"}:
            return
        if not channel_id or "ts" not in event:
            return

        async with (await get_db()) as db:
            await insert_message(db, event, channel_id)
            await db.commit()

    async def _on_file_event(self, body: Dict[str, Any], say=None, logger=None) -> None:  # type: ignore[no-untyped-def]
        event = body.get("event", {})
        file_obj = event.get("file")
        channel_id = event.get("channel_id") or (event.get("channel") or {}).get("id")
        if not file_obj:
            return
        async with (await get_db()) as db:
            await insert_file(db, file_obj, channel_id)
            await db.commit()

    async def start(self) -> None:
        if self._started:
            return
        # If tokens are not configured, skip starting Socket Mode to allow the web app to run.
        if not SLACK_APP_TOKEN or not SLACK_BOT_TOKEN:
            print("Slack tokens not set; skipping Socket Mode worker. Set SLACK_APP_TOKEN and SLACK_BOT_TOKEN in .env")
            return
        await init_db()
        self._handler = AsyncSocketModeHandler(self.app, SLACK_APP_TOKEN)
        await self._handler.start_async()
        self._started = True

    async def stop(self) -> None:
        if self._handler:
            await self._handler.close()
        self._started = False


worker = SlackIngestWorker()

