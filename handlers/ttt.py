# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""Tic-Tac-Toe with coins + global leaderboard — group lobby → DM play.

/ttt <amount> opens (or joins) a 2-player match in the GROUP; once two
players are in, the board is pushed into each player's DM (with a 📩 Check Dm
deep-link in the group). Moves are tapped inline in DM; a 60s turn timer
auto-awards the round to the opponent on timeout. Winner takes both wagers.
/lb shows the leaderboard. Small-caps strings are hand-written.
"""
import asyncio
import logging

from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from core.db import db
from core.helpers import fmt, mention, is_group
from core.ui import scorecard, truncate
from core.lobby import dm_button, check_dm_line
from handlers.kingdom import _get_village, _upd

logger = logging.getLogger(__name__)

WIN_LINES = [
    (0, 1, 2), (3, 4, 5), (6, 7, 8),
    (0, 3, 6), (1, 4, 7), (2, 5, 8),
    (0, 4, 8), (2, 4, 6),
]
TURN_SECONDS = 60
MIN_WAGER = 10

ACTIVE_TIMERS: dict[int, asyncio.Task] = {}


async def _vault_deduct(uid: int, amt: int) -> bool:
    v = await _get_village(uid)
    if v.get("vault", 0) < amt:
        return False
    await _upd(uid, vault=v["vault"] - amt)
    return True


async def _vault_add(uid: int, amt: int) -> None:
    v = await _get_village(uid)
    await _upd(uid, vault=v.get("vault", 0) + amt)


def _coll():
    return db().ttt_games


def _lb_coll():
    return db().ttt_lb


def _board_text(board, amount):
    rows = []
    for r in range(3):
        rows.append(" | ".join(board[r * 3 + c] for c in range(3)))
    grid = "\n─────────\n".join(rows)
    return f"⚡ ᴛɪᴄ ᴛᴀᴄ ᴛᴏᴇ — ᴡᴀɢᴇʀ: ${fmt(amount)}\n\n{grid}"


def _board_kb(board, chat_id):
    kb = []
    for r in range(3):
        row = []
        for c in range(3):
            pos = r * 3 + c
            label = board[pos] if board[pos] != " " else str(pos + 1)
            row.append(InlineKeyboardButton(label, callback_data=f"ttt_{chat_id}_{pos}"))
        kb.append(row)
    return InlineKeyboardMarkup(kb)


def _winner(board):
    for a, b, c in WIN_LINES:
        if board[a] != " " and board[a] == board[b] == board[c]:
            return board[a]
    return None


async def _lb_update(uid, name, delta, won):
    lb = await _lb_coll().find_one({"_id": uid})
    if not lb:
        lb = {"_id": uid, "name": name, "total": 0, "wins": 0, "losses": 0,
              "amt_won": 0, "amt_lost": 0, "streak": 0}
    lb["name"] = name
    lb["total"] = lb.get("total", 0) + delta
    if won:
        lb["wins"] = lb.get("wins", 0) + 1
        lb["amt_won"] = lb.get("amt_won", 0) + delta
        lb["streak"] = lb.get("streak", 0) + 1
    elif delta < 0:
        lb["losses"] = lb.get("losses", 0) + 1
        lb["amt_lost"] = lb.get("amt_lost", 0) + (-delta)
        lb["streak"] = 0
    await _lb_coll().update_one({"_id": uid}, {"$set": lb}, upsert=True)


async def cmd_ttt(client, message):
    chat = message.chat
    if not is_group(chat):
        await message.reply("⚠️ ᴛʜɪꜱ ɢᴀᴍᴇ ᴄᴀɴ ᴏɴʟʏ ʙᴇ ᴘʟᴀʏᴇᴅ ɪɴ ɢʀᴏᴜᴘꜱ.")
        return
    u = message.from_user
    args = message.command[1:] if len(getattr(message, "command", []) or []) > 1 else []
    if not args:
        await message.reply("❌ ᴜꜱᴀɢᴇ: /ttt <amount> — ᴏᴘᴇɴ ᴏʀ ᴊᴏɪɴ ᴀ ɢᴀᴍᴇ.")
        return
    try:
        amount = int(args[0])
    except Exception:
        await message.reply("❌ ɪɴᴠᴀʟɪᴅ ᴀᴍᴏᴜɴᴛ!")
        return
    if amount < MIN_WAGER:
        await message.reply(f"⚠️ ᴍɪɴɪᴍᴜᴍ ᴇɴᴛʀʏ ꜰᴇᴇ ɪꜱ {MIN_WAGER} ᴠᴀᴜʟᴛ ᴄᴏɪɴɢ.")
        return
    g = await _coll().find_one({"_id": chat.id})
    if g and g.get("status") == "playing":
        await message.reply("❌ ᴀ ɢᴀᴍᴇ ɪꜱ ᴀʟʀᴇᴀᴅʏ ɪɴ ᴘʀᴏɢʀᴇꜱꜱ ʜᴇʀᴇ.")
        return
    if g and g.get("status") == "lobby" and u.id not in g["players"]:
        # JOIN
        if not await _vault_deduct(u.id, amount):
            await message.reply(f"❌ ɴᴏᴛ ᴇɴᴏᴜɢʜ ᴠᴀᴜʟᴛ ᴄᴏɪɴɢ ᴛᴏ ᴊᴏɪɴ ({fmt(amount)})!")
            return
        players = [g["players"][0], u.id]
        names = g["names"]
        names[str(u.id)] = u.first_name or "ᴘʟᴀʏᴇʀ"
        await _coll().update_one({"_id": chat.id}, {"$set": {
            "players": players, "names": names, "marks": {str(players[0]): "❌", str(players[1]): "⭕"},
            "turn": players[0], "board": [" "] * 9, "status": "playing", "dm": {}}})
        await _start_match(client, chat.id)
        return
    if g and u.id in g.get("players", []):
        await message.reply("❌ ʏᴏᴜ'ʀᴇ ᴀʟʀᴇᴀᴅʏ ɪɴ ᴛʜɪꜱ ɢᴀᴍᴇ!")
        return

    # OPEN a new challenge
    if not await _vault_deduct(u.id, amount):
        await message.reply(f"❌ ɴᴏᴛ ᴇɴᴏᴜɢʜ ᴠᴀᴜʟᴛ ᴄᴏɪɴɢ ({fmt(amount)})!")
        return
    await _coll().update_one({"_id": chat.id}, {"$set": {
        "amount": amount, "players": [u.id],
        "names": {str(u.id): u.first_name or "ᴘʟᴀʏᴇʀ"},
        "marks": {}, "turn": None, "board": [" "] * 9, "status": "lobby", "dm": {},
    }}, upsert=True)
    name = u.first_name or "ᴘʟᴀʏᴇʀ"
    await client.send_message(
        chat.id,
        f"🎮 ᴛɪᴄ ᴛᴀᴄ ᴛᴏᴇ ᴍᴀᴛᴄʜ 🎮\n\n"
        f"💰 ᴡᴀɢᴇʀ: ${fmt(amount)}\n"
        f"👤 {mention(u.id, name)} ɪꜱ ʀᴇᴀᴅʏ!\n"
        f"👉 ꜱᴏᴍᴇᴏɴᴇ ᴇʟꜱᴇ ᴛʏᴘᴇ /ttt ᴛᴏ ᴊᴏɪɴ ᴡɪᴛʜ ${fmt(amount)}.",
        reply_markup=InlineKeyboardMarkup([[dm_button("ttt")]]),
    )


async def _start_match(client, chat_id):
    g = await _coll().find_one({"_id": chat_id})
    names = [g["names"].get(str(p), "ᴘʟᴀʏᴇʀ") for p in g["players"]]
    await client.send_message(
        chat_id,
        f"🎮 ᴛɪᴄ ᴛᴀᴄ ᴛᴏᴇ ᴍᴀᴛᴄʜ 🎮\n\n"
        f"❌ {mention(g['players'][0], names[0])} VS ⭕️ {mention(g['players'][1], names[1])}\n"
        f"💰 ᴘʀɪᴢᴇ ᴘᴏᴏʟ: {fmt(g['amount'] * 2)} ᴄᴏɪɴꜱ\n\n"
        f"👉 ᴛᴜʀɴ: {names[0]} (❌)\n"
        f"⏳ ʏᴏᴜ ʜᴀᴠᴇ {TURN_SECONDS} ꜱᴇᴄᴏɴᴅꜱ ᴛᴏ ᴍᴏᴠᴇ!\n\n"
        f"{check_dm_line()}",
        reply_markup=InlineKeyboardMarkup([[dm_button("ttt")]]),
    )
    dm = {}
    for p in g["players"]:
        sent = await client.send_message(p, _board_text(g["board"], g["amount"]),
                                          reply_markup=_board_kb(g["board"], chat_id))
        dm[str(p)] = sent.id
    await _coll().update_one({"_id": chat_id}, {"$set": {"dm": dm}})
    _arm_timer(client, chat_id, g["players"][0])


def _arm_timer(client, chat_id, uid):
    if chat_id in ACTIVE_TIMERS:
        ACTIVE_TIMERS[chat_id].cancel()
    ACTIVE_TIMERS[chat_id] = asyncio.create_task(_turn_timeout(client, chat_id, uid))


async def _turn_timeout(client, chat_id, uid):
    await asyncio.sleep(TURN_SECONDS)
    g = await _coll().find_one({"_id": chat_id})
    if not g or g.get("status") != "playing" or g.get("turn") != uid:
        return
    players = g["players"]
    winner = players[1] if uid == players[0] else players[0]
    await _finish(client, chat_id, winner, timeout=True)


async def ttt_callback(client, callback):
    q = callback
    await q.answer()
    parts = q.data.split("_")
    if len(parts) < 3:
        return
    chat_id = int(parts[1])
    pos = int(parts[2])
    g = await _coll().find_one({"_id": chat_id})
    if not g or g.get("status") != "playing":
        return
    uid = q.from_user.id
    players = g["players"]
    if uid not in players:
        await q.answer("ʏᴏᴜ'ʀᴇ ɴᴏᴛ ɪɴ ᴛʜɪꜱ ɢᴀᴍᴇ!", show_alert=True)
        return
    if g.get("turn") != uid:
        await q.answer("ɴᴏᴛ ʏᴏᴜʀ ᴛᴜʀɴ!", show_alert=True)
        return
    board = g["board"]
    if board[pos] != " ":
        await q.answer("ᴄᴇʟʟ ᴛᴀɪᴇɴ!", show_alert=True)
        return
    board[pos] = g["marks"][str(uid)]
    winner = _winner(board)
    full = " " not in board
    if winner or full:
        w_uid = players[0] if g["marks"][str(players[0])] == winner else (players[1] if winner else None)
        await _finish(client, chat_id, w_uid, draw=not winner)
        return
    nxt = players[1] if uid == players[0] else players[0]
    await _coll().update_one({"_id": chat_id}, {"$set": {"board": board, "turn": nxt}})
    await _push_boards(client, chat_id, board, g["amount"], nxt)
    _arm_timer(client, chat_id, nxt)


async def _push_boards(client, chat_id, board, amount, turn_uid):
    g = await _coll().find_one({"_id": chat_id})
    for p in g["players"]:
        msg_id = g.get("dm", {}).get(str(p))
        if not msg_id:
            continue
        try:
            await client.edit_message_text(p, msg_id, _board_text(board, amount),
                                            reply_markup=_board_kb(board, chat_id))
        except Exception:
            pass
    names = [g["names"].get(str(p), "ᴘʟᴀʏᴇʀ") for p in g["players"]]
    cur = g["names"].get(str(turn_uid), "ᴘʟᴀʏᴇʀ")
    mark = g["marks"].get(str(turn_uid), "")
    await client.send_message(
        chat_id,
        f"👉 ᴛᴜʀɴ: {cur} ({mark})\n⏳ {TURN_SECONDS} ꜱᴇᴄ ᴛᴏ ᴍᴏᴠᴇ!",
    )


async def _finish(client, chat_id, winner_uid, draw=False, timeout=False):
    if chat_id in ACTIVE_TIMERS:
        ACTIVE_TIMERS.pop(chat_id).cancel()
    g = await _coll().find_one({"_id": chat_id})
    if not g or g.get("status") != "playing":
        return
    players = g["players"]
    amount = g["amount"]
    await _coll().update_one({"_id": chat_id}, {"$set": {"status": "done"}})
    if draw:
        for p in players:
            await _vault_add(p, amount)
            await _lb_update(p, g["names"].get(str(p), "ᴘʟᴀʏᴇʀ"), 0, False)
        text = (f"🎮 ᴛɪᴄ ᴛᴀᴄ ᴛᴏᴇ ᴍᴀᴛᴄʜ ᴅʀᴀᴡ 🎮\n\n"
                f"❗️ {mention(players[0], g['names'].get(str(players[0]), 'ᴘʟᴀʏᴇʀ'))} "
                f"VS ⭕️ {mention(players[1], g['names'].get(str(players[1]), 'ᴘʟᴀʏᴇʀ'))}\n\n"
                f"❓ ʀᴇꜱᴜʟᴛ: ɪᴛ'ꜱ ᴀ ᴛɪᴇ! ʙᴏᴛʜ ᴘʟᴀʏᴇʀꜱ ʀᴇᴄᴇɪᴠᴇᴅ ᴛʜᴇɪʀ ᴇɴᴛʀʏ ꜰᴇᴇ ʙᴀᴄɪ.")
    else:
        w_name = g["names"].get(str(winner_uid), "ᴘʟᴀʏᴇʀ")
        l_uid = players[1] if winner_uid == players[0] else players[0]
        await _vault_add(winner_uid, amount * 2)
        await _lb_update(winner_uid, w_name, amount, True)
        await _lb_update(l_uid, g["names"].get(str(l_uid), "ᴘʟᴀʏᴇʀ"), -amount, False)
        reason = " ⏰ (ᴛɪᴍᴇᴏᴜᴛ)" if timeout else ""
        text = (
            f"🏆 <b>{mention(winner_uid, w_name)} ᴡɪɴꜱ!</b>{reason}\n\n"
            f"💰 +${fmt(amount)}  |  💸 -${fmt(amount)} ꜰᴏʀ {mention(l_uid, g['names'].get(str(l_uid), 'ᴘʟᴀʏᴇʀ'))}"
        )
    await client.send_message(chat_id, text)
    for p in players:
        msg_id = g.get("dm", {}).get(str(p))
        if not msg_id:
            continue
        try:
            await client.edit_message_text(p, msg_id, f"🏁 ɢᴀᴍᴇ ᴏᴠᴇʀ!\n\n{text}\n\n💡 ᴛʏᴘᴇ /ttt ᴛᴏ ᴘʟᴀʏ ᴀɢᴀɪɴ.")
        except Exception:
            pass


async def cmd_lb(client, message):
    rows = await _lb_coll().find().sort("total", -1).limit(10).to_list(10)
    if not rows:
        await message.reply("🏆 ɴᴏ ʀᴀɴɪᴇᴅ ʏᴇᴛ — ʙᴇ ᴛʜᴇ ꜰɪʀꜱᴛ!")
        return
    data = []
    for r in rows:
        uid = r["_id"]
        nm = r.get("name") or "ᴘʟᴀʏᴇʀ"
        data.append((mention(uid, truncate(nm)), f"${fmt(r.get('total', 0))}"))
    await message.reply(scorecard(data, "🏆 Tɪᴄ Tᴀᴄ Tᴏᴇ Lᴇᴀᴅᴇʀʙᴏᴀʀᴅ"))


async def _ttt_rank_text(u):
    lb = await _lb_coll().find_one({"_id": u.id}) or {
        "name": u.first_name or "ᴘʟᴀʏᴇʀ", "total": 0, "wins": 0, "losses": 0,
        "amt_won": 0, "amt_lost": 0, "streak": 0}
    net = lb.get("amt_won", 0) - lb.get("amt_lost", 0)
    pipeline = [{"$match": {}}, {"$addFields": {"net": {"$subtract": ["$amt_won", "$amt_lost"]}}},
                {"$match": {"net": {"$gt": net}}}, {"$count": "rank"}]
    res = await _lb_coll().aggregate(pipeline).to_list(1)
    rank = (res[0]["rank"] + 1) if res else 1
    return (
        f"🎮 <b>ᴛɪᴄ ᴛᴀᴄ ᴛᴏᴇ ʀᴀɴɪ</b>\n\n"
        f"👤 {mention(u.id, lb.get('name') or 'ᴘʟᴀʏᴇʀ')}\n"
        f"👉 ᴡɪɴꜱ: {lb.get('wins', 0)} || ʟᴏꜱꜱᴇꜱ: {lb.get('losses', 0)}\n"
        f"💰 ᴀᴍᴏᴜɴᴛ ᴡᴏɴ: ${fmt(lb.get('amt_won', 0))}\n"
        f"💸 ᴀᴍᴏᴜɴᴛ ʟᴏꜱꜱ: ${fmt(lb.get('amt_lost', 0))}\n"
        f"🔥 ꜱᴛʀᴇᴀɪ: {lb.get('streak', 0)}\n"
        f"🎖️ ʀᴀɴᴋ: #{rank}"
    )


async def cmd_tttrank(client, message):
    await message.reply(await _ttt_rank_text(message.from_user))


def register(add, filters, add_cb, **kwargs) -> int:
    n = 0
    add(cmd_ttt, filters.command(["ttt"]), group=0); n += 1
    add(cmd_tttrank, filters.command(["tttrank"]), group=0); n += 1
    add(cmd_lb, filters.command(["lb"]), group=0); n += 1
    add_cb(ttt_callback, filters.regex(r"^ttt_")); n += 1
    return n
