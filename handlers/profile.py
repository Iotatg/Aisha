# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""Profile & XP: /me card, /topxp leaderboard, /topkills leaderboard, level-up notices."""
import config
from core import money
from core.helpers import coins, mention
from core.ui import banner, chip, card, scorecard, bar, truncate


# Kept identical to the test contract (title_for assertions).
LEVEL_TITLES = [
    (0, "ɴᴇᴡʙɪᴇ 🌱"), (3, "ᴄᴜᴛɪᴇ 🌸"), (6, "ꜱᴛᴀʀʟᴇᴛ ✨"),
    (10, "Qᴜᴇᴇɴ 👑"), (15, "ʟᴇɢᴇɴᴅ 💫"),
]


def title_for(level: int) -> str:
    t = LEVEL_TITLES[0][1]
    for min_lvl, name in LEVEL_TITLES:
        if level >= min_lvl:
            t = name
    return t


async def cmd_me(client, message):
    u = message.from_user
    doc = await money.ensure_user(u.id, username=u.username or "",
                                  name=u.first_name)
    xp = doc.get("xp", 0)
    lvl = money.level_for(xp)
    into, need = money.xp_progress(xp)
    b = bar(into, need, 10)
    wins = doc.get("games_won", 0)
    losses = doc.get("games_lost", 0)
    text = card("ᴘʀᴏꜰɪʟᴇ", [
        f"🎀 <b>{mention(u.id, doc.get('name') or u.first_name)}</b>",
        chip("ʟᴠʟ", f"{lvl} • {title_for(lvl)}", "🏅"),
        f"{b} <i>{into}/{need} xᴘ</i>",
        chip("ᴄᴏɪɴꜱ", coins(doc["balance"]), "💰"),
        chip("ɢᴇᴍꜱ", doc.get("gems", 0), "💎"),
        chip("ᴡ/ʟ", f"{wins}ʙ / {losses}ʟ", "⚔️"),
        chip("ꜱᴛʀᴇᴀᴋ", f"{doc.get('daily_streak', 0)} ᴅᴀʏꜱ 🔥", "🔥"),
    ], icon="🎀")
    await message.reply(text)


async def cmd_topxp(client, message):
    cursor = money.users().find().sort("xp", -1).limit(10)
    rows = []
    async for d in cursor:
        uid = d["_id"]
        xp = d.get("xp", 0)
        lvl = money.level_for(xp)
        nm = d.get("name") or str(uid)
        rows.append((
            mention(uid, truncate(nm)),
            f"ʟᴠʟ {lvl} • {title_for(lvl)} • {coins(xp).replace('🪙 ', '')} xᴘ",
        ))
    if not rows:
        await message.reply(card("⚡ xᴘ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ", [
            "🫧 ɴᴏ xᴘ ʏᴇᴛ — ᴘʟᴀʏ ꜱᴏᴍᴇ ɢᴀᴍᴇꜱ! 🎮",
        ], icon="⚡"))
        return
    await message.reply(scorecard(rows, "✨ xᴘ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ"))


async def cmd_topkills(client, message):
    cursor = money.users().find().sort("kills", -1).limit(10)
    rows = []
    async for d in cursor:
        uid = d["_id"]
        kills = d.get("kills", 0)
        nm = d.get("name") or str(uid)
        rows.append((mention(uid, truncate(nm)), f"{kills} ᴋɪʟʟꜱ"))
    if not rows:
        await message.reply(card("🔪 ᴋɪʟʟꜱ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ", [
            "🫧 ɴᴏ ᴋɪʟʟꜱ ʏᴇᴛ — ᴛʀʏ <code>/murder</code> 🔪",
        ], icon="🔪"))
        return
    await message.reply(scorecard(rows, "🔪 ᴋɪʟʟꜱ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ"))


def register(add, filters, add_cb) -> int:
    add(cmd_me, filters.command(["me", "profile"]))
    add(cmd_topxp, filters.command(["topxp"]))
    add(cmd_topkills, filters.command(["topkills", "top"]))
    return 3
