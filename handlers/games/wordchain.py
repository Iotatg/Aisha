# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""Word Chain — build words off the last letter; no repeats; beat the clock.

Flow:
  /wordchain <word>        → open a round with the starting word
  next player types a word starting with the last letter of the previous
  word, longer than the previous one is NOT required, but must not repeat.
  20s per turn (config); timeout = that player is out; last survivor wins.
"""
import asyncio
import random
import time

import config
from core import money
from core.helpers import coins, mention
from core.ui import card, chip, notice

# ── validation helpers (pure, unit-tested) ────────────────────────────────

def normalize(word: str) -> str:
    return "".join(c for c in word.lower() if c.isalpha())


def valid_word(word: str, used: set[str], last_letter: str | None,
               min_len: int) -> tuple[bool, str]:
    w = normalize(word)
    if len(w) < min_len:
        return False, f"ᴍɪɴ {min_len} ʟᴇᴛᴛᴇʀꜱ!"
    if last_letter and w[0] != last_letter:
        return False, f"ᴍᴜꜱᴛ ꜱᴛᴀʀᴛ ᴡɪᴛʜ '{last_letter.upper()}'!"
    if w in used:
        return False, "ᴀʟʀᴇᴀᴅʏ ᴜꜱᴇᴅ!"
    return True, ""


# ── round state ────────────────────────────────────────────────────────────

class ChainRound:
    def __init__(self, starter_id, first_word):
        self.players: dict[int, dict] = {starter_id: {"name": "", "alive": True}}
        self.order: list[int] = [starter_id]
        self.last_player: int | None = None   # who played last (none yet)
        self.used: set[str] = {normalize(first_word)}
        self.last_letter: str = normalize(first_word)[-1]
        self.task = None                   # asyncio handle for turn timer
        self.msg_id = None
        self.started_at = time.time()


rounds: dict[int, ChainRound] = {}   # chat_id -> round


async def _timeout(client, cid):
    await asyncio.sleep(config.WORDCHAIN_TURN_SECS)
    rd = rounds.get(cid)
    if not rd:
        return
    uid = expected_next(rd)
    if uid is None:
        await _finish(client, cid,
                      [p for p in rd.order if rd.players[p]["alive"]])
        return
    rd.players[uid]["alive"] = False
    alive = [p for p in rd.order if rd.players[p]["alive"]]
    try:
        await client.send_message(
            cid,
            card("⏰ ᴛɪᴍᴇ'ꜱ ᴜᴘ!", [
                f"{mention(uid, rd.players[uid]['name'])} "
                f"ɪꜱ ᴏᴜᴛ 👋 ({len(alive)} ʟᴇꜰᴛ)",
            ], icon="⏰")
        )
    except Exception:
        pass
    if len(alive) <= 1:
        await _finish(client, cid, alive)
    else:
        rd.last_player = uid   # eliminated player counts as 'last'
        await _schedule(client, cid)


def expected_next(rd: ChainRound) -> int | None:
    """First alive player who is allowed to move now."""
    for p in rd.order:
        if rd.players[p]["alive"] and p != rd.last_player:
            return p
    return None


async def _schedule(client, cid):
    rd = rounds.get(cid)
    if not rd:
        return
    if rd.task:
        rd.task.cancel()
    rd.task = asyncio.create_task(_timeout(client, cid))


async def _finish(client, cid, alive_ids):
    rd = rounds.pop(cid, None)
    if not rd:
        return
    if rd.task:
        rd.task.cancel()
    if alive_ids:
        w = alive_ids[0]
        await money.ensure_user(w)
        await money.add_balance(w, config.WORDCHAIN_WIN_COINS)
        await money.add_xp(w, config.WORDCHAIN_WIN_XP)
        nm = rd.players[w]["name"]
        try:
            await client.send_message(
                cid,
                card("🏆 ᴄʜᴀɪɴ ᴄʜᴀᴍᴘ!", [
                    f"{mention(w, nm)} ꜱᴜʀᴠɪᴠᴇᴅ ᴛʜᴇ ᴄʜᴀɪɴ!",
                    chip("ᴡᴏɴ", coins(f'+{config.WORDCHAIN_WIN_COINS:,}') +
                         f" • +{config.WORDCHAIN_WIN_XP} xᴘ", "💰"),
                    f"🔗 ᴡᴏʀᴅꜱ ᴘʟᴀʏᴇᴅ: {len(rd.used)}",
                ], icon="🏆")
            )
        except Exception:
            pass


# ── commands ───────────────────────────────────────────────────────────────

async def cmd_wordchain(client, message):
    cid = message.chat.id
    u = message.from_user
    parts = (message.text or "").split()
    if cid in rounds:
        await message.reply(notice("🔗 ᴀ ᴄʜᴀɪɴ ɪꜱ ᴀʟʀᴇᴀᴅʏ ʀᴜɴɴɪɴɢ!"))
        return
    if len(parts) < 2 or not normalize(parts[1]):
        await message.reply(notice("/ᴡᴏʀᴅᴄʜᴀɪɴ <ꜱᴛᴀʀᴛɪɴɢ ᴡᴏʀᴅ>"))
        return
    word = normalize(parts[1])
    if len(word) < config.WORDCHAIN_MIN_LEN:
        await message.reply(notice(
            f"ꜱᴛᴀʀᴛɪɴɢ ᴡᴏʀᴅ ɴᴇᴇᴅꜱ {config.WORDCHAIN_MIN_LEN}+ ʟᴇᴛᴛᴇʀꜱ!"))
        return
    rd = ChainRound(u.id, word)
    rd.players[u.id]["name"] = u.first_name
    rd.last_player = u.id          # opener counts as their move
    rounds[cid] = rd
    m = await message.reply(
        card("🔗 ᴡᴏʀᴅ ᴄʜᴀɪɴ!", [
            f"ꜱᴛᴀʀᴛ: <b>{word.upper()}</b>",
            f"ɴᴇxᴛ ᴡᴏʀᴅ ꜱᴛᴀʀᴛꜱ ᴡɪᴛʜ '<b>{rd.last_letter.upper()}</b>'",
            f"⏱️ {config.WORDCHAIN_TURN_SECS}s ᴘᴇʀ ᴛᴜʀɴ — ᴛɪᴍᴇᴏᴜᴛ = ᴏᴜᴛ!",
            chip("ᴘʀɪᴢᴇ", coins(config.WORDCHAIN_WIN_COINS) +
                 f" + {config.WORDCHAIN_WIN_XP} xᴘ", "🏆"),
            "",
            f"▶️ {mention(u.id, u.first_name)}, ᴄᴏɴᴛɪɴᴜᴇ ᴛʜᴇ ᴄʜᴀɪɴ!",
        ], icon="🔗")
    )
    rd.msg_id = getattr(m, "id", None)
    await _schedule(client, cid)


async def on_chain_word(client, message):
    """Group message listener while a chain is active."""
    cid = message.chat.id
    rd = rounds.get(cid)
    if not rd or not message.text:
        return
    u = message.from_user
    if not u or message.text.startswith("/"):
        return
    if u.id not in rd.players:
        # join mid-game by playing a valid word
        rd.players[u.id] = {"name": u.first_name, "alive": True}
        rd.order.append(u.id)
    if not rd.players[u.id]["alive"]:
        return
    if u.id == rd.last_player:
        return   # you just played; wait for someone else

    ok, reason = valid_word(message.text, rd.used, rd.last_letter,
                            config.WORDCHAIN_MIN_LEN)
    if not ok:
        try:
            await message.reply(notice(reason))
        except Exception:
            pass
        return

    w = normalize(message.text)
    rd.used.add(w)
    rd.last_letter = w[-1]
    rd.players[u.id]["name"] = u.first_name
    rd.last_player = u.id
    await _schedule(client, cid)
    nxt = expected_next(rd)
    try:
        if nxt:
            await message.reply(
                f"🔗 <b>{w.upper()}</b> ✓  →  ɴᴇxᴛ: "
                f"'<b>{rd.last_letter.upper()}</b>' • "
                f"{mention(nxt, rd.players[nxt]['name'])}'s ᴛᴜʀɴ! ⏱️"
            )
        else:
            # nobody else alive → current player wins by survival
            await _finish(client, cid, [u.id])
    except Exception:
        pass


async def cmd_chainend(client, message):
    """Host/admin abort with full fairness (no rewards)."""
    cid = message.chat.id
    if cid not in rounds:
        await message.reply("🫧 ɴᴏ ᴄʜᴀɪɴ ʀᴜɴɴɪɴɢ.")
        return
    rd = rounds.pop(cid)
    if rd.task:
        rd.task.cancel()
    await message.reply(
        card("🛑 ᴄʜᴀɪɴ ᴇɴᴅᴇᴅ", [f"{len(rd.used)} ᴡᴏʀᴅꜱ ᴘʟᴀʏᴇᴅ 🌸"], icon="🛑"))


def register(add, filters, add_cb) -> int:
    add(cmd_wordchain, filters.command(["wordchain", "chain"]))
    add(cmd_chainend, filters.command(["chainend"]))
    # OWN handler group (3) so it never shadows chatbot (2) or other
    # group-1 listeners — pyrogram runs only the first match per group.
    add(on_chain_word, filters.group & filters.text &
        ~filters.command(["wordchain", "chainend", "start", "help"]), group=3)
    return 3
