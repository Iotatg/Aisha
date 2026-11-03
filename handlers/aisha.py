# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""Per-group aisha on/off toggle + global game-command gate.

Admins can disable aisha's games in their group with ``/aisha off`` and
re-enable with ``/aisha on``. The status is persisted in the
``group_settings`` collection and applied to every game command via a
pre-handler at group ``-10`` so the message is intercepted before any
game handler runs.

Non-game commands (start, balance, daily, pay, leaders, profile, social
actions, chatbot, reactions, …) are unaffected — only the curated
``GAME_COMMANDS`` list is gated.
"""
import asyncio
import logging
import time

from pyrogram.enums import ChatType

from core import ui
from core.db import db as get_db

logger = logging.getLogger(__name__)


# Every command that should be blocked when aisha is ``off`` in a group.
# Keep this list explicit; do NOT gate economy/profile/social commands.
GAME_COMMANDS = (
    # Real-time multiplayer
    "ttt", "tttrank", "lb",
    "bingo", "r",        # /r is the bingo-rank alias
    "typerace", "racestop",
    "wordchain", "chainend",
    "trivia",
    "luckybox",
    "duel",
    "kingdom", "village", "guide", "collect", "storage", "vault", "mines",
    "build", "walls", "defense", "train", "troops", "spy", "attack",
    "emperors", "settle", "convert", "market",
    "wallet", "shield", "raid", "quests",
    # Arcade (casino-style)
    "dicebet", "diceg", "dart", "basket", "ball", "foot", "football",
    "bowl", "bowling",
    # Casino/economy mini-games
    "gamble", "flipcoin", "coin", "dice",
)

# Per-group toggle cache: {chat_id: (enabled: bool, expires_at: float)}.
_cache: dict[int, tuple[bool, float]] = {}
_CACHE_TTL = 5.0  # seconds


async def is_aisha_enabled(chat_id: int) -> bool:
    """Return whether aisha games are enabled in ``chat_id`` (default True)."""
    now = time.monotonic()
    hit = _cache.get(chat_id)
    if hit and hit[1] > now:
        return hit[0]
    try:
        doc = await get_db().group_settings.find_one({"_id": chat_id})
    except Exception as e:
        logger.debug("is_aisha_enabled: db lookup failed: %s", e)
        return True  # fail open — never break the bot for a settings hiccup
    enabled = True
    if doc:
        enabled = bool(doc.get("aisha_enabled", True))
    _cache[chat_id] = (enabled, now + _CACHE_TTL)
    return enabled


async def set_aisha_enabled(chat_id: int, enabled: bool) -> None:
    """Persist the per-group toggle and invalidate the cache."""
    _cache.pop(chat_id, None)
    await get_db().group_settings.update_one(
        {"_id": chat_id},
        {"$set": {"aisha_enabled": enabled, "chat_id": chat_id}},
        upsert=True,
    )


async def _is_group_admin(client, chat_id: int, user_id: int) -> bool:
    try:
        member = await client.get_chat_member(chat_id, user_id)
    except Exception as e:
        logger.debug("get_chat_member failed for %s in %s: %s", user_id, chat_id, e)
        return False
    status = getattr(member, "status", None)
    return status in ("creator", "administrator")


# ── /aisha command ──────────────────────────────────────────────────────────

USAGE = "ᴜꜱᴀɢᴇ: /aisha on ᴏʀ /aisha off"


async def cmd_aisha(client, message):
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.reply(ui.notice(USAGE))
        return

    arg = parts[1].lower()
    if arg not in ("on", "off", "status"):
        await message.reply(ui.notice(USAGE))
        return

    chat = message.chat
    u = message.from_user
    if chat.type == ChatType.PRIVATE:
        await message.reply(
            ui.notice("ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ ɪꜱ ᴏɴʟʏ ꜰᴏʀ ɢʀᴏᴜᴘꜱ.")
        )
        return

    if arg == "status":
        enabled = await is_aisha_enabled(chat.id)
        flag = "🟢 ᴇɴᴀʙʟᴇ" if enabled else "🔴 ᴅɪꜱᴀʙʟᴇ"
        await message.reply(
            ui.notice(f"ᴀɪꜱʜᴀ ɢᴀᴍᴇ ꜱʏꜱᴛᴇᴍ ɪꜱ ɴᴏᴡ {flag} ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ.")
        )
        return

    if not await _is_group_admin(client, chat.id, u.id):
        await message.reply(
            ui.notice("ᴏɴʟʏ ɢʀᴏᴜᴘ ᴀᴅᴍɪɴꜱ ᴄᴀɴ ᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ.")
        )
        return

    enabled = arg == "on"
    await set_aisha_enabled(chat.id, enabled)
    flag = "🟢 ᴇɴᴀʙʟᴇ" if enabled else "🔴 ᴅɪꜱᴀʙʟᴇ"
    await message.reply(
        ui.notice(
            f"ᴀɪꜱʜᴀ ɢᴀᴍᴇ ꜱʏꜱᴛᴇᴍ ɪꜱ ɴᴏᴡ {flag} ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ."
        )
    )


# ── Pre-handler gate ────────────────────────────────────────────────────────

GATE_NOTICE = (
    "ᴀɪꜱʜᴀ ɢᴀᴍᴇ ꜱʏꜱᴛᴇᴍ ɪꜱ ɴᴏᴡ 🔴 ᴅɪꜱᴀʙʟᴇ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ. "
    "ᴀᴅᴍɪɴꜱ ᴄᴀɴ ʀᴇ-ᴇɴᴀʙʟᴇ ᴡɪᴛʜ /aisha on."
)


async def game_gate(client, message):
    """Block game commands in groups where aisha is disabled.

    Runs at group ``-10`` (before every other handler) so the disabled
    notice wins over game logic. Uses ``continue_propagation`` to let
    non-game commands (start, daily, balance, …) pass through.
    """
    if not message.text:
        return
    text = message.text.split()[0] if message.text else ""
    if not text.startswith("/"):
        return
    cmd = text[1:].split("@")[0].lower()
    if cmd not in GAME_COMMANDS:
        return

    if message.chat.type == ChatType.PRIVATE:
        return  # games always work in DM

    if await is_aisha_enabled(message.chat.id):
        return

    try:
        await message.reply(ui.notice(GATE_NOTICE))
    except Exception as e:
        logger.debug("game_gate: reply failed: %s", e)
    try:
        message.stop_propagation()
    except Exception:
        pass


# ── Registration ────────────────────────────────────────────────────────────

def register(add, filters, add_cb, **kwargs) -> int:
    # The toggle command itself is always available.
    add(cmd_aisha, filters.command(["aisha"]))
    # The pre-handler runs at group=-10 so it short-circuits any game
    # command before the game-specific handler can react.
    game_filter = filters.group & filters.command(list(GAME_COMMANDS))
    add(game_gate, game_filter, group=-10)
    return 2
