# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""Lucky Box — pick one of three girly boxes; risk it all 🎀"""
import random

import config
from core import money
from core.helpers import coins, mention
from core.ui import card, chip, notice

# (label, multiplier) — 0 means lose, 1.5 refund-ish, 2 double, 3 jackpot
BOXES = [
    ("🎀 ᴘɪɴᴋ ʙᴏx", None),   # rolled at runtime
    ("🎁 ɢɪꜰᴛ ʙᴏx", None),
    ("💖 ʜᴇᴀʀᴛ ʙᴏx", None),
]

OUTCOMES = [
    (2.0, 45),   # (multiplier, weight%) — win x2
    (3.0, 10),   # jackpot x3
    (1.5, 20),   # soft refund x1.5
    (0.0, 25),   # bust
]


def roll_multiplier() -> float:
    r = random.uniform(0, 100)
    acc = 0
    for mult, weight in OUTCOMES:
        acc += weight
        if r <= acc:
            return mult
    return OUTCOMES[-1][0]


def build_keyboard(bet: int):
    from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    rows = [[InlineKeyboardButton(label,
                                  callback_data=f"lbox|{bet}|{i}")
             for i, (label, _) in enumerate(BOXES)]]
    return InlineKeyboardMarkup(rows)


async def cmd_luckybox(client, message):
    u = message.from_user
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.reply(
            card("🎀 ʟᴜᴄᴋʏ ʙᴏx", [
                "ᴄʜᴏᴏꜱᴇ ᴏɴᴇ ᴏꜰ ᴛʜʀᴇᴇ ᴍʏꜱᴛᴇʀʏ ʙᴏxᴇꜱ:",
                "• x2 ᴡɪɴ — 45% ᴄʜᴀɴᴄᴇ 💰",
                "• x3 ᴊᴀᴄᴋᴘᴏᴛ — 10% 🥳",
                "• x1.5 ꜱᴏꜰᴛ ʟᴀɴᴅ — 20% 🌷",
                "• ʙᴜꜱᴛ... — 25% 💀",
                "",
                f"ℹ️ /ʟᴜᴄᴋʏʙᴏx ʙᴇᴛ (ᴍɪɴ {config.MIN_BET}, "
                f"ᴍᴀx {config.MAX_BET})",
            ], icon="🎀")
        )
        return
    try:
        bet = int(parts[1])
    except ValueError:
        await message.reply(notice("ɪɴᴠᴀʟɪᴅ ʙᴇᴛ!"))
        return
    if not (config.MIN_BET <= bet <= config.MAX_BET):
        await message.reply(
            f"❌ <b>ʙᴇᴛ ɢᴏᴇꜱ {config.MIN_BET}–{config.MAX_BET}!</b>")
        return
    await money.ensure_user(u.id, username=u.username or "",
                            name=u.first_name)
    await message.reply(
        card("🎁 ʟᴜᴄᴋʏ ʙᴏx", [
            f"{mention(u.id, u.first_name)}, ᴘɪᴄᴋ ʏᴏᴜʀ ʙᴏx!",
            chip("ʙᴇᴛ", coins(bet), "💰"),
        ], icon="🎁"),
        reply_markup=build_keyboard(bet),
    )


async def on_box_pick(client, query):
    _, bet_s, idx_s = query.data.split("|")
    bet, idx = int(bet_s), int(idx_s)
    u = query.from_user

    if not await money.try_deduct(u.id, bet):
        try:
            await query.answer("💸 ɴᴏᴛ ᴇɴᴏᴜɢʜ ᴄᴏɪɴꜱ!", show_alert=True)
        except Exception:
            pass
        return

    mult = roll_multiplier()
    payout = int(bet * mult)
    label = BOXES[idx][0]

    if mult == 0:
        text = card(f"{label} 💔", [
            f"ᴏᴍɢ... ɪᴛ ᴡᴀꜱ ᴇᴍᴘᴛʏ! ʟᴏꜱᴛ {coins(bet)} 😭",
        ], icon="💔")
        emoji = "😢"
    else:
        await money.add_balance(u.id, payout)
        xp_gain = 15 if mult >= 2 else 8
        await money.add_xp(u.id, xp_gain)
        if mult >= 2:
            head = "🥳 ᴊᴀᴄᴋᴘᴏᴛ!" if mult == 3 else "🎉 ᴡᴏɴ!"
            text = card(f"{label} {head}", [
                f"{mention(u.id, u.first_name)} ᴡᴏɴ {coins(payout)} ✨",
                f"(+{xp_gain} xᴘ)",
            ], icon="🥳")
        else:
            text = card(f"{label} 🌷", [
                "ꜱᴏꜰᴛ ʟᴀɴᴅ!",
                f"{mention(u.id, u.first_name)} ɢᴏᴛ ʙᴀᴄᴋ "
                f"{coins(payout)} (+{xp_gain} xᴘ)",
            ], icon="🌷")
        emoji = "🥳" if mult >= 2 else "🙂"

    try:
        await query.answer(f"{emoji}", show_alert=False)
    except Exception:
        pass
    try:
        await query.message.edit_text(text, reply_markup=None)
    except Exception:
        pass


def register(add, filters, add_cb) -> int:
    add(cmd_luckybox, filters.command(["luckybox"]))
    add_cb(on_box_pick, filters.regex(r"^lbox\|"))
    return 2
