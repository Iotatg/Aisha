# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""Aisha Sticker / GIF media-reply system.

HOW IT WORKS
────────────
• A sticker is received → detect its mood from the sticker's emoji →
  reply with a REAL Telegram sticker of the same mood (sticker-to-
  sticker). Aisha NEVER sends text in reply to a sticker.
• Sticker packs are crowd-sourced: every sticker Aisha sees is auto-
  saved into a MongoDB pool keyed by mood, so the bot learns packs from
  the group/DMs without any owner setup. The owner can also curate packs
  with /addsticker etc.
• A GIF/animation received → reply with a mood-matched GIF (gif→gif,
  no caption). 

TRIGGER RULES
─────────────
• DMs: always active.
• Groups: only when the bot is @tagged in the caption OR the message is
  a reply to one of Aisha's messages.

RELIABILITY
───────────
Every send is wrapped so a failure at any step (sticker send, gif fetch)
can never crash the handler. A missing sticker/gif just means silence.
"""
import logging
import random
import re

import config
from core import gif
from core.db import db as get_db
from core.helpers import is_private
from core.owner import is_owner
from core.ui import notice

log = logging.getLogger(__name__)

# ── Emoji → mood mapping ─────────────────────────────────────────────────────
_EMOJI_MOOD: dict = {
    "😂": "laugh", "🤣": "laugh", "😹": "laugh", "💀": "laugh",
    "😍": "love", "🥰": "love", "💕": "love", "💞": "love",
    "❤️": "love", "🫶": "love", "💝": "love", "💘": "love",
    "😭": "sad", "😢": "sad", "💔": "sad", "😔": "sad", "😞": "sad",
    "😡": "angry", "🤬": "angry", "😤": "angry", "💢": "angry",
    "🥳": "happy", "😊": "happy", "😁": "happy", "🎉": "happy",
    "😄": "happy", "🤩": "happy", "🎊": "happy",
    "😮": "surprise", "😱": "surprise", "😲": "surprise", "👀": "surprise",
    "💃": "dance", "🕺": "dance", "🎵": "dance", "🎶": "dance",
    "😎": "cool", "🤙": "cool", "✌️": "cool",
    "🥺": "cute", "🌸": "cute", "✨": "cute", "🌷": "cute",
    "🍑": "cute", "🌼": "cute",
}


def _detect_mood_from_sticker(sticker) -> str:
    if not sticker:
        return "default"
    for ch in (getattr(sticker, "emoji", "") or ""):
        m = _EMOJI_MOOD.get(ch)
        if m:
            return m
    return "default"


def _detect_mood_from_text(text: str) -> str:
    for ch in text:
        m = _EMOJI_MOOD.get(ch)
        if m:
            return m
    tl = text.lower()
    if any(w in tl for w in ["dance", "vibe", "music", "song"]):
        return "dance"
    if any(w in tl for w in ["love", "kiss", "heart", "pyaar"]):
        return "love"
    if any(w in tl for w in ["funny", "lol", "haha", "laugh"]):
        return "laugh"
    if any(w in tl for w in ["angry", "mad", "rage", "gussa"]):
        return "angry"
    if any(w in tl for w in ["cute", "kawaii", "aww", "soft"]):
        return "cute"
    return "default"


# Related moods — when the detected mood has no saved sticker, try these.
_MOOD_RELATED: dict = {
    "happy":   ["laugh", "dance", "cute", "cool"],
    "laugh":   ["happy", "cute", "dance"],
    "love":    ["cute", "sad", "happy"],
    "cute":    ["love", "happy", "laugh"],
    "sad":     ["love", "cute"],
    "angry":   ["cool", "surprise"],
    "surprise": ["cool", "angry"],
    "dance":   ["happy", "cool", "laugh"],
    "cool":    ["happy", "dance", "surprise"],
    "default": [],
}


# ── MongoDB-backed sticker packs (mood -> [file_id, ...]) ────────────────────
async def save_sticker(mood: str, file_id: str) -> None:
    """Add one sticker file_id under a mood (de-duped)."""
    col = get_db().sticker_packs
    doc = await col.find_one({"_id": mood.lower()})
    fids = list(doc.get("fids", [])) if doc else []
    if file_id in fids:
        return
    fids.append(file_id)
    await col.find_one_and_update(
        {"_id": mood.lower()}, {"$set": {"fids": fids}}, upsert=True)


async def get_stickers_for_mood(mood: str) -> list:
    doc = await get_db().sticker_packs.find_one({"_id": mood.lower()})
    return list(doc.get("fids", [])) if doc else []


async def list_all_sticker_packs() -> dict:
    """{mood: count} for every configured mood."""
    docs = await get_db().sticker_packs.find({}).to_list(200)
    return {d["_id"]: len(d.get("fids", [])) for d in docs}


async def clear_sticker_pack(mood: str) -> int:
    r = await get_db().sticker_packs.delete_one({"_id": mood.lower()})
    return getattr(r, "deleted_count", 0)


def _pick_other(file_ids: list, current_fid: str) -> list:
    """Return the pool with the incoming sticker removed, so Aisha never
    just echoes back the exact sticker the user sent."""
    return [f for f in file_ids if f != current_fid]


def _mood_arg(message) -> str | None:
    parts = (message.text or "").split(None, 1)
    if len(parts) > 1 and parts[1].strip():
        return parts[1].strip().lower()
    return None


# ── Response gating (anti-spam) ──────────────────────────────────────────────
async def _should_respond(client, message) -> bool:
    chat = message.chat
    if is_private(chat):
        return True
    # reply to one of Aisha's own messages?
    rm = message.reply_to_message
    if rm and rm.from_user and getattr(rm.from_user, "username", "").lower() \
            == config.BOT_USERNAME.lower():
        return True
    # @tagged in caption/text?
    text = (message.caption or "") + " " + (message.text or "")
    if f"@{config.BOT_USERNAME}".lower() in text.lower():
        return True
    return False


# ── Sticker reply ────────────────────────────────────────────────────────────
async def _reply_sticker(client, message, mood: str, incoming_fid: str) -> bool:
    try:
        packs = await list_all_sticker_packs()
    except Exception as e:
        log.debug("list packs failed: %s", e)
        packs = {}

    # 1) exact mood, then 2) related moods.
    for m in [mood] + _MOOD_RELATED.get(mood, []):
        if packs.get(m):
            others = _pick_other(await get_stickers_for_mood(m), incoming_fid)
            if others:
                return await _send_sticker(client, message, others)
    # 3) last resort — any configured mood with a different sticker.
    for m in packs:
        others = _pick_other(await get_stickers_for_mood(m), incoming_fid)
        if others:
            return await _send_sticker(client, message, others)
    return False


async def _send_sticker(client, message, fids: list) -> bool:
    fid = random.choice(fids)
    try:
        await client.send_sticker(
            message.chat.id, fid, reply_to_message_id=message.id)
        return True
    except Exception as e:
        log.debug("sticker send failed: %s", e)
        return False


async def sticker_reply_handler(client, message):
    u = message.from_user
    if not u or getattr(u, "is_bot", False):
        return
    if not await _should_respond(client, message):
        return
    sticker = message.sticker
    if not sticker:
        return

    mood = _detect_mood_from_sticker(sticker)
    # Crowd-source: learn this sticker into its mood pool.
    try:
        await save_sticker(mood, sticker.file_id)
    except Exception as e:
        log.debug("save_sticker failed: %s", e)

    await _reply_sticker(client, message, mood, sticker.file_id)


# ── GIF / animation reply (gif→gif, no caption) ──────────────────────────────
async def gif_reply_handler(client, message):
    u = message.from_user
    if not u or getattr(u, "is_bot", False):
        return
    if not await _should_respond(client, message):
        return
    anim = message.animation
    if not anim:
        return

    hint = (message.caption or "") or (getattr(anim, "file_name", "") or "")
    mood = _detect_mood_from_text(hint)
    try:
        url = await gif.get_gif_for_mood(mood)
    except Exception as e:
        log.debug("gif lookup failed for '%s': %s", mood, e)
        url = None
    if url:
        # gif→gif only: no text caption. Silence if the fetch fails.
        await gif.send_animation_url(
            message.chat.id, url, "", message.id, config.BOT_TOKEN)


# ── Owner curation commands ───────────────────────────────────────────────────
async def cmd_addsticker(client, message):
    u = message.from_user
    if not u or not await is_owner(u.id):
        return
    rm = message.reply_to_message
    if not rm or not rm.sticker:
        await _safe_reply(message, notice("ʀᴇᴘʟʏ ᴛᴏ ᴀ ꜱᴛɪᴄᴋᴇʀ ᴛᴏ ꜱᴀᴠᴇ ɪᴛ 🎴"))
        return
    mood = _mood_arg(message) or _detect_mood_from_sticker(rm.sticker)
    await save_sticker(mood, rm.sticker.file_id)
    await _safe_reply(message, notice(f"ꜱᴀᴠᴇᴅ! ᴍᴏᴏᴅ: {mood} 🎴"))


async def cmd_stickerpacks(client, message):
    u = message.from_user
    if not u or not await is_owner(u.id):
        return
    try:
        packs = await list_all_sticker_packs()
    except Exception as e:
        log.debug("list packs failed: %s", e)
        packs = {}
    if not packs:
        await _safe_reply(message,
                          notice("ɴᴏ ꜱᴛɪᴄᴋᴇʀ ᴘᴀᴄᴋꜱ ʏᴇᴛ~ ᴀᴅᴅ ᴡɪᴛʜ /ᴀᴅᴅꜱᴛɪᴄᴋᴇʀ 🎴"))
        return
    lines = ["🎴 <b>ꜱᴛɪᴄᴋᴇʀ ᴘᴀᴄᴋꜱ</b>"]
    for m, c in sorted(packs.items()):
        lines.append(f"• {m}: {c} ꜱᴛɪᴄᴋᴇʀꜱ")
    await _safe_reply(message, "\n".join(lines))


async def cmd_clearstickers(client, message):
    u = message.from_user
    if not u or not await is_owner(u.id):
        return
    mood = _mood_arg(message)
    if not mood:
        await _safe_reply(message, notice("ᴜꜱᴇ /ᴄʟᴇᴀʀꜱᴛɪᴄᴋᴇʀꜱ <ᴍᴏᴏᴅ> 🎴"))
        return
    try:
        n = await clear_sticker_pack(mood)
    except Exception as e:
        log.debug("clear failed: %s", e)
        n = 0
    await _safe_reply(message, notice(f"ᴄʟᴇᴀʀᴇᴅ {mood}: {n} 🎴"))


async def cmd_previewsticker(client, message):
    u = message.from_user
    if not u or not await is_owner(u.id):
        return
    mood = _mood_arg(message)
    if not mood:
        await _safe_reply(message, notice("ᴜꜱᴇ /ᴘʀᴇᴠɪᴇᴡꜱᴛɪᴄᴋᴇʀ <ᴍᴏᴏᴅ> 🎴"))
        return
    try:
        fids = await get_stickers_for_mood(mood)
    except Exception as e:
        log.debug("preview failed: %s", e)
        fids = []
    if not fids:
        await _safe_reply(message, notice(f"ɴᴏ ꜱᴛɪᴄᴋᴇʀꜱ ɪɴ {mood} 🎴"))
        return
    fid = random.choice(fids)
    try:
        await client.send_sticker(
            message.chat.id, fid, reply_to_message_id=message.id)
    except Exception as e:
        log.debug("preview send failed: %s", e)


async def _safe_reply(message, text):
    try:
        await message.reply(text)
    except Exception as e:
        log.debug("owner cmd reply failed: %s", e)


def register(add, filters, add_cb, **kwargs) -> int:
    n = 0
    add(sticker_reply_handler, filters.sticker, group=17)
    n += 1
    add(gif_reply_handler, filters.animation, group=17)
    n += 1
    add(cmd_addsticker, filters.command(["addsticker"]))
    n += 1
    add(cmd_stickerpacks, filters.command(["stickerpacks"]))
    n += 1
    add(cmd_clearstickers, filters.command(["clearstickers"]))
    n += 1
    add(cmd_previewsticker, filters.command(["previewsticker"]))
    n += 1
    return n
