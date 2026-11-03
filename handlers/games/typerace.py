# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""Typing Race — first to type the sentence wins; solo speed mode too."""
import random
import time

import config
from core import money
from core.helpers import coins, mention
from core.ui import card, chip, notice

SENTENCES = [
    "ꜱᴏꜰᴛ ʀᴏꜱᴇꜱ ʙʟᴏssᴏᴍ ɪɴ ᴛʜᴇ ɢᴇɴᴛʟᴇ ᴍᴏʀɴɪɴɢ ꜱᴜɴ",
    "ᴄᴜᴘᴄᴀᴋᴇꜱ ᴀɴᴅ ʀᴀɪɴʙᴏᴡꜱ ᴍᴀᴋᴇ ᴇᴠᴇʀʏᴏɴᴇ ꜱᴍɪʟᴇ",
    "ᴛʜᴇ Qᴜɪᴄᴋ ʙʀᴏᴡɴ ꜰᴏx ᴊᴜᴍᴘꜱ ᴏᴠᴇʀ ᴛʜᴇ ʟᴀᴢʏ ᴅᴏɢ",
    "ᴍᴏᴏɴʟɪɢʜᴛ ᴅᴀɴᴄᴇꜱ ᴏɴ ᴛʜᴇ Qᴜɪᴇᴛ ᴏᴄᴇᴀɴ ᴡᴀᴠᴇs",
    "ʟɪᴛᴛʟᴇ ꜱᴛᴀʀꜱ ᴛᴡɪɴᴋʟᴇ ɪɴ ᴛʜᴇ ᴘᴜʀᴘʟᴇ ɴɪɢʜᴛ ꜱᴋʏ",
    "ʙᴜᴛᴛᴇʀғʟɪᴇꜱ ᴡʜɪꜱᴘᴇʀ ꜱᴇᴄʀᴇᴛs ᴛᴏ ᴛʜᴇ ꜰʟᴏᴡᴇʀꜱ",
]

# chat_id -> {"text": str, "started": float, "done": set}
races: dict = {}


async def cmd_typerace(client, message):
    cid = message.chat.id
    race = races.get(cid)
    if race and time.time() - race["started"] < config.TYPERACE_SECONDS:
        remaining = int(config.TYPERACE_SECONDS -
                        (time.time() - race["started"]))
        await message.reply(notice(f"🏃 ᴀ ʀᴀᴄᴇ ɪꜱ ᴏɴ! {remaining}s ʟᴇꜰᴛ!"))
        return
    text = random.choice(SENTENCES)
    races[cid] = {"text": text, "norm": text.casefold(),
                  "started": time.time(), "done": {}}
    await message.reply(
        card("🏃‍♀️ ᴛʏᴘɪɴɢ ʀᴀᴄᴇ!", [
            f"⏱️ {config.TYPERACE_SECONDS}s",
            f"➤ <b>{text}</b>",
            f"ᴊᴜꜱᴛ ᴛʏᴘᴇ ɪᴛ! ꜰᴀꜱᴛᴇꜱᴛ ᴡɪɴꜱ {coins(config.TYPERACE_REWARD)} 💨",
        ], icon="🏃‍♀️")
    )


def accuracy(typed: str, target: str) -> float:
    """Character-level similarity, 0..1."""
    if not target:
        return 0.0
    typed, target = typed.strip().lower(), target.lower()
    same = sum(1 for a, b in zip(typed, target) if a == b)
    return same / max(len(target), len(typed))


async def on_race_message(client, message):
    cid = message.chat.id
    race = races.get(cid)
    if not race or not message.text:
        return
    u = message.from_user
    if not u or message.text.startswith("/"):
        return
    if u.id in race["done"]:
        return
    if time.time() - race["started"] > config.TYPERACE_SECONDS:
        races.pop(cid, None)
        return
    if message.text.strip().casefold() != race["norm"]:
        return   # silent — wrong typing doesn't spam

    elapsed = time.time() - race["started"]
    place = len(race["done"]) + 1
    race["done"][u.id] = elapsed
    payout = {1: config.TYPERACE_REWARD,
              2: config.TYPERACE_REWARD // 2}.get(place,
                                                  config.TYPERACE_REWARD // 4)
    await money.ensure_user(u.id, username=u.username or "",
                            name=u.first_name)
    await money.add_balance(u.id, payout)
    await money.add_xp(u.id, 20)
    place_str = {1: "1ꜱᴛ", 2: "2ɴᴅ", 3: "3ʀᴅ"}.get(place, f"{place}ᴛʜ")
    try:
        await message.reply(
            card("💨 ʀᴀᴄᴇ ꜰɪɴɪꜱʜ!", [
                f"👤 {mention(u.id, u.first_name)} "
                f"ꜰɪɴɪꜱʜᴇᴅ {place_str} ɪɴ <b>{elapsed:.1f}s</b>!",
                chip("ᴘʀɪᴢᴇ", f"+{payout} ᴄᴏɪɴꜱ • +20 xᴘ", "💰"),
            ], icon="💨")
        )
    except Exception:
        pass


async def cmd_racestop(client, message):
    cid = message.chat.id
    if races.pop(cid, None) is not None:
        await message.reply(card("🛑 ʀᴀᴄᴇ ꜱᴛᴏᴘᴘᴇᴅ", ["🌸"], icon="🛑"))
    else:
        await message.reply("🫧 ɴᴏ ʀᴀᴄᴇ ʀᴜɴɴɪɴɢ.")


def register(add, filters, add_cb) -> int:
    add(cmd_typerace, filters.command(["typerace"]))
    add(cmd_racestop, filters.command(["racestop"]))
    # OWN handler group (4) so it never shadows chatbot (2) or other
    # group-1 listeners — pyrogram runs only the first match per group.
    add(on_race_message, filters.group & filters.text &
        ~filters.command(["typerace", "racestop", "start", "help",
                          "wordchain", "chainend"]), group=4)
    return 3
