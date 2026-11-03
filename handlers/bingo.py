# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""Bingo — group lobby → DM play, with 📩 Check Dm deep-link button.

Flow (matches the reference-bot UX the users expect):
  /bingo <amount> [max|all]   → opens a lobby card in the GROUP with a
                                 Join button + 📩 Check Dm button
  players tap Join             → entry fee deducted, lobby updates
  game starts (cap reached or host taps Start)
                               → group posts "🎲 ʙɪɴɢᴏ ʜᴀꜱ ꜱᴛᴀʀᴛᴇᴅ! …
                                 Check your DMs to play!" and the bot pushes a
                                 5×5 card into every player's DM
  bot calls numbers on a timer → each player's DM card re-marks ✅
  a player taps 🎲 ʙɪɴɢᴏ in DM  → first valid bingo wins the pooled entry fees

/r still shows your bingo profile. Small-caps strings are hand-written.
"""
import asyncio
import logging
import random

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from core.db import db
from core.helpers import fmt, mention, is_group
from core.lobby import dm_button, check_dm_line
from core.ui import scorecard, truncate
from handlers.kingdom import _get_village, _upd

logger = logging.getLogger(__name__)

CALL_INTERVAL = 4          # seconds between called numbers
MIN_PLAYERS = 2
MAX_NUMBERS = 75
LOBBY_SECONDS = 120        # auto-cancel if not enough players join in time

# chat_id -> asyncio.Task running the number-caller loop (so we can cancel it)
ACTIVE_CALLS: dict[int, asyncio.Task] = {}
# chat_id -> asyncio.Task for the lobby auto-cancel timer
LOBBY_TIMERS: dict[int, asyncio.Task] = {}


async def _vault_deduct(uid: int, amt: int) -> bool:
    v = await _get_village(uid)
    if v.get("vault", 0) < amt:
        return False
    await _upd(uid, vault=v["vault"] - amt)
    return True


async def _vault_add(uid: int, amt: int) -> None:
    v = await _get_village(uid)
    await _upd(uid, vault=v.get("vault", 0) + amt)


async def _lobby_expire(client, chat_id):
    await asyncio.sleep(LOBBY_SECONDS)
    g = await _coll().find_one({"_id": chat_id})
    if not g or g.get("status") != "lobby":
        return
    for p in g["players"]:
        await _vault_add(p, g["bet"])
    await _coll().update_one({"_id": chat_id}, {"$set": {"status": "done"}})
    try:
        await client.send_message(
            chat_id,
            f"❗️ ʙɪɴɢᴏ ᴄᴀɴᴄᴇʟʟᴇᴅ!\n"
            f"ɴᴏ ᴇɴᴏᴜɢʜ ᴘʟᴀʏᴇʀɢ ᴊᴏɪɴᴇᴅ ɪɴ 2 ᴍɪɴꜱ. ꜰᴇᴇꜱ ʀᴇꜰᴜɴᴅᴇᴅ.",
        )
    except Exception:
        pass


def _arm_lobby_timer(client, chat_id):
    if chat_id in LOBBY_TIMERS:
        LOBBY_TIMERS.pop(chat_id).cancel()
    LOBBY_TIMERS[chat_id] = asyncio.create_task(_lobby_expire(client, chat_id))


def _coll():
    return db().bingo_games


def _lb_coll():
    return db().bingo_lb


def _card():
    nums = random.sample(range(1, 76), 24)
    grid = []
    for i in range(25):
        grid.append(0 if i == 12 else nums.pop(0))   # 0 = FREE center
    return grid


def _has_bingo(card, drawn):
    marked = [c in drawn or c == 0 for c in card]
    for i in range(5):
        if all(marked[i * 5 + j] for j in range(5)):
            return True
        if all(marked[j * 5 + i] for j in range(5)):
            return True
    if all(marked[i * 6] for i in range(5)):
        return True
    if all(marked[i * 4 + 4] for i in range(5)):
        return True
    return False


def _card_text(card, drawn, bet, last=None):
    lines = []
    for r in range(5):
        row = []
        for c in range(5):
            v = card[r * 5 + c]
            if v == 0:
                row.append("🟢")
            elif v in drawn:
                row.append("✅")
            else:
                row.append(f"{v:02d}")
        lines.append(" ".join(row))
    grid = "\n".join(lines)
    last_line = f"🎯 ʟᴀꜱᴛ ᴄᴀʟʟᴇᴅ: {last}" if last is not None else "⏳ ᴡᴀɪᴛɪɴɢ ꜰᴏʀ ᴛʜᴇ ꜰɪʀꜱᴛ ɴᴜᴍʙᴇʀ…"
    return (
        f"🃏 <b>ʏᴏᴜʀ ʙɪɴɢᴏ ᴄᴀʀᴅ</b> — ᴇɴᴛʀʏ ${fmt(bet)}\n\n"
        f"{grid}\n\n{last_line}\n"
        f"ᴛᴀᴘ 🎲 ʙɪɴɢᴏ ᴡʜᴇɴ ʏᴏᴜ ʜᴀᴠᴇ ᴀ ʟɪɴᴇ!"
    )


async def _lb_update(uid, name, won_amount, win):
    lb = await _lb_coll().find_one({"_id": uid}) or {"_id": uid, "name": name,
                                                      "won": 0, "lost": 0,
                                                      "amt_won": 0, "amt_lost": 0, "streak": 0}
    lb["name"] = name
    if win:
        lb["won"] += 1
        lb["amt_won"] += won_amount
        lb["streak"] += 1
    else:
        lb["lost"] += 1
        lb["amt_lost"] += won_amount
        lb["streak"] = 0
    await _lb_coll().update_one({"_id": uid}, {"$set": lb}, upsert=True)


async def cmd_bingo(client, message):
    chat = message.chat
    if not is_group(chat):
        await message.reply("❗️ ᴘʟᴇᴀꜱᴇ ᴜꜱᴇ /bingo ᴄᴏᴍᴍᴀɴᴅ ɪɴ ᴀ ɢʀᴏᴜᴘ!")
        return
    u = message.from_user
    args = message.command[1:] if len(getattr(message, "command", []) or []) > 1 else []
    if not args:
        await message.reply("❌ ᴜꜱᴀɢᴇ: /bingo <amount> [max|all]")
        return
    try:
        amount = int(args[0])
    except Exception:
        await message.reply("❌ ɪɴᴠᴀʟɪᴅ ᴀᴍᴏᴜɴᴛ!")
        return
    if amount <= 0:
        await message.reply("❌ ᴡᴀɢᴇʀ ᴍᴜꜱᴛ ʙᴇ ᴘᴏꜱɪᴛɪᴠᴇ!")
        return

    cap = 2
    if len(args) > 1:
        if args[1].lower() == "all":
            cap = None
        else:
            try:
                cap = int(args[1])
            except Exception:
                await message.reply("❌ ɪɴᴠᴀʟɪᴅ ᴍᴀx ᴘʟᴀʏᴇʀꜱ!")
                return
    if cap is not None and cap < 2:
        cap = 2

    if not await _vault_deduct(u.id, amount):
        await message.reply(f"❌ ʏᴏᴜ ɴᴇᴇᴅ {fmt(amount)} ᴠᴀᴜʟᴛ ᴄᴏɪɴɢ!")
        return

    await _coll().update_one(
        {"_id": chat.id},
        {"$set": {
            "bet": amount, "cap": cap, "players": [u.id],
            "names": {str(u.id): u.first_name or "ᴘʟᴀʏᴇʀ"},
            "status": "lobby", "drawn": [], "cards": {}, "dm": {}, "pool": amount,
        }},
        upsert=True,
    )
    await _send_lobby(client, chat.id, u.id)
    _arm_lobby_timer(client, chat.id)


async def _lobby_text(g):
    names = [g["names"].get(str(p), "ᴘʟᴀʏᴇʀ") for p in g["players"]]
    joined = ", ".join(names) if names else "—"
    cap = g["cap"] or "∞"
    return (
        f"🎮 ʙɪɴɢᴏ ʟᴏʙʙʏ ꜱᴛᴀʀᴛᴇᴅ! 🎮\n\n"
        f"👑 ʜᴏꜱᴛ: {names[0] if names else '—'}\n"
        f"💰 ᴇɴᴛʀʏ ꜰᴇᴇ: {fmt(g['bet'])} ᴄᴏɪɴꜱ\n"
        f"👥 ᴍᴀx ᴘʟᴀʏᴇʀꜱ: {cap}\n"
        f"✅ ᴊᴏɪɴᴇᴅ: {joined} ({len(g['players'])}/{cap})\n\n"
        f"ᴛᴀᴘ ᴛʜᴇ ᴊᴏɪɴ ʙᴜᴛᴛᴏɴ ʙᴇʟᴏᴡ ᴀɴᴅ ꜱᴛᴀʀᴛ ᴛʜᴇ ʙᴏᴛ ɪɴ Dᴍ ᴛᴏ ᴇɴᴛᴇʀ ᴛʜᴇ ɢᴀᴍᴇ!"
    )


async def _send_lobby(client, chat_id, host_id):
    g = await _coll().find_one({"_id": chat_id})
    if not g:
        return
    extra = []
    if g["players"][0] == host_id and len(g["players"]) >= MIN_PLAYERS:
        extra = [InlineKeyboardButton("▶️ ꜱᴛᴀʀᴛ", callback_data=f"bingo_start|{chat_id}")]
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🎮 ᴊᴏɪɴ", callback_data=f"bingo_join|{chat_id}"),
        dm_button("bingo"),
    ] + extra])
    await client.send_message(chat_id, await _lobby_text(g), reply_markup=kb)


async def bingo_join(client, cb):
    q = cb
    await q.answer()
    chat_id = int(q.data.split("|")[1])
    g = await _coll().find_one({"_id": chat_id})
    if not g or g.get("status") != "lobby":
        return
    uid = q.from_user.id
    if uid in g["players"]:
        await q.answer("ʏᴏᴜ'ʀᴇ ᴀʟʀᴇᴀᴅʏ ɪɴ!", show_alert=True)
        return
    if g["cap"] and len(g["players"]) >= g["cap"]:
        await q.answer("ʟᴏʙʙʏ ɪꜱ ꜰᴜʟʟ!", show_alert=True)
        return
    if not await _vault_deduct(uid, g["bet"]):
        await q.answer(f"ʏᴏᴜ ɴᴇᴇᴅ {fmt(g['bet'])} ᴠᴀᴜʟᴛ ᴄᴏɪɴɢ!", show_alert=True)
        return
    g["players"].append(uid)
    g["names"][str(uid)] = q.from_user.first_name or "ᴘʟᴀʏᴇʀ"
    g["pool"] += g["bet"]
    await _coll().update_one({"_id": chat_id}, {"$set": {
        "players": g["players"], "names": g["names"], "pool": g["pool"]}})
    await _send_lobby(client, chat_id, g["players"][0])
    await _try_start(client, chat_id)


async def bingo_start(client, cb):
    q = cb
    await q.answer()
    chat_id = int(q.data.split("|")[1])
    g = await _coll().find_one({"_id": chat_id})
    if not g or g.get("status") != "lobby":
        return
    if q.from_user.id != g["players"][0]:
        await q.answer("ᴏɴʟʏ ᴛʜᴇ ʜᴏꜱᴛ ᴄᴀɴ ꜱᴛᴀʀᴛ!", show_alert=True)
        return
    await _try_start(client, chat_id, force=True)


async def _try_start(client, chat_id, force=False):
    g = await _coll().find_one({"_id": chat_id})
    if not g or g.get("status") != "lobby":
        return
    if len(g["players"]) < MIN_PLAYERS:
        return
    cap_reached = g["cap"] and len(g["players"]) >= g["cap"]
    if not (force or cap_reached or g["cap"] == 2):
        return
    await _deal_and_start(client, chat_id)


async def _deal_and_start(client, chat_id):
    if chat_id in LOBBY_TIMERS:
        LOBBY_TIMERS.pop(chat_id).cancel()
    g = await _coll().find_one({"_id": chat_id})
    names = [g["names"].get(str(p), "ᴘʟᴀʏᴇʀ") for p in g["players"]]
    cards = {}
    for p in g["players"]:
        cards[str(p)] = _card()
    order = list(range(1, MAX_NUMBERS + 1))
    random.shuffle(order)
    await _coll().update_one({"_id": chat_id}, {"$set": {
        "status": "playing", "cards": cards, "order": order,
        "drawn": [], "dm": {}, "pool": g["bet"] * len(g["players"]),
    }})
    await client.send_message(
        chat_id,
        f"🎲 ʙɪɴɢᴏ ʜᴀꜱ ꜱᴛᴀʀᴛᴇᴅ!\n"
        f"👥 ᴘʟᴀʏᴇʀꜱ: {', '.join(names)}\n\n"
        f"{check_dm_line()}",
        reply_markup=InlineKeyboardMarkup([[dm_button("bingo")]]),
    )
    for p in g["players"]:
        sent = await client.send_message(
            p, _card_text(cards[str(p)], set(), g["bet"]),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🎲 ʙɪɴɢᴏ", callback_data=f"bingo_claim|{chat_id}")]]),
        )
        g.setdefault("dm", {})[str(p)] = sent.id
    await _coll().update_one({"_id": chat_id}, {"$set": {"dm": g["dm"]}})
    task = asyncio.create_task(_run_calls(client, chat_id))
    ACTIVE_CALLS[chat_id] = task


async def _edit_card(client, chat_id, uid, g, last):
    msg_id = g.get("dm", {}).get(str(uid))
    if not msg_id:
        return
    try:
        await client.edit_message_text(
            uid, msg_id, _card_text(g["cards"][str(uid)], set(g["drawn"]), g["bet"], last),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🎲 ʙɪɴɢᴏ", callback_data=f"bingo_claim|{chat_id}")]]),
        )
    except Exception:
        pass


async def _run_calls(client, chat_id):
    try:
        while True:
            g = await _coll().find_one({"_id": chat_id})
            if not g or g.get("status") != "playing":
                return
            order = g.get("order") or []
            drawn = g.get("drawn") or []
            if len(drawn) >= len(order):
                await _end_no_bingo(client, chat_id, g)
                return
            nxt = order[len(drawn)]
            drawn.append(nxt)
            await _coll().update_one({"_id": chat_id}, {"$set": {"drawn": drawn}})
            await client.send_message(chat_id, f"🎯 ɴᴜᴍʙᴇʀ {nxt} ᴄᴀʟʟᴇᴅ!")
            for p in g["players"]:
                await _edit_card(client, chat_id, p, g, nxt)
            await asyncio.sleep(CALL_INTERVAL)
    except asyncio.CancelledError:
        return


async def _finish_bingo(client, chat_id, winner_uid, g=None):
    g = g or await _coll().find_one({"_id": chat_id})
    if not g or g.get("status") != "playing":
        return
    if chat_id in ACTIVE_CALLS:
        ACTIVE_CALLS.pop(chat_id).cancel()
    pool = g["bet"] * len(g["players"])
    w_name = g["names"].get(str(winner_uid), "ᴘʟᴀʏᴇʀ")
    await _vault_add(winner_uid, pool)
    await _lb_update(winner_uid, w_name, pool - g["bet"], True)
    for p in g["players"]:
        if p != winner_uid:
            await _lb_update(p, g["names"].get(str(p), "ᴘʟᴀʏᴇʀ"), g["bet"], False)
    await _coll().update_one({"_id": chat_id}, {"$set": {"status": "done"}})
    names = [g["names"].get(str(p), "ᴘʟᴀʏᴇʀ") for p in g["players"]]
    await client.send_message(
        chat_id,
        f"🎊 ʙɪɴɢᴏ ᴄᴏᴍᴘʟᴇᴛᴇᴅ! 🎊\n"
        f"🏆 ᴡɪɴɴᴇʀ: {w_name}\n"
        f"💰 ᴘʀɪᴢᴇ ᴡᴏɴ: {fmt(pool)} ᴄᴏɪɴꜱ\n"
        f"👥 ᴘʟᴀʏᴇʀꜱ: {', '.join(names)}",
    )
    for p in g["players"]:
        msg_id = g.get("dm", {}).get(str(p))
        if not msg_id:
            continue
        txt = (f"🏆 ʏᴏᴜ ᴡᴏɴ {fmt(pool)} ᴄᴏɪɴꜱ!" if p == winner_uid
               else f"💔 {w_name} ɢᴏᴛ ᴛʜᴇ ʙɪɴɢᴏ. ʏᴏᴜ ʟᴏꜱᴛ {fmt(g['bet'])}.")
        try:
            await client.edit_message_text(p, msg_id, f"{txt}\n\n💡 ᴛʏᴘᴇ /bingo ᴛᴏ ꜱᴛᴀʀᴛ ᴀ ɴᴇᴡ ɢᴀᴍᴇ!")
        except Exception:
            pass


async def bingo_claim(client, cb):
    q = cb
    await q.answer()
    chat_id = int(q.data.split("|")[1])
    g = await _coll().find_one({"_id": chat_id})
    if not g or g.get("status") != "playing":
        return
    uid = q.from_user.id
    if uid not in g["players"]:
        await q.answer("ʏᴏᴜ'ʀᴇ ɴᴏᴛ ɪɴ ᴛʜɪꜱ ɢᴀᴍᴇ!", show_alert=True)
        return
    if not _has_bingo(g["cards"][str(uid)], set(g.get("drawn") or [])):
        await q.answer("ɴᴏ ʙɪɴɢᴏ ʏᴇᴛ! ᴄʜᴇᴄɪ ʏᴏᴜʀ ᴄᴀʀᴅ 😅", show_alert=True)
        return
    await _finish_bingo(client, chat_id, uid, g)


async def _end_no_bingo(client, chat_id, g):
    if chat_id in ACTIVE_CALLS:
        ACTIVE_CALLS.pop(chat_id).cancel()
    for p in g["players"]:
        await _vault_add(p, g["bet"])   # entry refunded
        await _lb_update(p, g["names"].get(str(p), "ᴘʟᴀʏᴇʀ"), 0, False)
    await _coll().update_one({"_id": chat_id}, {"$set": {"status": "done"}})
    await client.send_message(
        chat_id,
        f"🎲 ᴀʟʟ {MAX_NUMBERS} ɴᴜᴍʙᴇʀꜱ ᴄᴀʟʟᴇᴅ — ɴᴏ ʙɪɴɢᴏ!\n"
        f"💸 ᴇᴠᴇʀʏᴏɴᴇ'ꜱ ᴇɴᴛʀʏ ꜰᴇᴇ ({fmt(g['bet'])}) ʀᴇꜰᴜɴᴅᴇᴅ.",
    )


async def bingo_cancel(client, cb):
    q = cb
    await q.answer()
    chat_id = int(q.data.split("|")[1])
    g = await _coll().find_one({"_id": chat_id})
    if not g or g.get("status") != "lobby":
        return
    if q.from_user.id != g["players"][0]:
        await q.answer("ᴏɴʟʏ ᴛʜᴇ ʜᴏꜱᴛ ᴄᴀɴ ᴄᴀɴᴄᴇʟ!", show_alert=True)
        return
    if chat_id in ACTIVE_CALLS:
        ACTIVE_CALLS.pop(chat_id).cancel()
    if chat_id in LOBBY_TIMERS:
        LOBBY_TIMERS.pop(chat_id).cancel()
    for p in g["players"]:
        await _vault_add(p, g["bet"])
    await _coll().update_one({"_id": chat_id}, {"$set": {"status": "done"}})
    await client.send_message(chat_id, "🛑 ʙɪɴɢᴏ ᴄᴀɴᴄᴇʟʟᴇᴅ. ᴇɴᴛʀʏ ꜰᴇᴇꜱ ʀᴇꜰᴜɴᴅᴇᴅ.")


async def _bingo_rank_text(u):
    lb = await _lb_coll().find_one({"_id": u.id}) or {
        "name": u.first_name or "ᴘʟᴀʏᴇʀ", "won": 0, "lost": 0,
        "amt_won": 0, "amt_lost": 0, "streak": 0}
    net = lb.get("amt_won", 0) - lb.get("amt_lost", 0)
    pipeline = [{"$match": {}}, {"$addFields": {"net": {"$subtract": ["$amt_won", "$amt_lost"]}}},
                {"$match": {"net": {"$gt": net}}}, {"$count": "rank"}]
    res = await _lb_coll().aggregate(pipeline).to_list(1)
    rank = (res[0]["rank"] + 1) if res else 1
    return (
        f"🃏 <b>ʙɪɴɢᴏ ʀᴀɴᴋ</b>\n\n"
        f"👤 {mention(u.id, lb.get('name') or 'ᴘʟᴀʏᴇʀ')}\n"
        f"👉 ᴡɪɴꜱ: {lb.get('won', 0)} || ʟᴏꜱꜱᴇꜱ: {lb.get('lost', 0)}\n"
        f"💰 ᴀᴍᴏᴜɴᴛ ᴡᴏɴ: ${fmt(lb.get('amt_won', 0))}\n"
        f"💸 ᴀᴍᴏᴜɴᴛ ʟᴏꜱꜱ: ${fmt(lb.get('amt_lost', 0))}\n"
        f"🔥 ꜱᴛʀᴇᴀɪ: {lb.get('streak', 0)} / {lb.get('streak', 0)}\n"
        f"🎖️ ʀᴀɴᴋ: #{rank}"
    )


async def _ttt_lb_text():
    rows = await db().ttt_lb.find().sort("total", -1).limit(10).to_list(10)
    if not rows:
        return "⚡ Tɪᴄ Tᴀᴄ Tᴏᴇ Lᴇᴀᴅᴇʀʙᴏᴀʀᴅ ⚡\n\n🏆 ɴᴏ ʀᴀɴɪᴇᴅ ʏᴇᴛ — ʙᴇ ᴛʜᴇ ꜰɪʀꜱᴛ!"
    data = []
    for r in rows:
        uid = r["_id"]
        nm = r.get("name") or "ᴘʟᴀʏᴇʀ"
        data.append((mention(uid, truncate(nm)), f"${fmt(r.get('total', 0))}"))
    return scorecard(data, "⚡ Tɪᴄ Tᴀᴄ Tᴏᴇ Lᴇᴀᴅᴇʀʙᴏᴀʀᴅ")


def _rank_kb(view: str):
    if view == "bingo":
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("⚡ Tɪᴄ Tᴀᴄ Tᴏᴇ", callback_data="rank_ttt")]])
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🃏 Bɪɴɢᴏ", callback_data="rank_bingo")]])


async def cmd_bingorank(client, message):
    u = message.from_user
    await message.reply(await _bingo_rank_text(u), reply_markup=_rank_kb("bingo"))


async def rank_ttt_cb(client, cb):
    await cb.answer()
    try:
        await cb.edit_message_text(await _ttt_lb_text(), reply_markup=_rank_kb("ttt"))
    except Exception as e:
        logger.warning("rank_ttt edit failed: %s", e)


async def rank_bingo_cb(client, cb):
    await cb.answer()
    try:
        await cb.edit_message_text(await _bingo_rank_text(cb.from_user),
                                   reply_markup=_rank_kb("bingo"))
    except Exception as e:
        logger.warning("rank_bingo edit failed: %s", e)


def register(add, filters, add_cb, **kwargs) -> int:
    n = 0
    add(cmd_bingo, filters.command(["bingo"]), group=0); n += 1
    add(cmd_bingorank, filters.command(["r"]), group=0); n += 1
    add_cb(bingo_join, filters.regex(r"^bingo_join\|")); n += 1
    add_cb(bingo_start, filters.regex(r"^bingo_start\|")); n += 1
    add_cb(bingo_claim, filters.regex(r"^bingo_claim\|")); n += 1
    add_cb(bingo_cancel, filters.regex(r"^bingo_cancel\|")); n += 1
    add_cb(rank_ttt_cb, filters.regex(r"^rank_ttt$")); n += 1
    add_cb(rank_bingo_cb, filters.regex(r"^rank_bingo$")); n += 1
    return n
