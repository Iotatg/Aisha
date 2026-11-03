# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""Dice Arcade — native Telegram dice animations + coin bets.

Telegram renders the dice itself (server-side
fair, can't be rigged), then Aisha rolls the outcome against a simple
threshold and pays the pot. Five flavours, one engine:

  /dicebet <bet>  🎲  value 4-6 wins
  /dart <bet>     🎯  6 = jackpot, 4-5 win
  /basket <bet>   🏀  4-5 = swish (win), 5 jackpot
  /foot <bet>     ⚽  goal on 3-5
  /bowl <bet>     🎳  6 = strike jackpot
"""
import asyncio
import random
import time

import config
from core import money
from core.helpers import coins, mention
from core.ui import banner, chip, card, notice

# emoji -> (threshold>=, win_mult, jackpot_value, jackpot_mult)
GAMES = {
    "dicebet": ("🎲", 4, 2.0, None, 0.0),
    "dart":     ("🎯", 4, 1.8, 6, 3.0),
    "basket":   ("🏀", 4, 1.8, 5, 3.0),
    "foot":     ("⚽", 3, 1.9, 5, 3.0),
    "bowl":     ("🎳", 4, 1.8, 6, 3.0),
}

_cd: dict = {}  # uid -> last play epoch


async def _play(client, message, key: str):
    u = message.from_user
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.reply(
            card(f"{GAMES[key][0]} {key.upper()}", [
                chip("ʙᴇᴛ", f"{coins(config.MIN_BET)}–{coins(config.MAX_BET)}", "💰"),
                "ℹ️ " + f"<code>/{key} ᴀᴍᴏᴜɴᴛ</code>",
            ], icon=GAMES[key][0])
        )
        return

    now = time.time()
    if now - _cd.get(u.id, 0.0) < config.DICEBET_COOLDOWN:
        await message.reply(notice("ᴄᴀʟᴍ ᴅᴏᴡɴ ʙᴀʙᴇ — ᴡᴀɪᴛ ᴀ ꜱᴇᴄ 💤"))
        return

    try:
        bet = int(parts[1])
    except ValueError:
        if parts[1].lower() in ("all", "max"):
            doc = await money.get_user(u.id)
            bet = doc["balance"] if doc else 0
        else:
            bet = -1
    if bet <= 0:
        await message.reply(notice("ʙᴇᴛ ᴍᴜꜱᴛ ʙᴇ ᴘᴏꜱɪᴛɪᴠᴇ!"))
        return
    if not (config.MIN_BET <= bet <= config.MAX_BET):
        await message.reply(notice(
            f"ʙᴇᴛ ɢᴏᴇꜱ {config.MIN_BET}–{config.MAX_BET}!"))
        return
    if not await money.try_deduct(u.id, bet):
        await message.reply(notice("ɴᴏᴛ ᴇɴᴏᴜɢʜ ᴄᴏɪɴꜱ 💸"))
        return

    _cd[u.id] = now
    emoji, thr, wmult, jval, jmult = GAMES[key]
    try:
        sent = await client.send_dice(message.chat.id, emoji=emoji)
        value = getattr(getattr(sent, "dice", None), "value", None)
    except Exception:
        value = random.randint(1, 6)

    await money.ensure_user(u.id, username=u.username or "",
                            name=u.first_name)
    try:
        await asyncio.sleep(1.2)
    except Exception:
        pass

    if value is None:
        value = random.randint(1, 6)

    jackpot = (jval is not None and value == jval)
    win = jackpot or value >= thr
    if win:
        mult = jmult if jackpot else wmult
        payout = int(bet * mult)
        await money.add_balance(u.id, payout)
        await money.add_xp(u.id, config.DICEBET_WIN_XP)
        title = "ᴊᴀᴄᴋᴘᴏᴛ!" if jackpot else "ᴡᴏɴ!"
        icon = "🥳" if jackpot else "🟢"
        line = chip("ᴘᴀʏᴏᴜᴛ", coins(f"+{payout:,}") + f" • x{mult} • "
                    f"+{config.DICEBET_WIN_XP} xᴘ", "💰")
        verdict = f"{icon} <b>{title}</b>"
    else:
        title = "ʙᴜꜱᴛ!"
        line = chip("ɢᴏɴᴇ", coins(bet) + " • ɢʟ ɴᴇxᴛ 🍀", "💀")
        verdict = "🔴 <b>ʟᴏꜱᴛ!</b>"

    await message.reply(
        card(f"{emoji} {key.upper()} ʀᴏʟʟ", [
            chip("ʏᴏᴜ ʀᴏʟʟᴇᴅ", str(value), emoji),
            verdict,
            line,
        ], icon=emoji)
    )


async def cmd_dicebet(client, message): await _play(client, message, "dicebet")
async def cmd_dart(client, message):     await _play(client, message, "dart")
async def cmd_basket(client, message):   await _play(client, message, "basket")
async def cmd_foot(client, message):      await _play(client, message, "foot")
async def cmd_bowl(client, message):      await _play(client, message, "bowl")


def register(add, filters, add_cb) -> int:
    add(cmd_dicebet, filters.command(["dicebet", "diceg"]))
    add(cmd_dart,    filters.command(["dart"]))
    add(cmd_basket,  filters.command(["basket", "ball"]))
    add(cmd_foot,    filters.command(["foot", "football"]))
    add(cmd_bowl,    filters.command(["bowl", "bowling"]))
    return 5
