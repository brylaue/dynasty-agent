from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

import typer
from slack_sdk.web.async_client import AsyncWebClient

from .config import SLACK_BOT_TOKEN
from .db import get_db, init_db, insert_message, upsert_channel


cli = typer.Typer()


async def _paginate(client: AsyncWebClient, method: str, key: str, params: Dict[str, Any]):
    cursor: Optional[str] = None
    while True:
        resp = await client.api_call(method, params={**params, **({"cursor": cursor} if cursor else {})})
        resp.validate()
        for item in resp.get(key, []):
            yield item
        cursor = (resp.get("response_metadata") or {}).get("next_cursor") or None
        if not cursor:
            break


async def _backfill_channel(client: AsyncWebClient, channel: Dict[str, Any], oldest: float) -> None:
    channel_id = channel["id"]
    async with (await get_db()) as db:
        await upsert_channel(db, channel)
        await db.commit()

    async for msg in _paginate(
        client,
        "conversations.history",
        key="messages",
        params={"channel": channel_id, "limit": 1000, "oldest": oldest},
    ):
        async with (await get_db()) as db:
            await insert_message(db, msg, channel_id)
            await db.commit()


@cli.command()
def main(
    types: str = typer.Option("public,private,im,mpim", help="Conversation types to backfill"),
    days: int = typer.Option(90, help="How many past days to fetch"),
):
    async def run():
        await init_db()
        client = AsyncWebClient(token=SLACK_BOT_TOKEN)
        oldest_dt = datetime.now(timezone.utc) - timedelta(days=days)
        oldest = oldest_dt.timestamp()

        conv_types = types
        # list conversations
        async for channel in _paginate(
            client,
            "conversations.list",
            key="channels",
            params={"exclude_archived": True, "types": conv_types, "limit": 1000},
        ):
            # attempt to join public channels to ensure access
            try:
                if not channel.get("is_member") and not channel.get("is_private"):
                    await client.conversations_join(channel=channel["id"])  # type: ignore[arg-type]
            except Exception:
                pass
            await _backfill_channel(client, channel, oldest)

    asyncio.run(run())


if __name__ == "__main__":
    main()

