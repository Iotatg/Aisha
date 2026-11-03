# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""Self-ping keep-alive — pings the deployed URL's /health endpoint so Render
never puts the web service to sleep.

Render web services sleep after a period of *HTTP* inactivity. Writing to
MongoDB (as the old heartbeat did) does NOT generate inbound traffic, so Render
still slept the service. The fix: hit our own public /health route on a
timer. The Mongo write is kept only as a
diagnostics aid ("is the bot alive") and has no effect on Render's scheduler.
"""
import asyncio
import logging
import os
import time

import aiohttp

from core.db import db

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 300  # 5 minutes
HEARTBEAT_COLLECTION = "heartbeat"


def _self_ping_url() -> str:
    """Resolve the public URL to ping, or '' if self-ping is disabled."""
    url = os.environ.get("RENDER_EXTERNAL_URL") or os.environ.get("WEBAPP_BASE_URL", "")
    if not url:
        return ""
    return url.rstrip("/") + "/health"


async def _ping_self() -> None:
    """HTTP self-ping so Render sees inbound traffic and stays awake."""
    url = _self_ping_url()
    if not url:
        logger.info("Keep-alive self-ping disabled (no public URL).")
        return
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                logger.debug("Keep-alive ping %s -> HTTP %s", url, r.status)
    except Exception as e:
        logger.debug("keep-alive ping failed: %s", e)


async def _heartbeat_doc() -> None:
    """Keep heartbeat doc fresh — proves bot is alive (diagnostics only)."""
    try:
        coll = db()[HEARTBEAT_COLLECTION]
        await coll.update_one(
            {"_id": "aisha"},
            {"$set": {"last_heartbeat": time.time(), "service": "aisha"}},
            upsert=True,
        )
    except Exception:
        pass  # DB blip shouldn't crash bot


async def start_heartbeat() -> None:
    """Launch background keep-alive loop: HTTP self-ping + Mongo heartbeat."""
    # Ping immediately so we don't leave a full-interval gap at boot.
    await _ping_self()
    await _heartbeat_doc()
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL)
        await _ping_self()
        await _heartbeat_doc()
