# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""Social + sticker tools: /ship, /kang, /mykang.

/ship  : group-only love match between you and a partner (stable % per pair).
          The active /ship implementation lives in handlers/fun.py
          (Aisha card-style with banner image). This file keeps an
          alternative variant for reference.
          Reply to a user to ship with them; no reply = random soulmate.
/kang  : reply to a sticker to steal it into a real Telegram pack
          via the raw API, with a local MongoDB fallback; /mykang lists your pack.
The /st quote-sticker generator lives in handlers/quote.py.
"""
import logging
import random

import config
from pyrogram.file_id import FileId
from pyrogram.raw import functions
from pyrogram.raw.types import InputDocument, InputStickerSetItem, InputStickerSetShortName
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from core.db import db
from core.helpers import mention, is_group

logger = logging.getLogger(__name__)


ALPHA = "abcdefghijklmnopqrstuvwxyz"
SC = "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘQʀꜱᴛᴜᴠᴡxʏᴢ"
_SC_MAP = dict(zip(ALPHA, SC))


def _sc(text: str) -> str:
    return "".join(_SC_MAP.get(ch, ch) for ch in text.lower())


def _bar(pct: int) -> str:
    filled = pct // 10
    return "█" * filled + "░" * (10 - filled)


async def cmd_ship(client, message):
    """Ship variant (NOT registered, kept for reference).

    The Aisha card-style /ship with banner image lives in
    handlers/fun.py:cmd_ship. This function is intentionally not
    wired in register() to avoid double-firing /ship."""
    chat = message.chat
    if not is_group(chat):
        await message.reply("❗️ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ ᴏɴʟʏ ᴡᴏʀɪꜱ ɪɴ ɢʀᴏᴜᴘꜱ!")
        return
    u = message.from_user
    target = None
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user
    else:
        random.seed(f"{u.id}:{chat.id}")
        pct = random.randint(1, 100)
        name = _sc("ᴀ ʀᴀɴᴅᴏᴍ ꜱᴏᴜʟᴍᴀᴛᴇ")
        await message.reply(
            f"💞 <b>ꜱʜɪᴘ</b>\n\n{mention(u.id, u.first_name or 'ᴘʟᴀʏᴇʀ')} "
            f"💗 {name}\n\n{_bar(pct)} {pct}%"
        )
        return
    random.seed(f"{min(u.id, target.id)}:{max(u.id, target.id)}:{chat.id}")
    pct = random.randint(1, 100)
    await message.reply(
        f"💞 <b>ꜱʜɪᴘ</b>\n\n{mention(u.id, u.first_name or 'ᴘʟᴀʏᴇʀ')} "
        f"💗 {mention(target.id, target.first_name or 'ᴘʟᴀʏᴇʀ')}\n\n"
        f"{_bar(pct)} {pct}%\n{_sc(_flavour(pct))}"
    )


def _flavour(pct: int) -> str:
    if pct >= 90:
        return "soulmates fr"
    if pct >= 70:
        return "meant to be"
    if pct >= 50:
        return "worth a shot"
    if pct >= 30:
        return "friendship maybe"
    return "not meant to be"


async def _raise_to_telegram(client, u, st, short_name):
    """Best-effort: create/add the sticker to a real Telegram pack via raw API.

    Returns True on success. Requires a userbot-style session or a sticker bot
    with pack rights; on a plain bot without those rights Telegram rejects it
    and we fall back to the local MongoDB pack.
    """
    info = FileId.decode(st.file_id)
    doc = InputDocument(
        id=info.media_id,
        access_hash=info.access_hash,
        file_reference=info.file_reference or b"",
    )
    item = InputStickerSetItem(document=doc, emoji=st.emoji or "🙂")
    owner = await client.resolve_peer(u.id)
    if short_name:
        await client.invoke(functions.stickers.AddStickerToSet(
            stickerset=InputStickerSetShortName(short_name=short_name),
            sticker=item,
        ))
    else:
        await client.invoke(functions.stickers.CreateStickerSet(
            user_id=owner,
            title=f"{(u.first_name or 'Aɪsʜᴀ')} s Kᴀɴɢ Pᴀᴄɪ",
            short_name=f"aisha_{u.id}_by_{config.BOT_USERNAME}",
            stickers=[item],
        ))
    return True


async def cmd_kang(client, message):
    u = message.from_user
    rep = message.reply_to_message
    if not rep or not getattr(rep, "sticker", None):
        await message.reply("❗️ ʀᴇᴘʟʏ ᴛᴏ ᴀ ꜱᴛɪᴄɪᴇʀ ᴛᴏ ᴋᴀɴɢ ɪᴛ!")
        return
    st = rep.sticker

    rec = await db().kang_packs.find_one({"_id": u.id})
    prev_count = (rec or {}).get("count", 0)
    short_name = (rec or {}).get("short_name")

    real_ok = False
    try:
        ok = await _raise_to_telegram(client, u, st, short_name)
        real_ok = bool(ok)
    except Exception as e:
        logger.warning("real kang failed for %s: %s", u.id, e)
        real_ok = False

    final_short = short_name or f"aisha_{u.id}_by_{config.BOT_USERNAME}"
    await db().kang_packs.update_one(
        {"_id": u.id},
        {"$set": {"short_name": final_short},
         "$push": {"items": {"id": st.file_id, "emoji": st.emoji or "🙂"}},
         "$inc": {"count": 1}},
        upsert=True,
    )
    total = prev_count + 1

    pack_kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(_sc("📂 open sticker pack"),
                            url=f"https://t.me/addstickers/{final_short}")
    ]])
    progress = await message.reply(_sc("🪄 kanging sticker..."))

    if real_ok:
        await progress.edit_text(
            _sc("✅ sticker kanged successfully\n📥 added to: static pack\n"
                "⚡️ may take a few minutes to sync."),
            reply_markup=pack_kb,
        )
    else:
        await progress.edit_text(
            _sc(f"🎒 kanged locally! total: {total}\n"
                "⚠️ couldn't publish to telegram (needs userbot/sticker-bot perms)."),
            reply_markup=pack_kb,
        )


async def cmd_mykang(client, message):
    u = message.from_user
    rec = await db().kang_packs.find_one({"_id": u.id}) or {}
    total = rec.get("count", 0)
    short = rec.get("short_name")
    if not total:
        await message.reply(_sc("🎒 you have no kanged stickers yet!"))
        return
    link = f"https://t.me/addstickers/{short}" if short else ""
    body = _sc(f"🎒 your kang pack\n\n📦 total: {total}")
    await message.reply(f"{body}\n🔗 {link}" if link else body)


def register(add, filters, add_cb, **kwargs) -> int:
    # /ship and /couple are owned by handlers/fun.py (aisha card-style with
    # banner/couple images). This module also carries the /kang pack tooling,
    # so we register /kang here.
    n = 0
    add(cmd_kang, filters.command(["kang"]), group=0); n += 1
    add(cmd_mykang, filters.command(["mykang"]), group=0); n += 1
    return n
