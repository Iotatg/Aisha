# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""Per-user chat memory for the AI chatbot (Mongo-backed, TTL-trimmed).

Each user gets ONE doc in `chat_history`:
    { _id: uid, msgs: [{r: "u"|"a", t: str, ts: float}], updated_at }
Kept to the last AI_MAX_TURNS entries; entries older than MEMORY_DAYS are
purged lazily on access. All helpers degrade safely (never raise).
"""
import logging
import time

import config
from core.db import db as get_db

logger = logging.getLogger(__name__)


def _col():
    return get_db().chat_history


async def remember(uid: int, role: str, text: str) -> None:
    """Append a turn and trim to the window. Best-effort."""
    try:
        now = time.time()
        await _col().find_one_and_update(
            {"_id": uid},
            {"$push": {"msgs": {"r": role, "t": text, "ts": now}}},
            upsert=True,
        )
        doc = await _col().find_one({"_id": uid})
        if not doc:
            return
        cutoff = now - config.MEMORY_DAYS * 86400
        msgs = [m for m in doc.get("msgs", []) if m.get("ts", 0) >= cutoff]
        msgs = msgs[-config.AI_MAX_TURNS:]
        await _col().find_one_and_update(
            {"_id": uid}, {"$set": {"msgs": msgs, "updated_at": now}},
            upsert=True,
        )
    except Exception as e:
        logger.debug("remember failed: %s", e)


async def recent_turns(uid: int) -> list[dict]:
    """Last turns as provider-style messages. Best-effort."""
    try:
        doc = await _col().find_one({"_id": uid})
        out = []
        for m in (doc or {}).get("msgs", [])[-config.AI_MAX_TURNS:]:
            role = "user" if m.get("r") == "u" else "assistant"
            out.append({"role": role, "content": m.get("t", "")})
        return out
    except Exception as e:
        logger.debug("recent_turns failed: %s", e)
        return []


async def clear(uid: int) -> bool:
    try:
        res = await _col().find_one_and_update(
            {"_id": uid}, {"$set": {"msgs": []}},
        )
        return res is not None
    except Exception:
        return False
