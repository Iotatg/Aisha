# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""Aisha broadcast / DM core — storage, target lists, auto-delete sweep.

Bots CANNOT list their dialogs (messages.GetDialogs returns BOT_METHOD_INVALID
for bots), so target lists are kept in our own Mongo collections and filled by
handlers/presence.py from chat_member + message updates:

  groups          -> every group/supergroup the bot is a member of
  broadcast_users -> every human user the bot has seen (DM-able)

Every /broadcast and /dm run is recorded in broadcast_history with the exact
targets it reached, so the owner can retract it (/delbroadcast, /deldm) and a
background sweep honours the optional auto-delete timer (-12h, -30m, -2d …).
"""
import asyncio
import logging
import time
import uuid

from pyrogram import errors as tg_errors

from core.db import db as get_db

log = logging.getLogger(__name__)


# ── records ──────────────────────────────────────────────────────────────────

async def new_bid() -> str:
    return str(uuid.uuid4())[:8]


async def create_broadcast_record(kind: str, preview: str, sender_id: int,
                                  delete_after: int = None) -> str:
    """Create a history record for a /broadcast or /dm run.

    `delete_after` is an epoch-seconds timestamp; when set, every delivered
    message is auto-deleted once that time passes (see start_autodelete_sweep).
    """
    bid = await new_bid()
    await get_db().broadcast_history.insert_one({
        "_id": bid,
        "kind": kind,
        "content_preview": (preview or "")[:200],
        "sender_id": sender_id,
        "created_at": int(time.time()),
        "delete_after": delete_after,
        "auto_deleted": False if delete_after else None,
        "targets": [],
        "sent": 0,
        "failed": 0,
    })
    return bid


async def add_target(bid: str, chat_id: int, message_id: int, kind: str = "group"):
    await get_db().broadcast_history.update_one(
        {"_id": bid},
        {"$push": {"targets": {"chat_id": chat_id,
                               "message_id": message_id,
                               "kind": kind}},
         "$inc": {"sent": 1}},
    )


async def record_failure(bid: str, n: int = 1):
    await get_db().broadcast_history.update_one(
        {"_id": bid}, {"$inc": {"failed": n}}
    )


async def get_record(bid: str):
    return await get_db().broadcast_history.find_one({"_id": bid})


async def list_history(kind: str, limit: int = 20):
    return await (get_db().broadcast_history.find({"kind": kind})
                 .sort("created_at", -1).limit(limit).to_list(limit))


async def get_due_autodelete(before: int):
    return await get_db().broadcast_history.find({
        "delete_after": {"$lte": before, "$ne": None},
        "auto_deleted": {"$ne": True},
    }).to_list(1000)


async def mark_auto_deleted(bid: str):
    await get_db().broadcast_history.update_one(
        {"_id": bid}, {"$set": {"auto_deleted": True}}
    )


async def delete_run_messages(client, bid: str):
    """Delete every delivered message of a run. Returns (deleted, failed)."""
    rec = await get_record(bid)
    if not rec:
        return 0, 0
    deleted = failed = 0
    for t in rec.get("targets", []):
        try:
            await client.delete_messages(t["chat_id"], t["message_id"])
            deleted += 1
        except Exception as e:
            log.debug("delete run msg failed %s/%s: %s",
                      t["chat_id"], t["message_id"], e)
            failed += 1
        await asyncio.sleep(0.05)
    return deleted, failed


# ── bot-safe target lists ─────────────────────────────────────────────────────

async def get_all_groups():
    docs = await get_db().groups.find({}).to_list(100000)
    return [d["_id"] for d in docs]


async def get_broadcastable_users():
    docs = await get_db().broadcast_users.find({}).to_list(100000)
    return [d["_id"] for d in docs]


async def forget_group(chat_id: int):
    """A group the bot can no longer post to — drop it from the target list."""
    await get_db().groups.delete_one({"_id": chat_id})


async def forget_user(user_id: int):
    """A user the bot can no longer DM — drop them from the target list."""
    await get_db().broadcast_users.delete_one({"_id": user_id})


# ── auto-delete sweep ──────────────────────────────────────────────────────────

async def start_autodelete_sweep(client):
    """Retract broadcasts/Dms whose auto-delete timer elapsed. Runs every 60s
    so timers survive restarts (unlike one-shot jobs)."""
    while True:
        try:
            await asyncio.sleep(60)
            before = int(time.time())
            due = await get_due_autodelete(before)
            for rec in due:
                deleted, _ = await delete_run_messages(client, rec["_id"])
                await mark_auto_deleted(rec["_id"])
                log.debug("auto-deleted %s (%d msgs)", rec.get("_id"), deleted)
        except Exception:
            log.exception("broadcast autodelete sweep error")


# ── delivery error classification ─────────────────────────────────────────────

def classify_delivery_error(exc) -> str:
    """Classify a per-target send failure.

    - "dead"  : the chat/user is permanently unreachable (bot kicked, banned,
                chat hidden, or invalid id) -> forget it so we never retry.
    - "flood" : Telegram rate limit -> caller should sleep and retry.
    - "fail"  : any other transient error -> count and move on.
    """
    if isinstance(exc, tg_errors.FloodWait):
        return "flood"
    if isinstance(exc, (
            tg_errors.ChatWriteForbidden,
            tg_errors.UserBannedInChannel,
            tg_errors.ChannelPrivate,
            tg_errors.PeerIdInvalid,
            tg_errors.ChatAdminRequired,
    )):
        return "dead"
    return "fail"
