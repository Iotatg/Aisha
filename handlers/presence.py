# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""Aisha presence tracker — keeps bot-safe broadcast target lists up to date.

Bots cannot enumerate their dialogs (get_dialogs -> BOT_METHOD_INVALID), so
broadcast reads from two Mongo collections that this module maintains:

  groups          : every group/supergroup the bot is a member of
  broadcast_users : every human user the bot has seen (DM-able)

Sources of truth:
  - chat_member updates : bot added to / removed from a chat
  - any inbound message : backfills a group the bot already belonged to before
                          this tracker existed, and records the sending user
"""
import logging

from core.db import db as get_db
from core.owner import maybe_bind

log = logging.getLogger(__name__)


def _chat_type(chat_type) -> str:
    return getattr(chat_type, "value", str(chat_type))


async def on_chat_member(client, update):
    """Fires on any membership change. We only care about the bot itself
    joining/leaving; we keep `groups` in sync accordingly."""
    try:
        bot_id = (await client.get_me()).id
    except Exception:
        return
    subject = update.new_chat_member or update.old_chat_member
    if not subject or subject.user.id != bot_id:
        return
    status = getattr((update.new_chat_member or update.old_chat_member).status,
                     "value", None)
    joined = status in ("member", "administrator", "creator")
    try:
        if joined:
            await get_db().groups.update_one(
                {"_id": update.chat.id},
                {"$set": {"title": getattr(update.chat, "title", None),
                          "type": _chat_type(update.chat.type)}},
                upsert=True,
            )
        else:
            await get_db().groups.delete_one({"_id": update.chat.id})
    except Exception:
        log.debug("presence on_chat_member write failed for %s", update.chat.id)


async def on_seen(client, message):
    """Catch-all (group -1, runs before command handlers): bind the owner by
    username the first time they speak, record the human sender so DM
    broadcasts can reach them, and record any group we hear a message in so
    group lists self-heal even for chats joined before tracking existed."""
    u = message.from_user
    if u and not u.is_bot:
        try:
            await maybe_bind(u.id, u.username)
        except Exception:
            pass
        try:
            await get_db().broadcast_users.update_one(
                {"_id": u.id},
                {"$set": {"username": u.username, "name": u.first_name}},
                upsert=True,
            )
        except Exception:
            pass
    chat = message.chat
    if chat and _chat_type(chat.type) in ("group", "supergroup"):
        try:
            await get_db().groups.update_one(
                {"_id": chat.id},
                {"$set": {"title": getattr(chat, "title", None),
                          "type": _chat_type(chat.type)}},
                upsert=True,
            )
        except Exception:
            pass


def register(add, filters, add_cb, add_raw=None, add_msg_edited=None,
             add_chat_member=None) -> int:
    n = 0
    if add_chat_member:
        add_chat_member(on_chat_member)
        n += 1
    # run before command handlers (lower group number) so the owner binds
    # the moment they speak, making owner-only commands work immediately.
    add(on_seen, filters.all, group=-1)
    n += 1
    return n
