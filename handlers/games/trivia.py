# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""Trivia — multiple-choice quiz with inline buttons.

One active question per chat; first correct tap wins the pot.
"""
import random

import config
from core import money
from core.helpers import coins, mention
from core.ui import card, notice

# question bank: (question, [options...], correct_index)
QUESTIONS = [
    ("ᴡʜɪᴄʜ ᴘʟᴀɴᴇᴛ ɪꜱ ᴋɴᴏᴡɴ ᴀꜱ ᴛʜᴇ ʀᴇᴅ ᴘʟᴀɴᴇᴛ?", ["ᴠᴇɴᴜꜱ", "ᴍᴀʀꜱ", "ᴊᴜᴘɪᴛᴇʀ", "ᴍᴇʀᴄᴜʀʏ"], 1),
    ("ʜᴏᴡ ᴍᴀɴʏ ᴄᴏɴᴛɪɴᴇɴᴛꜱ ᴀʀᴇ ᴛʜᴇʀᴇ?", ["5", "6", "7", "8"], 2),
    ("ᴡʜᴀᴛ ɪꜱ 12 x 8?", ["86", "96", "106", "108"], 1),
    ("ᴡʜɪᴄʜ ᴏᴄᴇᴀɴ ɪꜱ ᴛʜᴇ ʙɪɢɢᴇꜱᴛ?", ["ᴀᴛʟᴀɴᴛɪᴄ", "ɪɴᴅɪᴀɴ", "ᴀʀᴄᴛɪᴄ", "ᴘᴀᴄɪғɪᴄ"], 3),
    ("ᴡʜᴀᴛ ᴄᴏʟᴏʀ ᴅᴏ ʏᴏᴜ ɢᴇᴛ ᴍɪxɪɴɢ ʙʟᴜᴇ + ʏᴇʟʟᴏᴡ?", ["ɢʀᴇᴇɴ", "ᴘᴜʀᴘʟᴇ", "ᴏʀᴀɴɢᴇ", "ʙʀᴏᴡɴ"], 0),
    ("ʜᴏᴡ ᴍᴀɴʏ ꜱɪᴅᴇꜱ ᴅᴏᴇꜱ ᴀ ʜᴇxᴀɢᴏɴ ʜᴀᴠᴇ?", ["5", "6", "7", "8"], 1),
    ("ᴡʜɪᴄʜ ᴀɴɪᴍᴀʟ ɪꜱ ᴋɴᴏᴡɴ ᴀꜱ ᴛʜᴇ ᴋɪɴɢ ᴏꢰ ᴛʜᴇ ᴊᴜɴɢʟᴇ?", ["ᴛɪɢᴇʀ", "ᴇʟᴇᴘʜᴀɴᴛ", "ʟɪᴏɴ", "ᴡᴏʟғ"], 2),
    ("ᴡʜᴀᴛ ɪꜱ ᴛʜᴇ ᴄʜᴇᴍɪᴄᴀʟ ꜱʏᴍʙᴏʟ ꜰᴏʀ ɢᴏʟᴅ?", ["ɢᴏ", "ɢᴅ", "ᴀᴜ", "ᴀɢ"], 2),
    ("ʜᴏᴡ ᴍᴀɴʏ ᴍɪɴᴜᴛᴇꜱ ɪɴ ᴀ ꜰᴜʟʟ ᴅᴀʏ?", ["1200", "1440", "1600", "2400"], 1),
    ("ᴡʜɪᴄʜ ꜰʀᴜɪᴛ ʜᴀꜱ ɪᴛꜱ ꜱᴇᴇᴅꜱ ᴏɴ ᴛʜᴇ ᴏᴜᴛꜱɪᴅᴇ?", ["ʙᴀɴᴀɴᴀ", "ꜱᴛʀᴀᴡʙᴇʀʀʏ", "ᴍᴀɴɢᴏ", "ᴘᴇᴀᴄʜ"], 1),
    ("ᴡʜᴀᴛ ɪꜱ ᴛʜᴇ ʟᴀʀɢᴇꜱᴛ ᴍᴀᴍᴍᴀʟ?", ["ᴀꜰʀɪᴄᴀɴ ᴇʟᴇᴘʜᴀɴᴛ", "ʙʟᴜᴇ ᴡʜᴀʟᴇ", "ɢɪʀᴀꜰꜰᴇ", "ᴏʀᴄᴀ"], 1),
    ("ʜᴏᴡ ᴍᴀɴʏ ᴇʟᴇᴍᴇɴᴛꜱ ɪɴ ᴛʜᴇ ᴘᴇʀɪᴏᴅɪᴄ ᴛᴀʙʟᴇ (ᴄᴜʀʀᴇɴᴛ)?", ["108", "112", "118", "124"], 2),
    ("ᴡʜɪᴄʜ ᴄᴏᴜɴᴛʀʏ ɪꜱ ʜᴏᴍᴇ ᴛᴏ ᴛʜᴇ ᴋᴀɴɢᴀʀᴏᴏ?", ["ᴀꜰʀɪᴄᴀ", "ʙʀᴀᴢɪʟ", "ᴀᴜꜱᴛʀᴀʟɪᴀ", "ɪɴᴅɪᴀ"], 2),
    ("ᴡʜᴀᴛ ᴅᴏ ʙᴇᴇꜱ ᴍᴀᴋᴇ?", ["ʜᴏɴᴇʏ", "ᴡᴀx ᴏɴʟʏ", "ᴍɪʟᴋ", "ᴊᴀᴍ"], 0),
    ("ᴡʜᴀᴛ ɪꜱ 50% ᴏꢰ 240?", ["110", "120", "130", "140"], 1),
]

LETTERS = ["🇦", "🇧", "🇨", "🇩"]

# chat_id -> {"q": tuple, "done": bool}
active: dict = {}


def build_keyboard(q_idx):
    from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    q = QUESTIONS[q_idx]
    rows = [[InlineKeyboardButton(f"{LETTERS[i]} {opt}",
                                  callback_data=f"trivia|{q_idx}|{i}")]
            for i, opt in enumerate(q[1])]
    return InlineKeyboardMarkup(rows)


async def cmd_trivia(client, message):
    cid = message.chat.id
    if cid in active and not active[cid]["done"]:
        await message.reply(notice("⏳ ᴀ Qᴜᴇꜱᴛɪᴏɴ ɪꜱ ᴀʟʀᴇᴀᴅʏ ʀᴜɴɴɪɴɢ!"))
        return
    q_idx = random.randrange(len(QUESTIONS))
    active[cid] = {"q": q_idx, "done": False, "winner": None}
    q = QUESTIONS[q_idx]
    await message.reply(
        card("🧠 ᴛʀɪᴠɪᴀ ᴛɪᴍᴇ!", [
            q[0],
            "",
            f"🎁 {coins(config.TRIVIA_REWARD)} + {config.TRIVIA_XP} xᴘ "
            f"ꜰᴏʀ ᴛʜᴇ ꜰɪʀꜱᴛ ᴄᴏʀʀᴇᴄᴛ ᴀɴꜱᴡᴇʀ!",
        ], icon="🧠"),
        reply_markup=build_keyboard(q_idx),
    )


async def on_trivia_answer(client, query):
    cid = query.message.chat.id
    state = active.get(cid)
    if not state or state["done"]:
        try:
            await query.answer("😴 ᴛᴏᴏ ʟᴀᴛᴇ!", show_alert=False)
        except Exception:
            pass
        return
    _, q_idx_s, choice_s = query.data.split("|")
    if int(q_idx_s) != state["q"]:
        try:
            await query.answer("⌛ ᴏʟᴅ Qᴜᴇꜱᴛɪᴏɴ!", show_alert=False)
        except Exception:
            pass
        return
    u = query.from_user
    correct = int(choice_s) == QUESTIONS[state["q"]][2]
    if correct:
        state["done"] = True
        await money.ensure_user(u.id, username=u.username or "",
                                name=u.first_name)
        await money.add_balance(u.id, config.TRIVIA_REWARD)
        await money.add_xp(u.id, config.TRIVIA_XP)
        active[cid]["winner"] = u.id
        try:
            await query.answer("✅ ᴄᴏʀʀᴇᴄᴛ!", show_alert=False)
        except Exception:
            pass
        await query.message.edit_text(
            card("🎉 ᴛʀɪᴠɪᴀ ᴡᴏɴ!", [
                f"{mention(u.id, u.first_name)} ɢᴏᴛ ɪᴛ ʀɪɢʜᴛ!",
                f"💡 ᴀɴꜱᴡᴇʀ: <b>{LETTERS[QUESTIONS[state['q']][2]]} "
                f"{QUESTIONS[state['q']][1][QUESTIONS[state['q']][2]]}</b>",
                f"🎁 +{config.TRIVIA_REWARD} ᴄᴏɪɴꜱ • +{config.TRIVIA_XP} xᴘ",
            ], icon="🎉"),
            reply_markup=None,
        )
    else:
        try:
            await query.answer("❌ ɴᴏᴘᴇ! ᴛʀʏ ᴀɢᴀɪɴ~", show_alert=False)
        except Exception:
            pass


def register(add, filters, add_cb) -> int:
    add(cmd_trivia, filters.command(["trivia"]))
    add_cb(on_trivia_answer, filters.regex(r"^trivia\|"))
    return 2
