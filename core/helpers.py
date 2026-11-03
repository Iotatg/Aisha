# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""Shared helpers: mentions, money formatting, small UI pieces."""
from html import escape

from pyrogram.enums import ChatType as _ChatType


def fmt(amount) -> str:
    """Comma-grouped integer, e.g. 1234567 -> '1,234,567'."""
    try:
        return f"{int(amount):,}"
    except (TypeError, ValueError):
        return str(amount)


def is_group(chat) -> bool:
    """True for normal groups and supergroups (Pyrogram 2.x uses the
    ChatType enum, so never compare chat.type to a plain string)."""
    return chat.type in (_ChatType.GROUP, _ChatType.SUPERGROUP)


def is_private(chat) -> bool:
    return chat.type == _ChatType.PRIVATE


def mention(uid, name) -> str:
    return f'<a href="tg://user?id={uid}">{escape(str(name))}</a>'


def coins(amount) -> str:
    if isinstance(amount, str):
        return f"🪙 {amount}"
    return f"🪙 {amount:,}"


def gems(amount) -> str:
    return f"💎 {amount:,}"


# Permission refusals, kept here so every handler spells them the same way.
OWNER_ONLY = "🧏‍♂️ Sʜʜ… Tʜᴀᴛ'ꜱ Mʏ Oᴡɴᴇʀ 😏"
ADMIN_ONLY = "❗ Oɴʟʏ Gʀᴏᴜᴘ Aᴅᴍɪɴꜱ Cᴀɴ Uꜱᴇ Tʜɪꜱ Cᴏᴍᴍᴀɴᴅ !"
HARM_OWNER = "😏 Sʜʜ… Dᴏɴ'ᴛ Tᴏᴜᴄʜ, Tʜᴀᴛ'ꜱ Mʏ Oᴡɴᴇʀ"
NOT_YOURS = "😏 Oᴏᴘs… Tʜᴀᴛ Cᴏᴍᴍᴀɴᴅ Iꜱ Nᴏᴛ Yᴏᴜʀꜱ ⚠️"
NOT_ON_LIST = "😂 Nɪᴄᴇ Tʀʏ… Bᴜᴛ Yᴏᴜ'ʀᴇ Nᴏᴛ Oɴ Tʜᴇ Lɪꜱᴛ 😭"
