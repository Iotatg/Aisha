# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""Aisha Fun & Social pack — GIF/action system.

Built on Aisha's pyrogram/kurigram engine. Same battle-tested contract:

  • action commands (slap/punch/...) are REPLY-REQUIRED — bare command
    nudges "❗ ʀᴇᴘʟʏ ᴛᴏ ꜱᴏᴍᴇᴏɴᴇ:".
  • you can't hit YOURSELF → funny self-block.
  • you can't hit THE BOT → Aisha hits back (she's immortal 💅).
  • other bots are immortal too.
  • single-user cooldown across ALL fun commands (anti spam).
  • every action pulls a matching anime GIF from the live GIPHY search
    (core/gif.py). If GIPHY is down it degrades to plain text — never a
    broken image, never a silent command.

Social/self-emote commands are text-only (no GIF).
Truth/Dare/Puzzle use STATIC banks (no AI/Mongo) per Aisha's scope.
"""
import aiohttp
import logging
import random
import time

import config
from core import gif
from core.helpers import mention, is_private
from core.ui import card, notice, hearts_bar, stable_pct

log = logging.getLogger(__name__)

# ── Anti-spam guard (one fun action per user per window, across all cmds) ──
FUN_COOLDOWN = 3.0
_fun_last: dict = {}

# Cached bot id (for the "can't hit the bot" check).
_ME_ID = None


async def _me_id(client) -> int | None:
    global _ME_ID
    if _ME_ID is None:
        try:
            _ME_ID = (await client.get_me()).id
        except Exception as e:
            log.debug("get_me failed: %s", e)
            _ME_ID = None
    return _ME_ID


def _guard(uid: int) -> bool:
    if not uid:
        return True
    now = time.time()
    if now - _fun_last.get(uid, 0.0) < FUN_COOLDOWN:
        return False
    _fun_last[uid] = now
    return True


def _is_self(u, t) -> bool:
    return u is not None and t is not None and u.id == t.id


# ── GIF delivery: send the GIF URL to Telegram's Bot API, so Telegram's
# servers fetch it — instant, no in-bot download+re-upload like MTProto
# would require. The caption carries the action text, reply_animation-style.
# ─────────────────────────────────────────────────────────────────────────
async def _send(client, message, text: str, mood: str | None = None):
    rid = getattr(message, "id", None)
    if mood:
        try:
            url = await gif.get_gif_for_mood(mood)
        except Exception as e:
            log.debug("gif url lookup failed (%s): %s", mood, e)
            url = None
        if url and await _bot_send_animation(message.chat.id, url, text, rid):
            return
    # Text fallback (MTProto) — a missing GIF must never swallow the reply.
    try:
        await client.send_message(
            message.chat.id, text, reply_to_message_id=rid)
    except Exception as e:
        log.debug("text fallback failed: %s", e)


async def _bot_send_animation(chat_id, url: str, caption: str, rid) -> bool:
    """Send an animation by URL via the Bot API (server-side fetch = fast).
    Returns True if Telegram accepted it. Falls back to False so the
    caller can send plain text instead."""
    return await gif.send_animation_url(
        chat_id, url, caption, rid, config.BOT_TOKEN)


# ── Local image ship (Sep 2026) ──────────────────────────────────────────────
# /ship sends the matchmaking banner (assets/ship/banner.jpg) as a photo
# with the verdict text as caption. /couple sends the couple image
# (couple.jpg) standalone. Missing files silently fall back to text.
import os

_SHIP_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "assets", "ship"
)
_BANNER_PATH = os.path.join(_SHIP_DIR, "banner.jpg")
_COUPLE_PATH = os.path.join(_SHIP_DIR, "couple.jpg")


async def _send_photo_local(client, message, path: str, caption: str):
    """Send a local file as photo with caption. Falls back to text when
    the file is missing so /ship and /couple never silently fail."""
    rid = getattr(message, "id", None)
    chat_id = message.chat.id
    if not os.path.isfile(path):
        await _send(client, message, caption)
        return
    try:
        await client.send_photo(
            chat_id, photo=path, caption=caption, reply_to_message_id=rid
        )
    except Exception as e:
        log.debug("local photo send failed (%s); falling back to text", e)
        await _send(client, message, caption)


# ── Self / bot "can't do that" replies (Aisha small-caps voice) ────────────
_SELF = {
    "slap": ["🙄 ꜱʟᴀᴘᴘɪɴɢ ʏᴏᴜʀꜱᴇʟꜰ? ᴀʀᴇ ʏᴏᴜ ᴀ ᴍᴀꜱᴏᴄʜɪꜱᴛ? 😂",
            "💅 ꜱʟᴀᴘ ʏᴏᴜʀꜱᴇʟꜰ? ɪɴᴛᴇʀᴇꜱᴛɪɴɢ ᴄʜᴏɪᴄᴇ ʙᴇꜱᴛɪᴇ"],
    "murder": ["💀 ᴍᴜʀᴅᴇʀɪɴɢ ʏᴏᴜʀꜱᴇʟꜰ? ᴛʜᴇʀᴀᴘʏ ᴛɪᴍᴇ 🥺",
              "😭 ᴅᴏɴ'ᴛ ʜᴜʀᴛ ʏᴏᴜʀꜱᴇʟꜰ ʙᴀʙᴇ~ ʟᴇᴀʀɴ ꜱᴏᴍᴇ ꜱᴇʟꜰ-ʟᴏᴠᴇ 💕"],
    "kiss": ["💋 ᴋɪꜱꜱɪɴɢ ʏᴏᴜʀꜱᴇʟꜰ? ᴛʜᴀᴛ'ꜱ ᴀ ʙɪᴛ ɴᴀʀᴄɪꜱꜱɪꜱᴛɪᴄ 😂",
            "😂 ɢᴏ ꜱᴛᴀɴᴅ ɪɴ ꜰʀᴏɴᴛ ᴏꜰ ᴀ ᴍɪʀʀᴏʀ ʙᴇꜱᴛɪᴇ"],
    "hug": ["🤗 ᴀᴡᴡ ꜱᴇʟꜰ-ʜᴜɢ! ᴏᴋᴀʏ ᴛʜᴀᴛ'ꜱ ᴄᴜᴛᴇ 🥺",
           "💕 ʜᴜɢɢɪɴɢ ʏᴏᴜʀꜱᴇʟꜰ ɪꜱ ꜱᴡᴇᴇᴛ ʙᴜᴛ... ᴄᴏᴍᴇ ʜᴇʀᴇ 🤗"],
    "bite": ["😬 ʙɪᴛɪɴɢ ʏᴏᴜʀꜱᴇʟꜰ? ᴡʜᴀᴛ'ꜱ ᴡʀᴏɴɢ ᴡɪᴛʜ ʏᴏᴜ 💀",
            "😂 ʏᴏᴜ'ᴅ ʙɪᴛᴇ ʏᴏᴜʀꜱᴇʟꜰ? ᴏᴋᴀʏ ᴡᴇɪʀᴅᴏ 💅"],
    "punch": ["😂 ᴘᴜɴᴄʜɪɴɢ ʏᴏᴜʀꜱᴇʟꜰ? ꜱᴇᴇ ᴀ ᴅᴏᴄᴛᴏʀ",
             "🙄 ᴅᴏɴ'ᴛ ʙᴇ ᴅʀᴀᴍᴀᴛɪᴄ, ᴅᴏɴ'ᴛ ᴘᴜɴᴄʜ ʏᴏᴜʀꜱᴇʟꜰ!"],
}
_BOT = {
    "slap": ["👋 ᴡʜᴀᴛ ᴅᴏɪɴɢ? 😑", "ꜱʟᴀᴘ ʙᴀᴄᴋ ᴛᴏ ʏᴏᴜ 😒 ᴛᴀᴋᴇ ᴛʜᴀᴛ!"],
    "murder": ["😈 ʏᴏᴜ Cᴀɴ'ᴛ Mᴜʀᴅᴇʀ Mᴇ! ɪ'ᴍ ɪᴍᴍᴏʀᴛᴀʟ 🔪",
              "💀 ᴛʀʏ ᴍᴜʀᴅᴇʀɪɴɢ ᴍᴇ? ɪ'ᴍ ᴅɪɢɪᴛᴀʟ ʙᴇꜱᴛɪᴇ~ ɴᴏ ᴄʜᴀɴᴄᴇ 😂"],
    "punch": ["ᴘᴜɴᴄʜ ʙᴀᴄᴋ ᴛᴏ ʏᴏᴜ 😑", "👊 ᴛᴀᴋᴇ ᴛʜᴀᴛ ᴘᴜɴᴄʜ! 😒"],
    "kiss": ["😳 ᴋɪꜱꜱ? ɪ'ᴍ ʙʟᴜꜱʜɪɴɢ ᴄᴜᴛɪᴇ 💕", "💋 ᴀᴡᴡ ᴏᴋᴀʏ 😳"],
    "hug": ["🤗 ʜᴜɢ ʙᴀᴄᴋ! ʏᴏᴜ'ʀᴇ ᴋɪɴᴅᴀ ᴄᴜᴛᴇ 💕", "ᴀᴡᴡ ʜᴜɢ 🥺💕"],
    "bite": ["😤 ʙɪᴛᴇ ᴍᴇ? ɪ'ʟʟ ʙɪᴛᴇ ʏᴏᴜ ʙᴀᴄᴋ! 😤",
            "ᴏᴜᴄʜ 😒 ʙɪᴛᴇ ʙᴀᴄᴋ ᴛᴏ ʏᴏᴜ ʙᴇꜱᴛɪᴇ"],
}
_SELF_GENERIC = ["🙄 ᴋʜᴜᴅ ᴋᴏ ᴍᴀʀɴᴀ? ᴅʀᴀᴍᴀ Qᴜᴇᴇɴ 😂",
                "💅 ꜱᴏ ʏᴏᴜ'ʀᴇ ꜰɪɢʜᴛɪɴɢ ʏᴏᴜʀꜱᴇʟꜰ ɴᴏᴡ? ᴏᴋᴀʏ ʙᴇꜱᴛɪᴇ"]
_BOT_GENERIC = ["😤 ʏᴏᴜ ᴡᴀɴɴᴀ ʜɪᴛ ᴍᴇ? ɪ'ᴍ ɪᴍᴍᴏʀᴛᴀʟ ʙᴀʙᴇ 💅",
                "😒 ɴᴀᴀʜ~ ɪ'ᴍ ɪɴᴠɪɴᴄɪʙʟᴇ, ᴛʀʏ ᴀ ʜᴜᴍᴀɴ 😎"]


def _make_action(name, gif_key, caption_fn,
                 self_msgs=None, bot_back_msgs=None, bot_mood=None):
    """Build a reply-required action command with self/bot/spam guards."""
    self_msgs = self_msgs or _SELF.get(name, _SELF_GENERIC)
    bot_back_msgs = bot_back_msgs or _BOT.get(name, _BOT_GENERIC)
    bot_mood = bot_mood or gif_key

    async def _cmd(client, message):
        u = message.from_user
        if not _guard(u.id if u else 0):
            return
        rm = message.reply_to_message
        if not rm or not rm.from_user:
            await _send(client, message,
                        notice(f"ʀᴇᴘʟʏ ᴛᴏ ꜱᴏᴍᴇᴏɴᴇ: /{name} 💢"))
            return
        t = rm.from_user
        if _is_self(u, t):
            await _send(client, message, random.choice(self_msgs))
            return
        me = await _me_id(client)
        if me is not None and t.id == me:
            await _send(client, message, random.choice(bot_back_msgs), bot_mood)
            return
        from core.helpers import HARM_OWNER
        from core.owner import is_owner as _is_bot_owner
        if await _is_bot_owner(t.id) and not await _is_bot_owner(u.id if u else 0):
            await _send(client, message, HARM_OWNER)
            return
        if getattr(t, "is_bot", False):
            await _send(client, message,
                        notice("ʙᴏᴛꜱ ᴀʀᴇ ɪᴍᴍᴏʀᴛᴀʟ ʙᴀʙᴇ~ ʜɪᴛ ᴀ ʜᴜᴍᴀɴ 💀"))
            return
        # Track the kill for /topkills leaderboard.
        if name == "murder":
            try:
                from core import money as _money
                await _money.ensure_user(u.id, username=u.username or "",
                                         name=u.first_name)
                await _money.add_kill(u.id)
            except Exception as _e:
                logger.debug("add_kill failed (non-fatal): %s", _e)
        await _send(client, message, caption_fn(u, t), gif_key)
    return _cmd


def _m(u):
    return mention(u.id, u.first_name)


# ── Action commands (reply-target + self/bot checks + mood GIF) ────────────
cmd_slap = _make_action(
    "slap", "slap",
    lambda u, t: f"👋 {_m(u)} ꜱʟᴀᴘꜱ {_m(t)} ʜᴀʀᴅ! 💥")
cmd_punch = _make_action(
    "punch", "punch",
    lambda u, t: f"👊 {_m(u)} ᴘᴜɴᴄʜᴇꜱ {_m(t)}! 💢")
cmd_kick = _make_action(
    "kick", "kick",
    lambda u, t: f"🦵 {_m(u)} ᴋɪᴄᴋꜱ {_m(t)}! 💢")
cmd_murder = _make_action(
    "murder", "murder",
    lambda u, t: f"🔪 {_m(u)} ᴍᴜʀᴅᴇʀꜱ {_m(t)} ᴡɪᴛʜ ᴀ {random.choice(['🔪 ᴋɴɪꜰᴇ','🔫 ɢᴜɴ','☠️ ᴘᴏɪꜱᴏɴ','💣 ʙᴏᴍʙ','🪓 ᴀxᴇ','🏹 ᴀʀʀᴏᴡ'])}! 💀")
cmd_kiss = _make_action(
    "kiss", "kiss",
    lambda u, t: f"💋 {_m(u)} ᴋɪꜱꜱᴇꜱ {_m(t)}! 💕")
cmd_bite = _make_action(
    "bite", "bite",
    lambda u, t: f"😈 {_m(u)} ʙɪᴛᴇꜱ {_m(t)}! 🦷")
cmd_hug = _make_action(
    "hug", "hug",
    lambda u, t: f"🤗 {_m(u)} ʜᴜɢꜱ {_m(t)} ᴛɪɢʜᴛʟʏ! 💞")

cmd_fall = _make_action(
    "fall", "fall",
    lambda u, t: f"🪂 {_m(u)} ᴘᴜꜱʜᴇꜱ {_m(t)} ᴏꜰꜰ ᴀ ᴄʟɪꜰꜰ! 😱")
cmd_throw = _make_action(
    "throw", "throw",
    lambda u, t: f"🌀 {_m(u)} ᴛʜʀᴏᴡꜱ {_m(t)} ᴀᴄʀᴏꜱꜱ ᴛʜᴇ ʀᴏᴏᴍ! 💫")
cmd_highfive = _make_action(
    "highfive", "happy",
    lambda u, t: f"🙌 {_m(u)} ʜɪɢʜ-ꜰɪᴠᴇꜱ {_m(t)}! ✨")
cmd_poke = _make_action(
    "poke", "cute",
    lambda u, t: f"👉 {_m(u)} ᴘᴏᴋᴇꜱ {_m(t)}! 😏")
cmd_tickle = _make_action(
    "tickle", "laugh",
    lambda u, t: f"🤭 {_m(u)} ᴛɪᴄᴋʟᴇꜱ {_m(t)}! 😂")
cmd_facepalm = _make_action(
    "facepalm", "default",
    lambda u, t: f"🤦 {_m(u)} ꜰᴀᴄᴇᴘᴀʟᴍꜱ ᴀᴛ {_m(t)}!")
cmd_pie = _make_action(
    "pie", "funny",
    lambda u, t: f"🥧 {_m(u)} ᴛʜʀᴏᴡꜱ ᴀ ᴘɪᴇ ᴀᴛ {_m(t)}! 😂")
cmd_trip = _make_action(
    "trip", "surprise",
    lambda u, t: f"🦶 {_m(u)} ᴛʀɪᴘꜱ {_m(t)}! 😂")
cmd_freeze = _make_action(
    "freeze", "cool",
    lambda u, t: f"❄️ {_m(u)} ꜰʀᴏᴢᴇ {_m(t)} ꜱᴏʟɪᴅ! 🥶")
cmd_zap = _make_action(
    "zap", "surprise",
    lambda u, t: f"⚡ {_m(u)} ᴢᴀᴘᴘᴇᴅ {_m(t)} ᴡɪᴛʜ ʟɪɢʜᴛɴɪɴɢ! ⚡")
cmd_dancewith = _make_action(
    "dancewith", "dance",
    lambda u, t: f"💃 {_m(u)} ᴅᴀɴᴄᴇꜱ ᴡɪᴛʜ {_m(t)}! 🕺✨")

cmd_pat = _make_action(
    "pat", "pat",
    lambda u, t: f"🤚 {_m(u)} ᴘᴀᴛꜱ {_m(t)}'ꜱ ʜᴇᴀᴅ! 🥺")
cmd_cuddle = _make_action(
    "cuddle", "hug",
    lambda u, t: f"🫂 {_m(u)} ᴄᴜᴅᴅʟᴇꜱ {_m(t)}! 💞")
cmd_lick = _make_action(
    "lick", "cute",
    lambda u, t: f"👅 {_m(u)} ʟɪᴄᴋꜱ {_m(t)}! 😝")
cmd_bonk = _make_action(
    "bonk", "funny",
    lambda u, t: f"🔨 {_m(u)} ʙᴏɴᴋꜱ {_m(t)} ᴏɴ ᴛʜᴇ ʜᴇᴀᴅ! 💥")
cmd_glare = _make_action(
    "glare", "angry",
    lambda u, t: f"😠 {_m(u)} ɢʟᴀʀᴇꜱ ᴀᴛ {_m(t)}! 🔥")
cmd_feed = _make_action(
    "feed", "happy",
    lambda u, t: f"🍰 {_m(u)} ꜰᴇᴇᴅꜱ {_m(t)} ꜱᴏᴍᴇᴛʜɪɴɢ ꜱᴡᴇᴇᴛ! 🥰")
cmd_beer = _make_action(
    "beer", "happy",
    lambda u, t: f"🍻 {_m(u)} ᴄʜᴇᴇʀꜱ ᴡɪᴛʜ {_m(t)}! 🍺")

cmd_boop = _make_action(
    "boop", "cute",
    lambda u, t: f"👉 {_m(u)} ʙᴏᴏᴘꜱ {_m(t)} ᴏɴ ᴛʜᴇ ɴᴏꜱᴇ! 🥺")
cmd_ruffle = _make_action(
    "ruffle", "cute",
    lambda u, t: f"🖐️ {_m(u)} ʀᴜꜰꜰʟᴇꜱ {_m(t)}'ꜱ ʜᴀɪʀ! ✨")
cmd_smooch = _make_action(
    "smooch", "kiss",
    lambda u, t: f"💋 {_m(u)} ɢɪᴠᴇꜱ {_m(t)} ᴀ ʙɪɢ ꜱᴍᴏᴏᴄʜ! 😘")
cmd_tackle = _make_action(
    "tackle", "funny",
    lambda u, t: f"🏈 {_m(u)} ᴛᴀᴄᴋʟᴇꜱ {_m(t)} ᴘʟᴀʏꜰᴜʟʟʏ! 💥")
cmd_pinch = _make_action(
    "pinch", "cute",
    lambda u, t: f"🤏 {_m(u)} ᴘɪɴᴄʜᴇꜱ {_m(t)}'ꜱ ᴄʜᴇᴇᴋ! 😊")
cmd_fistbump = _make_action(
    "fistbump", "happy",
    lambda u, t: f"👊 {_m(u)} ꜰɪꜱᴛ-ʙᴜᴍᴘꜱ {_m(t)}! 🔥")
cmd_bearhug = _make_action(
    "bearhug", "hug",
    lambda u, t: f"🐻 {_m(u)} ɢɪᴠᴇꜱ {_m(t)} ᴀ ɢɪᴀɴᴛ ʙᴇᴀʀ ʜᴜɢ! 🤗")
cmd_foreheadkiss = _make_action(
    "foreheadkiss", "kiss",
    lambda u, t: f"😚 {_m(u)} ᴋɪꜱꜱᴇꜱ {_m(t)} ᴏɴ ᴛʜᴇ ꜰᴏʀᴇʜᴀᴅ! 💕")
cmd_spin = _make_action(
    "spin", "dance",
    lambda u, t: f"🌀 {_m(u)} ꜱᴘɪɴꜱ {_m(t)}! 💫")
cmd_dab = _make_action(
    "dab", "dance",
    lambda u, t: f"💪 {_m(u)} ᴅᴀʙꜱ ᴏɴ {_m(t)}! 😎")
cmd_flex = _make_action(
    "flex", "happy",
    lambda u, t: f"💪 {_m(u)} ꜰʟᴇxᴇꜱ ᴏɴ {_m(t)}! 🔥")
cmd_nom = _make_action(
    "nom", "cute",
    lambda u, t: f"🍪 {_m(u)} ɴᴏᴍꜱ {_m(t)}! 😋")
cmd_squish = _make_action(
    "squish", "cute",
    lambda u, t: f"🧸 {_m(u)} ꜱQᴜɪꜱʜᴇꜱ {_m(t)}! 🥺")
cmd_yeet = _make_action(
    "yeet", "throw",
    lambda u, t: f"🚀 {_m(u)} ʏᴇᴇᴛꜱ {_m(t)} ɪɴᴛᴏ ᴛʜᴇ ᴠᴏɪᴅ! 💀")
cmd_stare = _make_action(
    "stare", "default",
    lambda u, t: f"👀 {_m(u)} ꜱᴛᴀʀᴇꜱ ᴀᴛ {_m(t)}... 🔥")
cmd_laugh = _make_action(
    "laugh", "laugh",
    lambda u, t: f"😂 {_m(u)} ʟᴀᴜɢʜꜱ ᴡɪᴛʜ {_m(t)}! 🤣")
cmd_shoulderpunch = _make_action(
    "shoulderpunch", "punch",
    lambda u, t: f"👊 {_m(u)} ɢɪᴠᴇꜱ {_m(t)} ᴀ ᴘʟᴀʏꜰᴜʟ ꜱʜᴏᴜʟᴅᴇʀ ᴘᴜɴᴄʜ! 💢")
cmd_cheekpinch = _make_action(
    "cheekpinch", "cute",
    lambda u, t: f"😊 {_m(u)} ᴘɪɴᴄʜᴇꜱ {_m(t)}'ꜱ ᴄʜᴇᴇᴋꜱ! 🥰")
cmd_headrub = _make_action(
    "headrub", "pat",
    lambda u, t: f"🤲 {_m(u)} ʀᴜʙꜱ {_m(t)}'ꜱ ʜᴇᴀᴅ ɢᴇɴᴛʟʏ! 😌")
cmd_grouphug = _make_action(
    "grouphug", "hug",
    lambda u, t: f"🫂 {_m(u)} ᴘᴜʟʟꜱ {_m(t)} ɪɴᴛᴏ ᴀ ɢʀᴏᴜᴘ ʜᴜɢ! 💞✨")
cmd_suplex = _make_action(
    "suplex", "funny",
    lambda u, t: f"🤼 {_m(u)} ꜱᴜᴘʟᴇxᴇꜱ {_m(t)}! 💥")
cmd_boopboop = _make_action(
    "boopboop", "cute",
    lambda u, t: f"👉👉 {_m(u)} ᴅᴏᴜʙʟᴇ-ʙᴏᴏᴘꜱ {_m(t)}! 🥺💕")
cmd_cheekkiss = _make_action(
    "cheekkiss", "kiss",
    lambda u, t: f"😘 {_m(u)} ᴋɪꜱꜱᴇꜱ {_m(t)} ᴏɴ ᴛʜᴇ ᴄʜᴇᴇᴋ! 🌸")
cmd_headpat = _make_action(
    "headpat", "pat",
    lambda u, t: f"🤚 {_m(u)} ɢɪᴠᴇꜱ {_m(t)} ꜱᴏꜰᴛ ʜᴇᴀᴅᴘᴀᴛꜱ! 🥺✨")


# ── Self-emotes (text only, no reply needed) ───────────────────────────────
async def cmd_cry(client, message):
    if not _guard(message.from_user.id if message.from_user else 0):
        return
    u = message.from_user
    await _send(client, message, random.choice([
        f"😭 {_m(u)} ɪꜱ ᴄʀʏɪɴɢ... 💔",
        f"😢 {_m(u)} ꜱᴛᴀʀᴛᴇᴅ ꜱᴏʙʙɪɴɢ 😭",
        f"💧 {_m(u)} ꜱᴛᴀʀᴛᴇᴅ ᴄʀʏɪɴɢ ᴀʙᴏᴜᴛ ꜱᴏᴍᴇᴛʜɪɴɢ 😭",
    ]))


async def cmd_blush(client, message):
    if not _guard(message.from_user.id if message.from_user else 0):
        return
    u = message.from_user
    await _send(client, message, random.choice([
        f"😊 {_m(u)} ɪꜱ ʙʟᴜꜱʜɪɴɢ~ 🌸",
        f"🥺 {_m(u)} ᴛᴜʀɴᴇᴅ ʀᴇᴅ 😳",
        f"🌸 {_m(u)} ɢᴏᴛ ꜱʜʏ 😊",
    ]))


async def cmd_wave(client, message):
    if not _guard(message.from_user.id if message.from_user else 0):
        return
    await _send(client, message,
                f"👋 {_m(message.from_user)} ᴡᴀᴠᴇꜱ ʜᴇʟʟᴏ! 👋")


async def cmd_wink(client, message):
    if not _guard(message.from_user.id if message.from_user else 0):
        return
    await _send(client, message,
                f"😉 {_m(message.from_user)} ᴡɪɴᴋꜱ ᴀᴛ ʏᴏᴜ~ 😏")


async def cmd_dance(client, message):
    if not _guard(message.from_user.id if message.from_user else 0):
        return
    u = message.from_user
    await _send(client, message, random.choice([
        f"💃 {_m(u)} ɪꜱ ᴅᴀɴᴄɪɴɢ! 🕺✨",
        f"🕺 {_m(u)} ᴅʀᴏᴘᴘᴇᴅ ᴀ ᴍᴏᴠᴇ! 💃",
        f"🎶 {_m(u)} ᴅᴀɴᴄᴇ ᴘᴀʀᴛʏ ꜱʜᴜʀᴜ! 💃🕺",
    ]))


async def cmd_sleep(client, message):
    if not _guard(message.from_user.id if message.from_user else 0):
        return
    u = message.from_user
    await _send(client, message, random.choice([
        f"😴 {_m(u)} ꜰᴇʟʟ ᴀꜱʟᴇᴇᴘ... 💤",
        f"💤 {_m(u)} ꜱᴏ ɢᴀʏᴀ/ꜱʜᴀʏɪ 🥱",
        f"🛌 {_m(u)} ɪꜱ ꜱʟᴇᴇᴘɪɴɢ ᴘᴇᴀᴄᴇꜰᴜʟʟʏ 😴",
    ]))


# ── Reply-target social texts ────────────────────────────────────────────────
async def cmd_simp(client, message):
    if not _guard(message.from_user.id if message.from_user else 0):
        return
    u = message.from_user
    rm = message.reply_to_message
    if not rm or not rm.from_user:
        await _send(client, message, notice("ʀᴇᴘʟʏ ᴛᴏ ꜱᴏᴍᴇᴏɴᴇ ᴛᴏ ᴄᴀʟʟ ᴛʜᴇᴍ ᴀ ꜱɪᴍᴘ! 😂"))
        return
    t = rm.from_user
    if _is_self(u, t):
        await _send(client, message, "😂 ᴋʜᴜᴅ ᴋᴏ ꜱɪᴍᴘ? ꜱᴇʟꜰ-ʟᴏᴠᴇ ꜰʀ 💀")
        return
    me = await _me_id(client)
    if me is not None and t.id == me:
        await _send(client, message, "😳 ᴍᴇ? ʏᴏᴜʀ ꜱɪᴍᴘ? ɪ'ᴍ ʙʟᴜꜱʜɪɴɢ 💕")
        return
    await _send(client, message,
                f"😂 {_m(u)} ᴋᴇʜᴛᴀ/ᴋᴇʜᴛɪ ʜᴀɪ {_m(t)} ɪꜱ ꜱᴜᴄʜ ᴀ ꜱɪᴍᴘ! 💀👑")


async def cmd_sus(client, message):
    if not _guard(message.from_user.id if message.from_user else 0):
        return
    u = message.from_user
    rm = message.reply_to_message
    if not rm or not rm.from_user:
        await _send(client, message, notice("🛸 ʀᴇᴘʟʏ ᴛᴏ ꜱᴏᴍᴇᴏɴᴇ ᴛᴏ ᴄᴀʟʟ ᴛʜᴇᴍ ꜱᴜꜱ!"))
        return
    t = rm.from_user
    if _is_self(u, t):
        await _send(client, message, "🚨 ᴋʜᴜᴅ ᴋᴏ ꜱᴜꜱ? ꜱᴇʟꜰ-ʀᴇᴘᴏʀᴛ! 💀")
        return
    me = await _me_id(client)
    if me is not None and t.id == me:
        await _send(client, message,
                    "🚨 ᴍᴀɪɴ ꜱᴜꜱ? ɴᴇᴠᴇʀ 😎 (ᴇᴍᴇʀɢᴇɴᴄʏ ᴍᴇᴇᴛɪɴɢ! 🛸)")
        return
    await _send(client, message,
                f"🚨 {_m(t)} ɪꜱ ꜱᴜꜱ! 🛸 ʀᴇᴅ ᴀʟᴇʀᴛ, ᴄʀᴇᴡᴍᴀᴛᴇ! 🔴")


# ── Social commands ─────────────────────────────────────────────────────────
async def cmd_couples(client, message):
    if is_private(message.chat):
        await _send(client, message,
                    notice("ɢʀᴏᴜᴘꜱ ᴏɴʟʏ ʙᴀʙᴇ~ ᴜꜱᴇ ᴛʜɪꜱ ɪɴ ᴀ ɢʀᴏᴜᴘ 💕"))
        return
    pool = []
    try:
        seen = set()
        async for m in client.get_chat_history(message.chat.id, limit=120):
            u = m.from_user
            if u and not u.is_bot and u.id not in seen:
                seen.add(u.id)
                pool.append(u)
            if len(pool) >= 30:
                break
    except Exception as e:
        log.debug("couples history failed: %s", e)
        pool = []
    if len(pool) < 2:
        await _send(client, message,
                    notice("ɴᴏᴛ ᴇɴᴏᴜɢʜ ᴘᴇᴏᴘʟᴇ ʜᴇʀᴇ ʏᴇᴛ~ ᴄʜᴀᴛ ᴍᴏʀᴇ ʙᴀʙᴇ 💕"))
        return
    a, b = random.sample(pool, 2)
    await _send(client, message,
                f"💕 <b>ᴛᴏᴅᴀʏ'ꜱ ᴄᴏᴜᴘʟᴇ!</b>\n\n"
                f"{_m(a)} ❤️ {_m(b)}\n\n"
                f"ᴄᴏᴍᴘᴀᴛɪʙɪʟɪᴛʏ: <b>{random.randint(60, 100)}%</b> 💘")


async def cmd_crush(client, message):
    if is_private(message.chat):
        await _send(client, message,
                    notice("ɢʀᴏᴜᴘꜱ ᴏɴʟʏ ʙᴀʙᴇ~ ʀᴇᴘʟʏ ɪɴ ᴀ ɢʀᴏᴜᴘ 💗"))
        return
    u = message.from_user
    rm = message.reply_to_message
    if not rm or not rm.from_user:
        await _send(client, message, notice("🚫 ʀᴇᴘʟʏ ᴛᴏ ꜱᴏᴍᴇᴏɴᴇ!"))
        return
    t = rm.from_user
    await _send(client, message,
                f"💗 {_m(u)} ʜᴀꜱ ᴀ ᴄʀᴜꜱʜ ᴏɴ {_m(t)}! 🥺\n"
                f"ᴄʀᴜꜱʜ ᴍᴇᴛᴇʀ: <b>{random.randint(50, 100)}%</b> 💕")


async def cmd_love(client, message):
    u = message.from_user
    rm = message.reply_to_message
    t = rm.from_user if (rm and rm.from_user) else u
    pct = random.randint(0, 100)
    heart = ("💔" if pct < 30 else "💛" if pct < 60
             else "❤️" if pct < 85 else "💘")
    await _send(client, message,
                f"{heart} {_m(u)} + {_m(t)} = <b>{pct}%</b> {heart}")


async def cmd_look(client, message):
    u = message.from_user
    rm = message.reply_to_message
    if not rm or not rm.from_user:
        await _send(client, message, notice("ʀᴇᴘʟʏ ᴛᴏ ꜱᴏᴍᴇᴏɴᴇ."))
        return
    t = rm.from_user
    await _send(client, message,
                f"👀 {_m(u)} ɪꜱ ʟᴏᴏᴋɪɴɢ ᴀᴛ {_m(t)}... {random.randint(60, 100)}/100 😍")


async def cmd_brain(client, message):
    rm = message.reply_to_message
    t = rm.from_user if (rm and rm.from_user) else message.from_user
    pct = random.randint(1, 200)
    txt = ("🤯 ɢᴇɴɪᴜꜱ!" if pct > 150
           else "😐 ᴀᴠᴇʀᴀɢᴇ" if pct > 80 else "😂 ʟᴏʟ")
    await _send(client, message,
                f"🧠 {_m(t)}'ꜱ ʙʀᴀɪɴ: <b>{pct}%</b>{txt}")


async def cmd_stupid(client, message):
    rm = message.reply_to_message
    t = rm.from_user if (rm and rm.from_user) else message.from_user
    await _send(client, message,
                f"🤪 {_m(t)}: <b>{random.randint(0, 100)}%</b> ꜱᴛᴜᴘɪᴅ 😂")


# ── Truth / Dare / Puzzle (static banks, no AI/Mongo) ───────────────────────
TRUTH_LIST = [
    "ᴋᴀʙʜɪ ᴋɪꜱɪ ᴄʀᴜꜱʜ ᴋᴏ ᴘʀᴏᴘᴏꜱᴇ ᴋɪʏᴀ ʜ? 👀",
    "ɢʀᴏᴜᴘ ᴍᴇɪɴ ꜱᴀʙꜱᴇ ᴄᴜᴛᴇ ᴋᴀᴜɴ ʜ?",
    "ᴀᴘɴɪ ᴇx ꜱᴇ ᴀʙʜɪ ʙᴀᴀᴛ ʜᴏᴛɪ ʜ ᴋʏᴀ?",
    "ꜱᴀʙꜱᴇ ᴇᴍʙᴀʀʀᴀꜱꜱɪɴɢ ᴍᴏᴍᴇɴᴛ ʙᴀᴛᴀᴏ~ 🫣",
    "ᴋɪꜱꜱ ᴘᴇʜʟɪ ʙᴀᴀʀ ᴋᴀʙ ᴋɪʏᴀ ᴛʜᴀ?",
    "ᴋᴜᴄʜ ᴀɪꜱᴀ ʙᴀᴛᴀᴏ ᴊᴏ ᴛᴜᴍɴᴇ ᴋɪꜱɪ ᴋᴏ ɴᴀʜɪ ʙᴀᴛᴀʏᴀ~",
    "ɢʀᴏᴜᴘ ᴍᴇɪɴ ᴋɪꜱɪ ᴋᴇ ꜱᴀᴛʜ ᴅᴀᴛᴇ ᴘᴇ ᴊᴀᴀɴᴀ ᴄʜᴀʜᴏɢᴇ?",
    "ᴋᴀʙʜɪ ᴋɪꜱɪ ᴋɪ ᴄᴏᴘʏ ᴋɪ ʜᴀɪ ᴇxᴀᴍ ᴍᴇɪɴ? 😂",
]
DARE_LIST = [
    "ᴀɢʟᴇ ᴍᴇꜱꜱᴀɢᴇ ᴡᴀʟᴇ ᴋᴏ 2 ʟᴀɪɴ ᴋᴀ ᴘᴏᴇᴍ ʟɪᴋʜᴏ 📝",
    "ɢʀᴏᴜᴘ ᴍᴇɪɴ ᴀᴘɴᴀ ʙɪᴏ ʙᴀᴅʟᴏ 💅",
    "ᴠᴏɪᴄᴇ ɴᴏᴛᴇ ɢᴀᴀᴋᴇ ʙʜᴇᴊᴏ 🎵",
    "ᴀɢʟᴇ 10 ᴍɪɴ ᴛᴀᴋ ꜱɪʀꜰ ᴇᴍᴏᴊɪꜱ ᴍᴇɪɴ ʙᴀᴀᴛ ᴋᴀʀᴏ ✨",
    "ᴀᴘɴᴇ ᴄʀᴜꜱʜ ᴋᴏ ᴀʙʜɪ ᴛᴇxᴛ ᴋᴀʀᴏ 👀",
    "ᴀɢʟᴇ 5 ᴍᴇꜱꜱᴀɢᴇ ꜱɪʀꜰ ʀʜʏᴍᴇꜱ ᴍᴇɪɴ ʙʜᴇᴊᴏ!",
]
PUZZLE_LIST = [
    ("ᴍᴀɪ ᴋᴀʙʜɪ ɴᴀʜɪ ɢɪʀᴛᴀ ᴘᴀʀ ʜᴀᴍᴇꜱʜᴀ ɢɪʀᴛᴀ ᴅɪᴋʜᴀɪ ᴅᴇᴛᴀ ʜᴜ. ᴋᴀᴜɴ ʜᴜ?", "ʙᴀʀɪꜱʜ"),
    ("ᴊɪᴛɴᴀ ʟɪʏᴀ ᴜᴛɴᴀ ᴄʜʜᴏᴅᴀ, ᴋʏᴀ ʜ?", "ᴋᴀᴅᴀᴍ"),
    ("ᴍᴀɪ ᴋᴇʏꜱ ʀᴀᴋʜᴛɪ ʜᴜ ʟᴇᴋɪɴ ʟᴏᴄᴋ ɴᴀʜɪ — ᴋʏᴀ ʜᴜ?", "ᴋᴇʏʙᴏᴀʀᴅ"),
    ("ᴊᴏ ʙᴀɴᴛᴀ ʜᴀɪ ʀᴏᴢ, ᴋᴏɪ ɴᴀʜɪ ᴋʜᴀᴛᴀ — ᴋʏᴀ ʜ?", "ꜱᴀᴘɴᴇ"),
    ("ᴊɪᴛɴᴀ ʟᴏ, ᴜᴛɴᴀ ʜɪ ᴘɪᴄʜʜᴇ ᴄʜʜᴏᴅ ᴊᴀᴀᴏ — ᴋʏᴀ ʜ?", "ꜰᴜᴛᴘʀɪɴᴛꜱ"),
]


async def cmd_truth(client, message):
    if not _guard(message.from_user.id if message.from_user else 0):
        return
    await _send(client, message,
                random.choice(TRUTH_LIST), mood=None)


async def cmd_dare(client, message):
    if not _guard(message.from_user.id if message.from_user else 0):
        return
    await _send(client, message,
                random.choice(DARE_LIST), mood=None)


async def cmd_puzzle(client, message):
    q, a = random.choice(PUZZLE_LIST)
    await _send(client, message,
                f"🧠 <b>ʙʀᴀɪɴ ᴛᴇᴀꜱᴇʀ:</b>\n\n{q}\n\n"
                f"<tg-spoiler>ᴀɴꜱᴡᴇʀ: {a}</tg-spoiler>")


# ── Aisha-style extras folded into the fun pack ─────────────────────────────
SHIP_INTROS = ["ᴍᴀᴛᴄʜ ᴍᴀᴅᴇ ɪɴ ʜᴇᴀᴠᴇɴ!", "ᴄᴜᴛᴇ ᴄʜᴇᴍɪꜱᴛʀʏ~", "ʜᴍᴍ... ꜱᴘᴀʀᴋꜱ!"]
VERDICTS = [
    (95, "💍 ᴍᴀʀʀʏ ɴᴏᴡ!!"),
    (75, "💗 ꜱᴛʀᴏɴɢ ᴄʀᴜꜱʜ ᴇɴᴇʀɢʏ"),
    (50, "🌸 ᴄᴜᴛᴇ ꜰʀɪᴇɴᴅꜱ+"),
    (25, "🫧 ʜᴍᴍ... ꜱʟᴏᴡ ꜱᴛᴀʀᴛ"),
    (0,  "🙃 ʙᴇꜱᴛ ᴀꜱ ʀɪᴠᴀʟꜱ"),
]
EIGHTBALL = [
    "ʏᴇꜱ, 100%! ✨", "ɴᴏ. ᴅᴏɴ'ᴛ ᴇᴠᴇɴ. ❌", "ᴀꜱᴋ ᴀɢᴀɪɴ ᴀꜰᴛᴇʀ ᴄʜᴀɪ 🍵",
    "ᴍʏ ꜱᴏᴜʀᴄᴇꜱ ꜱᴀʏ... ᴍᴀʏʙᴇ~ 🌸", "ᴅᴇꜰɪɴɪᴛᴇʟʏ! 💖",
    "ᴏᴜᴛʟᴏᴏᴋ ɴᴏᴛ ꜱᴏ ᴄᴜᴛᴇ 😬", "ɪᴛ ɪꜱ ᴄᴇʀᴛᴀɪɴ 🌟",
    "ᴅᴏɴ'ᴛ ᴄᴏᴜɴᴛ ᴏɴ ɪᴛ 🫧",
]
ROAST_LIST = [
    "ʏᴏᴜ'ʀᴇ ʟɪᴋᴇ ᴀ ᴄʟᴏᴜᴅ — ᴀʟᴡᴀʏꜱ ɪɴ ᴛʜᴇ ᴡᴀʏ ☁️",
    "ɪꜰ ʙʀᴀɪɴꜱ ᴡᴇʀᴇ ɢᴀꜱ, ʏᴏᴜ'ᴅ ʙᴇ ᴀ ᴠᴀᴄᴜᴜᴍ 🫠",
    "ʏᴏᴜ ᴍɪꜱꜱᴇᴅ ᴛʜᴇ ɪQ ʙᴜꜱ ᴀɴᴅ ɪᴛ ᴡᴀꜱɴ'ᴛ ᴇᴠᴇɴ ʟᴀᴛᴇ 🚌",
    "ɢᴏᴏᴅ ᴛʜɪɴɢ ʏᴏᴜ ʜᴀᴠᴇ ɴᴏ ɪᴅᴇᴀ ʜᴏᴡ ᴜɴꜰᴜɴɴʏ ʏᴏᴜ ᴀʀᴇ 🤡",
    "ʏᴏᴜ'ʀᴇ ᴘʀᴏᴏꜰ ᴛʜᴀᴛ ᴅᴜᴍʙ ᴄᴀɴ ꜱᴛɪʟʟ ʙʀᴇᴀᴛʜᴇ 💨",
    "ᴍɪʀʀᴏʀ ɴᴇᴇᴅꜱ ᴀ ʙʀᴇᴀᴋ ᴀꜰᴛᴇʀ ꜱᴇᴇɪɴɢ ʏᴏᴜ 🪞",
]

afk: dict = {}


async def cmd_ship(client, message):
    u = message.from_user
    rm = message.reply_to_message
    if not rm or not rm.from_user or not u:
        await _send_photo_local(
            client, message, _BANNER_PATH,
            notice("ʀᴇᴘʟʏ ᴛᴏ ꜱᴏᴍᴇᴏɴᴇ: /ꜱʜɪᴘ 💕"),
        )
        return
    a, b = u, rm.from_user
    pct = random.randint(0, 100)
    verdict = next(v for min_v, v in VERDICTS if pct >= min_v)
    hearts = ("💖" * max(1, round(pct / 20))
              + "🤍" * (5 - max(1, round(pct / 20))))
    caption = card("💕 ꜱʜɪᴘ ᴍᴀᴄʜɪɴᴇ", [
        f"{_m(a)} × {_m(b)}",
        f"{hearts} <b>{pct}%</b>",
        f"{verdict} ✨",
    ], icon="💕")
    await _send_photo_local(client, message, _BANNER_PATH, caption)


async def cmd_couple(client, message):
    """Standalone couple image (Sep 2026). Works in any chat."""
    await _send_photo_local(
        client, message, _COUPLE_PATH,
        card("💞 ʟᴏᴠᴇ ʙɪʀᴅs", ["💕", "✨"], icon="💞"),
    )


async def cmd_charm(client, message):
    target = message.from_user
    if message.reply_to_message:
        target = message.reply_to_message.from_user
    pct = stable_pct(target.id, "charm")
    label = ("🔥 ʜᴏᴛ ᴍᴇss", "💖 ᴀᴅᴏʀᴀʙʟᴇ", "🌸 ᴄᴜᴛᴇ",
             "🫧 ᴍᴇʜ", "🙃 ɴᴏᴛ ᴛᴏᴅᴀʏ")[min(4, pct // 20)]
    await _send(client, message,
                card("💞 ᴄʜᴀʀᴍ ᴍᴇᴛᴇʀ", [
                    f"{_m(target)}",
                    f"{hearts_bar(pct)} <b>{pct}%</b>",
                    label,
                ], icon="💞"))


async def cmd_8ball(client, message):
    parts = (message.text or "").split(None, 1)
    if len(parts) < 2:
        await _send(client, message,
                    "ℹ️ <b>/8ʙᴀʟʟ <Qᴜᴇꜱᴛɪᴏɴ> 🎱</b>")
        return
    await _send(client, message,
                card("🎱 ᴍᴀɢɪᴄ 8-ʙᴀʟʟ", [random.choice(EIGHTBALL)],
                     icon="🎱"))


async def cmd_roast(client, message):
    target = message.reply_to_message.from_user if message.reply_to_message else message.from_user
    actor = message.from_user
    if target and actor:
        from core.helpers import HARM_OWNER
        from core.owner import is_owner as _is_bot_owner
        if await _is_bot_owner(target.id) and not await _is_bot_owner(actor.id):
            await _send(client, message, HARM_OWNER)
            return
    subject = _m(target) if target else "ʏᴏᴜ"
    await _send(client, message,
                card("🔥 ʀᴏᴀꜱᴛ", [f"{subject}: {random.choice(ROAST_LIST)}"],
                     icon="🔥"))


def _fmt_since(ts: float) -> str:
    secs = int(time.time() - ts)
    h, m = secs // 3600, (secs % 3600) // 60
    return f"{h}ʜ {m}ᴍ" if h else f"{m}ᴍ"


async def cmd_afk(client, message):
    u = message.from_user
    reason = (message.text or "").split(None, 1)
    afk[u.id] = {"since": time.time(),
                 "reason": reason[1] if len(reason) > 1 else "ᴀꜰᴋ"}
    await _send(client, message,
                f"🌙 {_m(u)} ɪꜱ ɴᴏᴡ ᴀꜰᴋ — <i>{afk[u.id]['reason']}</i>")


async def on_maybe_return(client, message):
    """Welcome back anyone who was AFK and speaks again (group 5)."""
    u = message.from_user
    if not u or u.id not in afk or not message.text:
        return
    if (message.text or "").startswith("/"):
        return
    info = afk.pop(u.id)
    try:
        await _send(client, message,
                    f"☀️ ᴡᴇʟᴄᴏᴍᴇ ʙᴀᴄᴋ {_m(u)}! "
                    f"ɢᴏɴᴇ ꜰᴏʀ {_fmt_since(info['since'])} 🌸")
    except Exception:
        pass


# ── Registration ────────────────────────────────────────────────────────────
FUN_GROUP = 6


def register(add, filters, add_cb, **kwargs) -> int:
    n = 0

    def A(fn, names, group=FUN_GROUP):
        nonlocal n
        for nm in names:
            add(fn, filters.command([nm]), group=group)
            n += 1

    # Action commands
    for fn, names in [
        (cmd_slap, ["slap"]), (cmd_punch, ["punch"]), (cmd_kick, ["kick"]),
        (cmd_murder, ["murder", "kill"]), (cmd_kiss, ["kiss"]),
        (cmd_bite, ["bite"]), (cmd_hug, ["hug"]), (cmd_fall, ["fall"]),
        (cmd_throw, ["throw"]), (cmd_highfive, ["highfive"]),
        (cmd_poke, ["poke"]), (cmd_tickle, ["tickle"]),
        (cmd_facepalm, ["facepalm"]), (cmd_pie, ["pie"]),
        (cmd_trip, ["trip"]), (cmd_freeze, ["freeze"]),
        (cmd_zap, ["zap"]), (cmd_dancewith, ["dancewith"]),
        (cmd_pat, ["pat"]), (cmd_cuddle, ["cuddle"]), (cmd_lick, ["lick"]),
        (cmd_bonk, ["bonk"]), (cmd_glare, ["glare"]), (cmd_feed, ["feed"]),
        (cmd_beer, ["beer"]), (cmd_boop, ["boop"]), (cmd_ruffle, ["ruffle"]),
        (cmd_smooch, ["smooch"]), (cmd_tackle, ["tackle"]),
        (cmd_pinch, ["pinch"]), (cmd_fistbump, ["fistbump"]),
        (cmd_bearhug, ["bearhug"]), (cmd_foreheadkiss, ["foreheadkiss"]),
        (cmd_spin, ["spin"]), (cmd_dab, ["dab"]), (cmd_flex, ["flex"]),
        (cmd_nom, ["nom"]), (cmd_squish, ["squish"]), (cmd_yeet, ["yeet"]),
        (cmd_stare, ["stare"]), (cmd_laugh, ["laugh"]),
        (cmd_shoulderpunch, ["shoulderpunch"]),
        (cmd_cheekpinch, ["cheekpinch"]), (cmd_headrub, ["headrub"]),
        (cmd_grouphug, ["grouphug"]), (cmd_suplex, ["suplex"]),
        (cmd_boopboop, ["boopboop"]), (cmd_cheekkiss, ["cheekkiss"]),
        (cmd_headpat, ["headpat"]),
    ]:
        A(fn, names)

    # Self-emotes
    A(cmd_cry, ["cry"])
    A(cmd_blush, ["blush"])
    A(cmd_wave, ["wave"])
    A(cmd_wink, ["wink"])
    A(cmd_dance, ["dance"])
    A(cmd_sleep, ["sleep"])

    # Social / reply-target texts
    A(cmd_simp, ["simp"])
    A(cmd_sus, ["sus"])
    A(cmd_couples, ["couples"])
    A(cmd_crush, ["crush"])
    A(cmd_love, ["love"])
    A(cmd_look, ["look"])
    A(cmd_brain, ["brain"])
    A(cmd_stupid, ["stupid"])

    # Truth / Dare / Puzzle
    A(cmd_truth, ["truth"])
    A(cmd_dare, ["dare"])
    A(cmd_puzzle, ["puzzle"])

    # Aisha-style extras
    A(cmd_ship, ["ship"])
    A(cmd_couple, ["couple"])
    A(cmd_charm, ["charm", "charmrate"])
    A(cmd_8ball, ["8ball"])
    A(cmd_roast, ["roast"])
    A(cmd_afk, ["afk"])

    # AFK welcome-back listener — own group (5) so it never shadows
    # chatbot (2) or game listeners (3/4); pyrogram runs only the first
    # matching handler per group, and this one filters out commands.
    add(on_maybe_return,
        filters.group & filters.text & ~filters.regex(r"^/"), group=5)
    n += 1

    return n
