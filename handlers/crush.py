# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""Secret admirer matcher: /crush (reply to someone, or @their handle).

Stores a one-way crush per chat; if the target has also crushed on you,
both get a private DM revealing the mutual match."""
import logging

from core.db import db
from core.fonts import smallcaps as _sc

logger = logging.getLogger(__name__)


def register(add, filters, add_cb):
    add(cmd_crush, filters.command("crush"))


async def cmd_crush(client, message):
    chat_id = message.chat.id
    uid = message.from_user.id
    uname = message.from_user.first_name or "player"

    target = None
    tname = None
    if message.reply_to_message and message.reply_to_message.from_user:
        t = message.reply_to_message.from_user
        if t.id == uid:
            await message.reply("😅 " + _sc("you can't crush on yourself"))
            return
        target, tname = t.id, t.first_name or "player"
    else:
        parts = message.text.split(maxsplit=1)
        handle = parts[1].strip().lstrip("@") if len(parts) > 1 else ""
        if not handle:
            await message.reply(f"💌 <b>{_sc('crush')}</b>\n\n"
                                 f"{_sc('reply to someone or use')} /crush @handle")
            return
        target, tname = handle.lower(), handle

    col = db().crushes
    key = f"{chat_id}:{uid}"
    await col.update_one(
        {"_id": key},
        {"$set": {"to": target, "name": tname}}, upsert=True,
    )

    opp = await col.find_one({"_id": f"{chat_id}:{target}"})
    if opp and str(opp.get("to")) == str(uid):
        msg = (f"💞 <b>{_sc('it is mutual')}!</b>\n\n"
               f"{_sc('you and')} {tname} {_sc('like each other')} "
               f"({_sc('in this chat')}).")
        try:
            await client.send_message(uid, msg)
            if isinstance(target, int):
                await client.send_message(target, msg)
        except Exception:
            pass
        await message.reply("💞 " + _sc("match found — check your dms!"))
        return

    await message.reply(f"💌 {_sc('your secret is safe')} 🤫")
