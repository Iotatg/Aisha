# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""PvP Duel — challenge someone to a coin dice duel.

Flow (open lobby):
  /duel <bet>           → open a lobby, Aisha waits for one challenger
  tap "👥 ᴊᴏɪɴ"          → both roll native 🎲, higher wins the pot
  ties                    → pot split evenly
One active duel per chat. Self-challenge and bot-challenge blocked.
"""
import asyncio
import random
import time

import config
from core import money
from core.helpers import coins, mention
from core.ui import banner, chip, card, lobby_card, notice

lobbies: dict = {}   # chat_id -> {"host":uid, "bet":int, "msg_id":int,
                     #            "host_name":str, "task":asyncio.Task}


def build_join_kb(bet: int):
    from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("👥 ᴊᴏɪɴ ᴅᴜᴇʟ", callback_data=f"duel_join|{bet}"),
    ]])


async def _close_lobby(client, cid, text):
    rd = lobbies.pop(cid, None)
    if not rd:
        return
    if rd.get("task"):
        rd["task"].cancel()
    try:
        await client.edit_message_text(text, cid, rd["msg_id"])
    except Exception:
        pass


async def _timeout(client, cid):
    await asyncio.sleep(config.DUEL_JOIN_SECS)
    rd = lobbies.get(cid)
    if not rd:
        return
    await _close_lobby(
        client, cid,
        card("⏳ ᴅᴜᴇʟ ᴇxᴘɪʀᴇᴅ", [
            chip("ʙᴇᴛ", coins(rd["bet"]), "💰"),
            "ɴᴏ ʙʀᴀᴠᴇ ꜱᴏᴜʟ ꜱʜᴏᴡᴇᴅ ᴜᴘ~ 🕊️",
        ], icon="⏳")
    )


async def cmd_duel(client, message):
    cid = message.chat.id
    u = message.from_user
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.reply(
            card("👥 ᴅᴜᴇʟ ᴄʜᴀʟʟᴇɴɢᴇ", [
                chip("ʙᴇᴛ", f"{coins(config.MIN_BET)}–{coins(config.MAX_BET)}"),
                f"⏳ {config.DUEL_JOIN_SECS}s ᴛᴏ ᴊᴏɪɴ",
                "ℹ️ /ᴅᴜᴇʟ <ᴀᴍᴏᴜɴᴛ>",
            ], icon="👥")
        )
        return
    try:
        bet = int(parts[1])
    except ValueError:
        await message.reply(notice("ɪɴᴠᴀʟɪᴅ ʙᴇᴛ!"))
        return
    if not (config.MIN_BET <= bet <= config.MAX_BET):
        await message.reply(notice(
            f"ʙᴇᴛ ɢᴏᴇꜱ {config.MIN_BET}–{config.MAX_BET}!"))
        return
    await money.ensure_user(u.id, username=u.username or "",
                            name=u.first_name)
    if not await money.try_deduct(u.id, bet):
        await message.reply(notice("ɴᴏᴛ ᴇɴᴏᴜɢʜ ᴄᴏɪɴꜱ 💸"))
        return

    if cid in lobbies and lobbies[cid].get("task"):
        lobbies[cid]["task"].cancel()
    m = await message.reply(
        lobby_card("👥 ᴅᴜᴇʟ ᴏᴘᴇɴ!", [
            chip("ʜᴏꜱᴛ", mention(u.id, u.first_name), "🎀"),
            chip("ᴘᴏᴛ", coins(bet * 2), "💰"),
            f"⏳ {config.DUEL_JOIN_SECS}s — ᴛᴀᴘ ᴊᴏɪɴ!",
        ], icon="👥"),
        reply_markup=build_join_kb(bet),
    )
    task = asyncio.create_task(_timeout(client, cid))
    lobbies[cid] = {
        "host": u.id, "host_name": u.first_name,
        "bet": bet, "msg_id": getattr(m, "id", None),
        "task": task,
    }


async def on_duel_join(client, query):
    cid = query.message.chat.id
    rd = lobbies.get(cid)
    if not rd:
        try:
            await query.answer("❗ ɴᴏ ᴅᴜᴇʟ ʟᴏʙʙʏ~", show_alert=True)
        except Exception:
            pass
        return
    bet = rd["bet"]
    u = query.from_user
    if u.id == rd["host"]:
        try:
            await query.answer("❗ ʏᴏᴜ ᴄᴀɴ'ᴛ ꜰɪɢʜᴛ ʏᴏᴜʀꜱᴇʟꜰ 🤡",
                               show_alert=True)
        except Exception:
            pass
        return
    await money.ensure_user(u.id, username=u.username or "",
                            name=u.first_name)
    if not await money.try_deduct(u.id, bet):
        try:
            await query.answer("💸 ɴᴏᴛ ᴇɴᴏᴜɢʜ ᴄᴏɪɴꜱ!", show_alert=True)
        except Exception:
            pass
        return

    # both roll native 🎲 — server-fair
    try:
        h = await client.send_dice(cid, emoji="🎲")
        hv = getattr(getattr(h, "dice", None), "value", random.randint(1, 6))
    except Exception:
        hv = random.randint(1, 6)
    try:
        c = await client.send_dice(cid, emoji="🎲")
        cv = getattr(getattr(c, "dice", None), "value", random.randint(1, 6))
    except Exception:
        cv = random.randint(1, 6)

    await asyncio.sleep(1.2)
    pot = bet * 2
    if hv == cv:
        half = pot // 2
        await money.add_balance(rd["host"], half)
        await money.add_balance(u.id, pot - half)
        result = card("🤝 ᴅᴜᴇʟ ᴛɪᴇ!", [
            chip("ʜᴏꜱᴛ", f"{rd['host_name']} 🎲 {hv}", "🎀"),
            chip("ᴄʜᴀʟʟᴇɴɢᴇʀ", f"{u.first_name} 🎲 {cv}", "👥"),
            chip("ᴇᴀᴄʜ ɢᴇᴛꜱ", coins(half) + f" (+{pot - half - half})", "💰"),
        ], icon="🤝")
    else:
        winner_id, wname, wv = (rd["host"], rd["host_name"], hv) \
            if hv > cv else (u.id, u.first_name, cv)
        await money.add_balance(winner_id, pot)
        await money.add_xp(winner_id, config.DUEL_WIN_XP)
        loser = u.first_name if winner_id != u.id else rd["host_name"]
        lv = cv if winner_id != u.id else hv
        result = card("🏆 ᴅᴜᴇʟ ᴡᴏɴ!", [
            chip("ᴡɪɴɴᴇʀ", mention(winner_id, wname) + f" 🎲 {wv}", "🏆"),
            chip("ʟᴏꜱᴇʀ", f"{loser} 🎲 {lv}", "💀"),
            chip("ᴘᴏᴛ ᴡᴏɴ", coins(pot) + f" • +{config.DUEL_WIN_XP} xᴘ",
                 "💰"),
        ], icon="🏆")

    lobbies.pop(cid, None)
    try:
        await query.answer("🎲 ʀᴏʟʟ ᴅᴏɴᴇ!", show_alert=False)
    except Exception:
        pass
    try:
        await query.message.edit_text(result, reply_markup=None)
    except Exception:
        pass


def register(add, filters, add_cb) -> int:
    add(cmd_duel, filters.command(["duel"]))
    add_cb(on_duel_join, filters.regex(r"^duel_join\|"))
    return 2
