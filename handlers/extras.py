# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""Girly extras — compliments. The rest of the fun/social pack
(ship, charm, 8ball, afk, roast, action & truth/dare games) now lives
in handlers/fun.py. This module keeps the standalone /compliment command only.
"""
import random

from core.helpers import mention

COMPLIMENTS = [
    "ʏᴏᴜʀ ꜱᴍɪʟᴇ ʟɪᴛᴇʀᴀʟʟʏ ᴍᴀᴋᴇꜱ ɢʀᴏᴜᴘꜱ ʙʀɪɢʜᴛᴇʀ ✨",
    "ʏᴏᴜ'ʀᴇ ᴛʜᴇ ʜᴜᴍᴀɴ ᴠᴇʀꜱɪᴏɴ ᴏꜰ ᴀ ᴡᴏʀᴍ ᴄᴏᴍᴘʟɪᴍᴇɴᴛ 🌷",
    "ʏᴏᴜʀ ᴠɪʙᴇ? ᴘʀɪᴄᴇʟᴇss. 💎",
    "ʏᴏᴜ ᴍᴀᴋᴇ ʙᴀsɪᴄ ᴅᴀʏꜱ ʟᴏᴏᴋ ɢᴏᴏᴅ 💖",
    "ᴛᴀʟᴇɴᴛ, ᴄʜᴀʀᴍ, ᴀɴᴅ ɢʀᴇᴀᴛ ᴛᴀꜱᴛᴇ — ʏᴏᴜ ʜᴀᴠᴇ ɪᴛ ᴀʟʟ 🌸",
    "ᴇᴠᴇɴ ꜱᴜɴꜰʟᴏᴡᴇʀꜱ ᴊᴇᴀʟᴏᴜꜱ ᴏꜰ ʏᴏᴜʀ ɢʟᴏᴡ 🌻",
    "ʏᴏᴜ'ʀᴇ ᴛʜᴇ ᴘʟᴏᴛ ᴛᴡɪꜱᴛ ᴇᴠᴇʀʏᴏɴᴇ ɴᴇᴇᴅᴇᴅ 💫",
    "10/10 ᴡᴏᴜʟᴅ ꜱʜᴀʀᴇ ᴍʏ ᴅessert ᴡɪᴛʜ ʏᴏᴜ 🧁",
]


async def cmd_compliment(client, message):
    target = message.reply_to_message.from_user if message.reply_to_message else None
    if target:
        text = (f"💌 {mention(target.id, target.first_name)}, "
                f"{random.choice(COMPLIMENTS)}")
    else:
        text = f"💌 {random.choice(COMPLIMENTS)}"
    await message.reply(text)


def register(add, filters, add_cb, **kwargs) -> int:
    add(cmd_compliment, filters.command(["compliment"]))
    return 1
