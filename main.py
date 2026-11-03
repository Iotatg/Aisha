# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""Aisha — a soft, girly group companion bot.

Entry point: builds the kurigram client, registers handlers and runs.
"""
import asyncio
import logging
import os

from core.app import build_client
from core import db
from core import health_server
from core import heartbeat


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app = build_client("aisha")
    try:
        health_server.start()
        logging.info("Health server started on port %s (/health)", os.environ.get("PORT", "8080"))
        # 300-second self-ping heartbeat — keeps Render + MongoDB alive
        asyncio.create_task(heartbeat.start_heartbeat())
        await app.start()
        me = await app.get_me()
        logging.info("Aisha is live as @%s 💗", me.username)
        # auto-delete broadcasts/Dms whose timer has elapsed
        from core import broadcast as _broadcast
        asyncio.create_task(_broadcast.start_autodelete_sweep(app))
        await asyncio.Event().wait()   # run forever
    finally:
        await app.stop()
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
