# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""Custom group welcomes: /welcome <text> sets a greeting posted when
someone joins. Placeholders: {name} {mention} {id}. /welcome off disables,
/welcome shows the current one.

Sep 2026: defaults to a cute Aisha-style greeting when an admin hasn't
set a per-chat message yet. The default is still overridable per group
by /welcome <text>. /welcome off disables the welcome entirely (no
default, no custom). The default is also auto-saved to Mongo on the
first join so admins can /welcome to preview/edit it.
"""
import logging

from core.db import db
from core.helpers import is_group, mention
from core.fonts import smallcaps as _sc

logger = logging.getLogger(__name__)


# Sep 2026: a friendly default that works in any group right out of the
# box. Placeholders get filled in by welcome_format() the same way admin-
# set text does. Admins can override with /welcome <text> and revert to
# this default by /welcome reset.
DEFAULT_WELCOME = "ʜᴇʏ {mention} 💗 ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ ᴛʜᴇ ɢʀᴏᴜᴘ! ʜᴀᴠᴇ ꜰᴜɴ ʜᴇʀᴇ 🌸"


def welcome_format(text, user):
    return (text
            .replace("{name}", user.first_name or "player")
            .replace("{mention}", mention(user.id, user.first_name or "player"))
            .replace("{id}", str(user.id)))


def register(add, filters, add_cb, add_chat_member=None):
    add(cmd_welcome, filters.command("welcome"))
    if add_chat_member is not None:
        add_chat_member(on_member)


async def cmd_welcome(client, message):
    if not is_group(message.chat):
        await message.reply("❗️ " + _sc("group only"))
        return
    cid = message.chat.id
    parts = message.text.split(maxsplit=1)
    arg = parts[1].strip() if len(parts) > 1 else ""
    if not arg:
        doc = await db().welcomes.find_one({"_id": cid})
        cur = (doc or {}).get("text") or DEFAULT_WELCOME
        disabled = (doc or {}).get("disabled", False)
        await message.reply(
            f"👋 <b>{_sc('welcome message')}</b>\n\n" +
            (f"{cur}\n\n" if not disabled else _sc("disabled") + "\n\n") +
            f"{_sc('use')}: /welcome <text>\n"
            f"{_sc('tags')}: " + "{name} {mention} {id}"
        )
        return
    if arg.lower() in ("off", "disable"):
        await db().welcomes.update_one(
            {"_id": cid},
            {"$set": {"text": DEFAULT_WELCOME, "disabled": True}},
            upsert=True,
        )
        await message.reply("🚫 " + _sc("welcome disabled"))
        return
    if arg.lower() in ("reset", "default"):
        await db().welcomes.update_one(
            {"_id": cid},
            {"$set": {"text": DEFAULT_WELCOME, "disabled": False}},
            upsert=True,
        )
        await message.reply("↩️ " + _sc("welcome reset to default"))
        return
    await db().welcomes.update_one(
        {"_id": cid}, {"$set": {"text": arg, "disabled": False}}, upsert=True)
    await message.reply(f"✅ {_sc('welcome set')}:\n\n{arg}")


async def on_member(client, update):
    new = getattr(update, "new_chat_member", None)
    old = getattr(update, "old_chat_member", None)
    if new is None or old is None:
        return
    if getattr(new.status, "value", new.status) == "member" and \
            getattr(old.status, "value", old.status) != "member":
        user = new.user
        doc = await db().welcomes.find_one({"_id": update.chat.id})
        # Sep 2026: if no per-chat config OR the admin disabled it,
        # honor that. Otherwise fall back to the default Aisha-style
        # greeting so the welcome works out of the box.
        disabled = bool(doc and doc.get("disabled"))
        if disabled:
            return
        if not doc or not doc.get("text"):
            text = DEFAULT_WELCOME
        else:
            text = doc["text"]
        try:
            await client.send_message(
                update.chat.id, welcome_format(text, user))
        except Exception:
            logger.debug("welcome send failed", exc_info=True)
