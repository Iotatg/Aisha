# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""Wallet operations — the only place that touches user balances.

Every mutation goes through these functions so tests only need to stub
one layer, and balance checks stay consistent across features.
"""
from core.db import db as get_db


def users():
    return get_db().users


async def ensure_user(uid: int, username: str = "", name: str = "") -> dict:
    """Fetch a user, creating a starter wallet on first sight."""
    doc = await users().find_one({"_id": uid})
    if doc:
        return doc
    import config
    doc = {
        "_id": uid,
        "name": name,
        "username": username,
        "balance": config.START_BALANCE,
        "gems": 0,
        "xp": 0,
        "kills": 0,
        "woods": 0,
        "stone": 0,
        "iron": 0,
        "daily_streak": 0,
        "last_daily": None,
        "created_at": __import__("datetime").datetime.utcnow(),
    }
    await users().insert_one(doc)
    return doc


async def get_user(uid: int) -> dict | None:
    return await users().find_one({"_id": uid})


async def add_balance(uid: int, amount: int) -> int:
    """Credit coins; returns the new balance."""
    res = await users().find_one_and_update(
        {"_id": uid}, {"$inc": {"balance": amount}},
        return_document=True,
    )
    return res["balance"]


async def add_gems(uid: int, amount: int) -> int:
    res = await users().find_one_and_update(
        {"_id": uid}, {"$inc": {"gems": amount}},
        return_document=True,
    )
    return res["gems"]


async def try_deduct(uid: int, amount: int) -> bool:
    """Debit coins only if the balance suffices (atomic guard)."""
    res = await users().find_one_and_update(
        {"_id": uid, "balance": {"$gte": amount}},
        {"$inc": {"balance": -amount}},
        return_document=True,
    )
    return res is not None


async def add_xp(uid: int, amount: int) -> tuple[int, int]:
    """Add XP; returns (new_xp, new_level)."""
    res = await users().find_one_and_update(
        {"_id": uid}, {"$inc": {"xp": amount}},
        return_document=True,
    )
    return res["xp"], level_for(res["xp"])


async def add_kill(uid: int) -> int:
    """Increment the user's kill counter; returns the new total.

    Backfills the field on legacy user docs that predate the kills
    counter (Mongo ``$inc`` treats missing as 0).
    """
    res = await users().find_one_and_update(
        {"_id": uid}, {"$inc": {"kills": 1}},
        return_document=True,
    )
    if res is None:
        await ensure_user(uid)
        res = await users().find_one_and_update(
            {"_id": uid}, {"$inc": {"kills": 1}},
            return_document=True,
        )
    return (res or {}).get("kills", 0)


async def add_resources(uid: int, *, woods: int = 0, stone: int = 0,
                        iron: int = 0) -> dict:
    """Credit resources atomically; returns the new resource dict.

    Uses ``$inc`` only, which is safe on legacy user docs that don't
    have the field yet (Mongo treats the missing value as 0).
    """
    inc = {}
    if woods:
        inc["woods"] = woods
    if stone:
        inc["stone"] = stone
    if iron:
        inc["iron"] = iron
    if not inc:
        # Nothing to do — return the current values.
        doc = await get_user(uid) or {}
        return {
            "woods": doc.get("woods", 0),
            "stone": doc.get("stone", 0),
            "iron": doc.get("iron", 0),
        }
    res = await users().find_one_and_update(
        {"_id": uid}, {"$inc": inc}, return_document=True,
    )
    if res is None:
        # User doesn't exist — create with the credited resources.
        doc = await ensure_user(uid)
        res = await users().find_one_and_update(
            {"_id": uid}, {"$inc": inc}, return_document=True,
        ) or doc
    return {
        "woods": (res or {}).get("woods", 0),
        "stone": (res or {}).get("stone", 0),
        "iron": (res or {}).get("iron", 0),
    }


def level_for(xp: int) -> int:
    """Level curve: every level costs 25% more XP than the last."""
    level = 0
    need = 100
    remaining = xp
    while remaining >= need:
        remaining -= need
        level += 1
        need = int(need * 1.25)
    return level


def xp_progress(xp: int) -> tuple[int, int]:
    """(xp_into_current_level, xp_needed_for_next)."""
    level = 0
    need = 100
    remaining = xp
    while remaining >= need:
        remaining -= need
        level += 1
        need = int(need * 1.25)
    return remaining, need
