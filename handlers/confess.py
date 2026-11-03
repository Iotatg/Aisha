# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""Anonymous confessions: /confess <text> posts as the bot in the group,
attributed to 'ᴀɴᴏɴʏᴍᴏᴜꜱ' so the author stays hidden."""
import logging

from core.helpers import is_group
from core.fonts import smallcaps as _sc

logger = logging.getLogger(__name__)


def register(add, filters, add_cb):
    add(cmd_confess, filters.command("confess"))


async def cmd_confess(client, message):
    if not is_group(message.chat):
        await message.reply("🤫 ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ ᴏɴʟʏ ᴡᴏʀɪꜱ ɪɴ ɢʀᴏᴜᴘꜱ!")
        return
    parts = message.text.split(maxsplit=1)
    text = parts[1].strip() if len(parts) > 1 else ""
    if not text:
        await message.reply(f"🤫 <b>{_sc('confess')}</b>\n\n"
                             f"{_sc('use')}: /confess <your secret>")
        return
    await message.delete()
    await client.send_message(
        message.chat.id,
        f"🤫 <b>{_sc('anonymous confession')}</b>\n\n{text}",
    )
