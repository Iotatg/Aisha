# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""Shared building blocks for Aisha's group-lobby → DM-play games.

Every game (bingo, ttt, duel, …) follows the same shape the users expect
from the reference bots:

  • a game is opened with a command inside a GROUP
  • the bot posts a lobby card with a Join button + a "📩 Check Dm" button
  • once enough players join, the bot posts
      "🎲 <GAME> ʜᴀꜱ ꜱᴛᴀʀᴛᴇᴅ! … Check your DMs to play!"
    and pushes the actual play surface into each player's private chat
  • the "📩 Check Dm" button just deep-links the user to the bot's DM so the
    pushed messages are visible

This module keeps the small repeated pieces (deep-link url, the button, the
"check your dm" line, the lobby keyboard) in one place so every game stays
consistent.
"""
import config

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def dm_url(game: str) -> str:
    """Deep link that opens the bot's DM (optionally with a start payload)."""
    return f"https://t.me/{config.BOT_USERNAME}?start={game}"


def dm_button(game: str, text: str = "📩 Check Dm") -> InlineKeyboardButton:
    return InlineKeyboardButton(text, url=dm_url(game))


def check_dm_line() -> str:
    return "ᴄʜᴇᴄɪ ʏᴏᴜʀ Dᴍꜱ ᴛᴏ ᴘʟᴀʏ!"


def lobby_markup(join_cb: str, game: str,
                 extra: list[InlineKeyboardButton] | None = None) -> InlineKeyboardMarkup:
    """Standard lobby keyboard: Join (callback) + 📩 Check Dm (deep link).

    ``join_cb`` is the full callback_data for the join button, e.g.
    ``f"bingo_join|{chat_id}"``. ``extra`` lets a game append a host Start
    button or similar.
    """
    row = [InlineKeyboardButton("🎮 ᴊᴏɪɴ", callback_data=join_cb), dm_button(game)]
    if extra:
        row.extend(extra)
    return InlineKeyboardMarkup([row])
