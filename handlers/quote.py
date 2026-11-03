# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""Quote-sticker generator for /st (QuotLyBot-style).

Public (everyone):
  /st              -> default colour quote
  /st <color>      -> a named colour (red/blue/green/yellow/orange/purple/pink/black)
  /st r            -> random colour
  /st r <color>    -> random colour (alias)
  /st reply        -> include the quoted message's reply context
  /st 3            -> quote the next N messages
  /st s3           -> scale factor

Owner-only settings (configure the quote renderer):
  /qcolor <hex|random|transparent>   -> set background colour
  /qb <apple|google|twitter>        -> set emoji brand
  /qemoji <on|off>                  -> toggle emoji suffix on stickers
  /hidden <on|off>                  -> toggle hidden quotes (forward attribution)
  /privacy <on|off>                 -> toggle privacy mode
  /qrate <on|off>                   -> toggle rate buttons
  /qgab <1-100>                     -> set random-quote gab frequency
  /qarchive <on|off>                -> toggle text archiving
  /qforget                          -> clear all quote data for this chat
  /qd <local_id>                    -> delete a specific quote by local id
  /qdrand                           -> delete a random quote
  /qs                               -> save the replied quote sticker to your DMs
  /qapp                             -> show quote app info

Text replies are rendered into a .webp quote sticker via the quote API and
sent back. Photo replies are echoed with a colour-tagged caption (the API
has no media pipeline), keeping "/st photo" working.
"""
import asyncio
import re
import random
from io import BytesIO

import aiohttp
from pyrogram.enums import ChatAction

from core import helpers
from core import owner as owner_mod
from core.db import db as get_db

QUOTE_API = "https://quote-api-p0px.onrender.com/generate.webp"

ALPHA = "abcdefghijklmnopqrstuvwxyz"
SC = "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘQʀꜱᴛᴜᴠᴡxʏᴢ"
_SC_MAP = dict(zip(ALPHA, SC))

COLOR_HEX = {
    "red": "#e74c3c", "blue": "#3498db", "green": "#2ecc71", "yellow": "#f1c40f",
    "orange": "#e67e22", "purple": "#9b59b6", "pink": "#e84393", "black": "#111111",
}
COLOR_EMOJI = {
    "red": "🔴", "blue": "🔵", "green": "🟢", "yellow": "🟡",
    "orange": "🟠", "purple": "🟣", "pink": "🩷", "black": "⚫",
}
DEFAULT_COLOR = "#292232"

_HEADERS = {
    "Accept-Language": "id-ID",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/107.0.0.0 Safari/537.36 Edge/107.0.1418.42",
}


def _sc(text: str) -> str:
    return "".join(_SC_MAP.get(ch, ch) for ch in text.lower())


def _parse_args(args):
    flag = {"reply": False, "color": None, "scale": 2, "count": 1}
    for a in args:
        if a == "reply":
            flag["reply"] = True
        elif a == "r":
            flag["color"] = "#%06x" % random.randint(0, 0xFFFFFF)
        elif a in COLOR_HEX:
            flag["color"] = COLOR_HEX[a]
        elif re.match(r"^#?[0-9a-fA-F]{6}$", a):
            flag["color"] = a if a.startswith("#") else "#" + a
        elif re.match(r"^s[+-]?\d*\.?\d+$", a):
            flag["scale"] = float(a[1:])
        elif a.isdigit():
            flag["count"] = max(1, min(int(a), 50))
    return flag


async def _sender(m):
    u = getattr(m, "from_user", None)
    if u:
        name = (f"{u.first_name or ''} {u.last_name or ''}".strip()
                or getattr(u, "username", None) or "Someone")
        return {"id": u.id, "name": name, "username": getattr(u, "username", None) or "",
                "type": "private"}
    sc = getattr(m, "sender_chat", None)
    if sc:
        return {"id": sc.id, "name": getattr(sc, "title", None) or "Channel",
                "username": getattr(sc, "username", None) or "", "type": "channel"}
    return {"id": 1, "name": "Someone", "username": "", "type": "private"}


def _entities(m):
    ents = getattr(m, "entities", None) or getattr(m, "caption_entities", None) or []
    out = []
    for e in ents:
        t = getattr(e, "type", None)
        if isinstance(t, type):
            name = t.__name__
        elif hasattr(t, "name") and isinstance(getattr(t, "name"), str):
            name = t.name
        elif hasattr(t, "value"):
            v = t.value
            name = v if isinstance(v, str) else getattr(v, "__name__", str(v))
        else:
            name = str(t)
        if isinstance(name, str) and name.startswith("MessageEntity"):
            name = name[len("MessageEntity"):]
        if isinstance(name, str) and name != name.lower():
            name = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
        out.append({"type": name.lower() if isinstance(name, str) else str(name),
                    "offset": e.offset, "length": e.length})
    return out


def _text(m):
    return getattr(m, "text", None) or getattr(m, "caption", None) or ""


async def _build_payload(messages, include_reply, color, scale):
    payload = {
        "type": "quote", "format": "webp", "backgroundColor": color,
        "width": 512, "height": 768, "scale": scale,
        "emojiBrand": "apple", "messages": [],
    }
    for m in messages:
        s = await _sender(m)
        chat_type = "private"
        chat = getattr(m, "chat", None)
        if chat and getattr(chat, "type", None) is not None:
            chat_type = str(chat.type).lower()
        entry = {
            "entities": _entities(m), "chatId": s["id"], "text": _text(m),
            "avatar": True,
            "from": {"id": s["id"], "name": s["name"],
                     "username": s["username"], "type": chat_type},
        }
        reply = getattr(m, "reply_to_message", None)
        if include_reply and reply is not None:
            rs = await _sender(reply)
            entry["replyMessage"] = {"name": rs["name"], "text": _text(reply),
                                     "chatId": rs["id"]}
        else:
            entry["replyMessage"] = {}
        payload["messages"].append(entry)
    return payload


async def _render(payload) -> bytes:
    # Render's free worker sleeps between uses and answers 404/5xx while it
    # wakes up; retry a couple of times before surfacing the error.
    async with aiohttp.ClientSession(headers=_HEADERS) as s:
        for attempt in range(3):
            if attempt:
                await asyncio.sleep(2 * (attempt + 1))
            async with s.post(QUOTE_API, json=payload,
                              timeout=aiohttp.ClientTimeout(total=40)) as r:
                if r.status == 200:
                    return await r.read()
                if r.status in (404, 502, 503) and attempt < 2:
                    continue
                raise RuntimeError(f"quote-api HTTP {r.status}")


async def _is_owner(uid: int) -> bool:
    await owner_mod._load()
    return uid == getattr(owner_mod, "_owner_id", None) or False


def _parse_onoff(args):
    a = (args[0].lower() if args else "on")
    return a in ("on", "1", "true", "yes")


async def _settings(cid):
    doc = await get_db().quote_groups.find_one({"_id": cid}) or {}
    return doc.get("settings") or {}


async def _next_quote_id(cid):
    doc = await get_db().quote_groups.find_one({"_id": cid}) or {}
    return doc.get("next_quote_id", 1)


async def qcolor_cmd(client, message):
    if not await owner_mod.is_owner(message.from_user.id):
        return await message.reply_text(helpers.OWNER_ONLY)
    args = getattr(message, "command", []) or []
    if not args:
        return await message.reply_text("/qcolor &lt;#hex|random|transparent&gt;")
    value = args[0]
    if value == "random":
        value = "#%06x" % random.randint(0, 0xFFFFFF)
    settings = await get_db().quote_groups.update_one(
        {"_id": message.chat.id},
        {"$set": {"settings.backgroundColor": value}},
        upsert=True
    )
    await message.reply_text(f"✅ ᴄᴏʟᴏʀ <code>{value}</code>")


async def qb_cmd(client, message):
    if not await owner_mod.is_owner(message.from_user.id):
        return await message.reply_text(helpers.OWNER_ONLY)
    args = getattr(message, "command", []) or []
    if not args:
        return await message.reply_text("/qb &lt;apple|google|twitter&gt;")
    settings = await get_db().quote_groups.update_one(
        {"_id": message.chat.id},
        {"$set": {"settings.emojiBrand": args[0].lower()}},
        upsert=True
    )
    await message.reply_text(f"✅ ʙʀᴀɴᴅ <code>{args[0].lower()}</code>")


async def qemoji_cmd(client, message):
    if not await owner_mod.is_owner(message.from_user.id):
        return await message.reply_text(helpers.OWNER_ONLY)
    on = _parse_onoff(getattr(message, "command", []) or [])
    settings = await get_db().quote_groups.update_one(
        {"_id": message.chat.id},
        {"$set": {"settings.emojiSuffix": "random" if on else ""}},
        upsert=True
    )
    await message.reply_text(f"✅ ᴇᴍᴏᴊɪ {'ᴏɴ' if on else 'ᴏꜰꜰ'}")


async def hidden_cmd(client, message):
    if not await owner_mod.is_owner(message.from_user.id):
        return await message.reply_text(helpers.OWNER_ONLY)
    on = _parse_onoff(getattr(message, "command", []) or [])
    settings = await get_db().quote_groups.update_one(
        {"_id": message.chat.id},
        {"$set": {"settings.hidden": on}},
        upsert=True
    )
    await message.reply_text(f"✅ ʜɪᴅᴅᴇɴ {'ᴏɴ' if on else 'ᴏꜰꜰ'}")


async def privacy_cmd(client, message):
    if not await owner_mod.is_owner(message.from_user.id):
        return await message.reply_text(helpers.OWNER_ONLY)
    on = _parse_onoff(getattr(message, "command", []) or [])
    settings = await get_db().quote_groups.update_one(
        {"_id": message.chat.id},
        {"$set": {"settings.privacy": on}},
        upsert=True
    )
    await message.reply_text(f"✅ ᴘʀɪᴠᴀᴄʏ {'ᴏɴ' if on else 'ᴏꜰꜰ'}")


async def qrate_cmd(client, message):
    if not await owner_mod.is_owner(message.from_user.id):
        return await message.reply_text(helpers.OWNER_ONLY)
    on = _parse_onoff(getattr(message, "command", []) or [])
    settings = await get_db().quote_groups.update_one(
        {"_id": message.chat.id},
        {"$set": {"settings.rate": on}},
        upsert=True
    )
    await message.reply_text(f"✅ ʀᴀᴛɪɴɢ {'ᴏɴ' if on else 'ᴏꜰꜰ'}")


async def qgab_cmd(client, message):
    if not await owner_mod.is_owner(message.from_user.id):
        return await message.reply_text(helpers.OWNER_ONLY)
    args = getattr(message, "command", []) or []
    if not args or not args[0].isdigit():
        return await message.reply_text("/qgab &lt;1-100&gt;")
    gab_value = max(1, min(int(args[0]), 100))
    settings = await get_db().quote_groups.update_one(
        {"_id": message.chat.id},
        {"$set": {"settings.gab": gab_value}},
        upsert=True
    )
    await message.reply_text(f"✅ ɢᴀʙ 1/{gab_value}")


async def qarchive_cmd(client, message):
    if not await owner_mod.is_owner(message.from_user.id):
        return await message.reply_text(helpers.OWNER_ONLY)
    on = _parse_onoff(getattr(message, "command", []) or [])
    settings = await get_db().quote_groups.update_one(
        {"_id": message.chat.id},
        {"$set": {"settings.archive": on}},
        upsert=True
    )
    await message.reply_text(f"✅ ᴀʀᴄʜɪᴠᴇ {'ᴏɴ' if on else 'ᴏꜰꜰ'}")


async def qforget_cmd(client, message):
    if not await owner_mod.is_owner(message.from_user.id):
        return await message.reply_text(helpers.OWNER_ONLY)
    cid = message.chat.id
    await get_db().quote_quotes.delete_many({"group_id": cid})
    await get_db().quote_groups.delete_one({"_id": cid})
    await message.reply_text("🧹 ǫᴜᴏᴛᴇ ᴅᴀᴛᴀ ᴄʟᴇᴀʀᴇᴅ.")


async def qd_cmd(client, message):
    if not await owner_mod.is_owner(message.from_user.id):
        return await message.reply_text(helpers.OWNER_ONLY)
    args = getattr(message, "command", []) or []
    if not args or not args[0].isdigit():
        return await message.reply_text("/qd &lt;local_id&gt;")
    cid = message.chat.id
    doc = await get_db().quote_quotes.find_one({"group_id": cid, "local_id": int(args[0])})
    if not doc:
        return await message.reply_text("❌ ɴᴏᴛ ꜰᴏᴜɴᴅ.")
    await get_db().quote_quotes.delete_one({"_id": doc["_id"]})
    await message.reply_text("🗑️ ǫᴜᴏᴛᴇ ᴅᴇʟᴇᴛᴇᴅ.")


async def qdrand_cmd(client, message):
    if not await owner_mod.is_owner(message.from_user.id):
        return await message.reply_text(helpers.OWNER_ONLY)
    cid = message.chat.id
    docs = await get_db().quote_quotes.find({"group_id": cid}).to_list(200)
    if not docs:
        return await message.reply_text("❌ ɴᴏ ǫᴜᴏᴛᴇs.")
    await get_db().quote_quotes.delete_one({"_id": random.choice(docs)["_id"]})
    await message.reply_text("🗑️ ʀᴀɴᴅᴏᴍ ǫᴜᴏᴛᴇ ᴅᴇʟᴇᴛᴇᴅ.")


async def qs_cmd(client, message):
    if not await owner_mod.is_owner(message.from_user.id):
        return await message.reply_text(helpers.OWNER_ONLY)
    if not message.reply_to_message:
        return await message.reply_text("ʀᴇᴘʟʏ ᴛᴏ sᴀᴠᴇ ᴀ ǫᴜᴏᴛᴇ sᴛɪᴄᴋᴇʀ.")
    uid = message.from_user.id
    pack = await get_db().quote_users.find_one({"_id": uid}) or {}
    name = (pack.get("pack") or {}).get("name") or f"q_{uid}_by_{message.from_user.username or 'me'}"
    img = await _render(_build_payload([message.reply_to_message], False, "//#292232", 2))
    buf = BytesIO(img)
    buf.name = "quote.webp"
    await client.send_sticker(uid, buf)
    await get_db().quote_users.update_one(
        {"_id": uid},
        {"$set": {"pack.name": name}},
        upsert=True
    )
    await message.reply_text("✅ ǫᴜᴏᴛᴇ sᴇɴᴛ ᴛᴏ ʏᴏᴜʀ ᴅᴍ.")


async def qapp_cmd(client, message):
    if not await owner_mod.is_owner(message.from_user.id):
        return await message.reply_text(helpers.OWNER_ONLY)
    me = await client.get_me()
    await message.reply_text(
        f"📱 <b>QuotLyBot</b>\n"
        f"ʙᴏᴛ: @{me.username}\n"
        f"ᴜʀʟ: https://t.me/{me.username}/app\n"
        f"ᴏᴡɴᴇʀ: <code>{message.from_user.id}</code>"
    )


def _photo_caption(rep, color_name):
    text = _text(rep)
    tag = COLOR_EMOJI.get(color_name, "")
    if tag and text:
        return f"{tag} {_sc(text)}"
    return tag or _sc(text)


def _color_name(hex_or_none):
    if not hex_or_none:
        return None
    for name, h in COLOR_HEX.items():
        if h.lower() == hex_or_none.lower():
            return name
    return None


async def cmd_st(client, message):
    args = getattr(message, "command", []) or []
    flag = _parse_args(args)
    rep = message.reply_to_message
    if not rep:
        return await message.reply(
            _sc("❗️ reply to a photo/text to make a sticker!\n"
                "usage: /st | /st color | /st r"))

    photo = getattr(rep, "photo", None)
    if photo is not None:
        await client.send_chat_action(message.chat.id, ChatAction.CHOOSE_STICKER)
        await client.send_photo(
            message.chat.id, photo.file_id,
            caption=_photo_caption(rep, _color_name(flag["color"])),
            reply_to_message_id=getattr(message, "id", None),
        )
        return

    color = flag["color"] or DEFAULT_COLOR
    await client.send_chat_action(message.chat.id, ChatAction.CHOOSE_STICKER)
    try:
        payload = await _build_payload([rep], flag["reply"], color, flag["scale"])
        img = await _render(payload)
    except Exception as e:
        return await message.reply(f"❌ {_sc('quote generate fail')}: {e}")

    buf = BytesIO(img)
    buf.name = "quote.webp"
    try:
        await client.send_sticker(message.chat.id, buf,
                                  reply_to_message_id=getattr(message, "id", None))
    except Exception:
        buf.seek(0)
        await client.send_document(message.chat.id, buf, file_name="quote.webp",
                                   reply_to_message_id=getattr(message, "id", None))


def register(add, filters, add_cb, **kwargs) -> int:
    n = 0
    add(cmd_st, filters.command(["st"]), group=0); n += 1
    # Owner-only quote settings commands
    add(qcolor_cmd, filters.command(["qcolor"]), group=0); n += 1
    add(qb_cmd, filters.command(["qb"]), group=0); n += 1
    add(qemoji_cmd, filters.command(["qemoji"]), group=0); n += 1
    add(hidden_cmd, filters.command(["hidden"]), group=0); n += 1
    add(privacy_cmd, filters.command(["privacy"]), group=0); n += 1
    add(qrate_cmd, filters.command(["qrate"]), group=0); n += 1
    add(qgab_cmd, filters.command(["qgab"]), group=0); n += 1
    add(qarchive_cmd, filters.command(["qarchive"]), group=0); n += 1
    add(qforget_cmd, filters.command(["qforget"]), group=0); n += 1
    add(qd_cmd, filters.command(["qd"]), group=0); n += 1
    add(qdrand_cmd, filters.command(["qdrand"]), group=0); n += 1
    add(qs_cmd, filters.command(["qs"]), group=0); n += 1
    add(qapp_cmd, filters.command(["qapp"]), group=0); n += 1
    return n
