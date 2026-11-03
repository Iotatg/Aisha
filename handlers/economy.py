# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""Economy: balance, daily streak, pay, leaders, gamble, coinflip, dice.

Every output goes through core/ui so the whole section reads like one
polished product: banners, chips, progress bars and result cards — with
the shared emoji grammar (💰 👥 🔥 ⏳ 🏆 ❗).
"""
import random
from datetime import datetime, timedelta

import config
from core import money, ui
from core.helpers import coins, mention
from core.ui import banner, chip, card, notice


# ── /balance ────────────────────────────────────────────────────────────────

async def cmd_balance(client, message):
    u = message.from_user
    doc = await money.ensure_user(u.id, username=u.username or "",
                                  name=u.first_name)
    xp = doc.get("xp", 0)
    lvl = money.level_for(xp)
    into, need = money.xp_progress(xp)
    text = ui.card(
        "ᴡᴀʟʟᴇᴛ", [
            chip("ᴄᴏɪɴꜱ", coins(doc["balance"]), "💰"),
            chip("ɢᴇᴍꜱ", doc.get("gems", 0), "💎"),
            chip("xᴘ", f"{xp} • ʟᴠʟ {lvl}", "⚡"),
            f"{ui.bar(into, need)} <i>{into}/{need}</i>",
            chip("ꜱᴛʀᴇᴀᴋ", f"{doc.get('daily_streak', 0)} ᴅᴀʏꜱ 🔥"),
        ], icon="👛",
    )
    await message.reply(text)


# ── /pay ────────────────────────────────────────────────────────────────────

async def cmd_pay(client, message):
    u = message.from_user
    parts = (message.text or "").split()
    if len(parts) < 2 or not message.reply_to_message:
        await message.reply(
            ui.card("💗 ꜱᴇɴᴅ ᴄᴏɪɴꜱ", [
                "ʀᴇᴘʟʏ ᴛᴏ ꜱᴏᴍᴇᴏɴᴇ ᴀɴᴅ ᴛʏᴘᴇ:",
                "<code>/pay ᴀᴍᴏᴜɴᴛ</code>",
            ], icon="💗")
        )
        return
    try:
        amount = int(parts[1])
    except ValueError:
        await message.reply(notice("ᴛʜᴀᴛ'ꜱ ɴᴏᴛ ᴀ ᴠᴀʟɪᴅ ᴀᴍᴏᴜɴᴛ!"))
        return
    if amount <= 0:
        await message.reply(notice("ᴀᴍᴏᴜɴᴛ ᴍᴜꜱᴛ ʙᴇ ᴘᴏꜱɪᴛɪᴠᴇ!"))
        return
    target = message.reply_to_message.from_user
    if target.id == u.id:
        await message.reply("🙃 ᴘᴀʏɪɴɢ ʏᴏᴜʀꜱᴇʟꜰ? ᴄᴜᴛᴇ, ʙᴜᴛ ɴᴏ.")
        return
    await money.ensure_user(target.id, username=target.username or "",
                            name=target.first_name)
    if not await money.try_deduct(u.id, amount):
        await message.reply(
            ui.card("💸 ɴᴏᴛ ᴇɴᴏᴜɢʜ!", [
                "<i>ʏᴏᴜʀ ᴘᴏᴄᴋᴇᴛꜱ ᴀʀᴇ ᴇᴍᴘᴛʏ ꜱᴡᴇᴇᴛɪᴇ~</i>",
            ], icon="💸")
        )
        return
    await money.add_balance(target.id, amount)
    await message.reply(
        ui.card("💗 ᴘᴀʏᴍᴇɴᴛ ꜱᴇɴᴛ", [
            chip("ᴀᴍᴏᴜɴᴛ", coins(amount), "💰"),
            chip("ꜰʀᴏᴍ", u.first_name, "📤"),
            chip("ᴛᴏ", target.first_name, "📥"),
        ], icon="💗")
    )


# ── /leaders ────────────────────────────────────────────────────────────────

async def cmd_leaders(client, message):
    cursor = money.users().find().sort("balance", -1).limit(10)
    rows = []
    async for d in cursor:
        uid = d["_id"]
        nm = d.get("name") or str(uid)
        rows.append((mention(uid, ui.truncate(nm)), coins(d["balance"])))
    body = ui.scorecard(
        rows,
        title="💰 ʀɪᴄʜᴇꜱᴛ ꜰʀɪᴇɴᴅꜱ",
    )
    await message.reply(
        body + "\n\n"
        "<i>ᴇᴀʀɴ ᴄᴏɪɴꜱ ᴡɪᴛʜ /daily, /gamble, /bowl, ᴏʀ ʟᴏᴏᴋ ꜰᴏʀ ᴅᴜᴇʟꜱ ⚔️</i>"
    )


# ── /gamble ─────────────────────────────────────────────────────────────────

GAMBLE_WIN_CHANCE = 0.45   # house edge, doubled payout


async def cmd_gamble(client, message):
    u = message.from_user
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.reply(
            ui.card("🎲 ɢᴀᴍʙʟᴇ", [
                chip("ᴡɪɴ", "x2 (45%)", "🟢"),
                chip("ʟᴏꜱᴇ", "ʙᴜꜱᴛ (55%)", "🔴"),
                "ℹ️ <code>/gamble ᴀᴍᴏᴜɴᴛ</code> ᴏʀ <code>/gamble ᴀʟʟ</code>",
            ], icon="🎲")
        )
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
    if not await money.try_deduct(u.id, bet):
        await message.reply(notice("ʏᴏᴜ ᴄᴀɴ'ᴛ ᴀꜰꜰᴏʀᴅ ᴛʜᴀᴛ ʙᴇᴛ!"))
        return
    win = random.random() < GAMBLE_WIN_CHANCE
    if win:
        payout = bet * 2
        await money.add_balance(u.id, payout)
        await money.add_xp(u.id, 10)
        verdict = "🟢 <b>ᴡᴏɴ!</b>"
        line = chip("ᴘᴀʏᴏᴜᴛ", coins(f"+{payout:,}") + " • +10 xᴘ", "💰")
    else:
        verdict = "🔴 <b>ʟᴏꜱᴛ!</b>"
        line = chip("ɢᴏɴᴇ", coins(bet) + " • ɢʟ ɴᴇxᴛ 🍀", "💀")
    await message.reply(
        ui.card("🎰 ꜱʟᴏᴛ ꜰᴇᴠᴇʀ", [
            chip("ʙᴇᴛ", coins(bet), "💰"),
            verdict,
            line,
        ], icon="🎰")
    )


# ── /flipcoin · /dice ───────────────────────────────────────────────────────

async def cmd_flipcoin(client, message):
    cid = message.chat.id
    frames = ["🪙 <i>ᴛᴏssɪɴɢ...</i>", "💫 <i>ꜱᴘɪɴɴɪɴɢ...</i>",
              "🌀 <i>ᴀʟᴍᴏꜱᴛ ᴛʜᴇʀᴇ...</i>"]
    side = random.choice(["ʜᴇᴀᴅꜱ 🌕", "ᴛᴀɪʟꜱ 🌑"])
    final = ui.card("🪙 ᴄᴏɪɴ ꜰʟɪᴘ", [f"ɪᴛ'ꜱ <b>{side}</b>!"], icon="🪙")
    await ui.movie(client, cid, frames, final_text=final, delay=0.5)


async def cmd_dice(client, message):
    """Native Telegram dice animation + Aisha result card."""
    n = random.randint(1, 6)
    faces = ["⚀", "⚁", "⚂", "⚃", "⚄", "⚅"]
    try:
        await client.send_dice(message.chat.id, emoji="🎲")
    except Exception:
        pass
    import asyncio as _aio
    try:
        await _aio.sleep(0.8)
    except Exception:
        pass
    await message.reply(
        ui.card("🎲 ᴅɪᴄᴇ ʀᴏʟʟ", [
            f"ʏᴏᴜ ʀᴏʟʟᴇᴅ <b>{n}</b> {faces[n - 1]} ✨",
        ], icon="🎲")
    )


def register(add, filters, add_cb) -> int:
    add(cmd_balance, filters.command(["balance", "bal"]))
    add(cmd_pay, filters.command(["pay"]))
    add(cmd_leaders, filters.command(["leaders", "rich"]))
    add(cmd_gamble, filters.command(["gamble"]))
    add(cmd_flipcoin, filters.command(["flipcoin", "coin"]))
    add(cmd_dice, filters.command(["dice"]))
    return 6
