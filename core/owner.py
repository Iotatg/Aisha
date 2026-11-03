# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""Owner binding & checks.

The bot may not know the owner's numeric id at boot (Telegram only
resolves users it has seen). So the username is configured statically
and the numeric id binds itself the first time that user ever speaks
in a chat with the bot; the binding persists in Mongo (`meta` doc).
"""
import logging

import config
from core.db import db as get_db

logger = logging.getLogger(__name__)

_owner_id: int | None = None
_db_checked: bool = False


async def _load() -> None:
    global _owner_id, _db_checked
    if _owner_id is not None:
        return
    if getattr(config, "OWNER_ID", 0):
        _owner_id = int(config.OWNER_ID)
        return
    if _db_checked:
        return
    try:
        doc = await get_db().meta.find_one({"_id": "owner"})
        if doc:
            _owner_id = doc.get("uid")
        else:
            _db_checked = True
    except Exception as e:
        _db_checked = True
        logger.debug("owner load failed: %s", e)


async def maybe_bind(uid: int, username: str | None) -> bool:
    """Bind ownership if this username matches; returns True if bound."""
    global _owner_id
    if _owner_id is not None:
        return False
    await _load()
    if _owner_id is not None:
        return False
    uname = (username or "").lower().lstrip("@")
    if uname and uname == (config.OWNER_USERNAME or "").lower().lstrip("@"):
        _owner_id = uid
        try:
            await get_db().meta.find_one_and_update(
                {"_id": "owner"},
                {"$set": {"uid": uid, "username": uname}},
                upsert=True,
            )
            logger.info("OWNER BOUND uid=%s (@%s)", uid, uname)
        except Exception as e:
            logger.debug("owner save failed: %s", e)
        return True
    return False


async def is_owner(uid: int) -> bool:
    await _load()
    return _owner_id is not None and uid == _owner_id


def owner_username() -> str:
    return (config.OWNER_USERNAME or "").lstrip("@")
