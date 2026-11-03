# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""Emoji helper: /emoji <word> -> matching emoji, /emoji -> random emoji,
/emoji <sentence> -> translates known words into emoji."""
import logging
import re

from core.fonts import emoji_for, random_emoji, EMOJI_WORDS, smallcaps as _sc

logger = logging.getLogger(__name__)


def register(add, filters, add_cb):
    add(cmd_emoji, filters.command("emoji"))


async def cmd_emoji(client, message):
    parts = message.text.split(maxsplit=1)
    text = parts[1].strip() if len(parts) > 1 else ""
    if not text:
        await message.reply(f"{random_emoji()} <b>{_sc('random emoji')}</b>\n\n"
                             f"{_sc('use')}: /emoji <word>")
        return
    words = re.findall(r"[a-z]+", text.lower())
    found = [emoji_for(w) for w in words if emoji_for(w)]
    if found:
        await message.reply(f"{''.join(found)}  <i>({', '.join(w for w in words if emoji_for(w))})</i>")
        return
    await message.reply(f"{random_emoji()}  <i>{_sc('no match, here is a random one')}</i>")
