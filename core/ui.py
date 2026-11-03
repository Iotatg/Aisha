# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""Aisha UI engine — one coherent visual language for every output.

Fresh implementation: a girly, sassy layer with the same structural
discipline so the whole bot reads like ONE polished product instead of a
loose pile of handlers:

  • banner()      decorated section header with soft divider
  • chip()        compact key/value line
  • bar()         text progress bar ▰▰▰▱▱▱
  • scorecard()   medal-ranked list
  • card()        full result card (header/body/footer)
  • notice()      red-alert ❗ line ("italian" punch)
  • table()       tidy two-column rows
  • lobby_card()  PvP/Duel open-lobby card
  • movie()       send→edit frame sequencer for in-chat animations

Emoji grammar (italian-stack vocabulary):
  ❗ notice  👥 players  💰 pot/coins  🏆 winner  💀 lost/bust
  🔥 streak  ⏳ timer  🎯 aim  ⚡ xp  🎮 game  ✨ sparkle  🎀 brand

Every sender here NEVER raises — a broken animation must never kill a
game flow.
"""
import asyncio
import logging

logger = logging.getLogger(__name__)

DIVIDER = "♡" * 1 + "─" * 24          # ───────────────────────♡ style tail
BAR_FULL, BAR_EMPTY = "▰", "▱"
# Row-prefix used in every leaderboard row (one icon, consistent grammar).
USER_ICON = "👤"


# ── core primitives ────────────────────────────────────────────────────────

def divider() -> str:
    return DIVIDER


def banner(title: str, icon: str = "🎀") -> str:
    """Section header: icon + bold title over a soft divider."""
    return f"{icon} <b>{title}</b>\n{DIVIDER}"


def rank(i: int) -> str:
    """Top-N rank label. ``#1`` for the first row, ``#2`` for the second, …
    No medal emojis — we use the same ``👤`` row-prefix for every entry
    so the leaderboard reads as a clean, consistent list.
    """
    return f"#{i + 1}"


def chip(label: str, value="", emoji="✧") -> str:
    if value:
        return f"{emoji} <b>{label}:</b> {value}"
    return f"{emoji} <b>{label}</b>"


def bar(value: int, maximum: int, width: int = 10) -> str:
    if maximum <= 0:
        return BAR_EMPTY * width
    ratio = max(0.0, min(1.0, value / maximum))
    filled = round(ratio * width)
    return BAR_FULL * filled + BAR_EMPTY * (width - filled)


def notice(text: str) -> str:
    """Red-alert ❗ line — punchy notice."""
    return f"❗ <b>{text}</b>"


def table(rows: list, sep: str = "—") -> str:
    """rows = [(left, right)] rendered as `left — right`."""
    if not rows:
        return "🫧 ᴇᴍᴘᴛʏ ʜᴇʀᴇ~"
    return "\n".join(f"{l} {sep} {r}" for l, r in rows[:12])


def scorecard(rows, title="🏆 ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ", user_icon: str = USER_ICON) -> str:
    """rows = [(name, value_str)] rendered as a tidy ranked table.

    Every row is prefixed with the same ``user_icon`` (default 👤) so
    the leaderboard reads as a uniform list — no medal noise.
    """
    if not rows:
        return f"{banner(title)}\n🫧 ɴᴏᴛʜɪɴɢ ʜᴇʀᴇ ʏᴇᴛ."
    lines = [banner(title)]
    for i, (name, val) in enumerate(rows[:12]):
        lines.append(f"{user_icon} {rank(i)} {name} — {val}")
    return "\n".join(lines)


def card(title, body_lines, icon="🎀", footer="") -> str:
    out = banner(title, icon) + "\n\n" + "\n".join(body_lines)
    if footer:
        out += "\n\n" + footer
    return out


def lobby_card(title: str, body_lines, icon: str = "👥") -> str:
    """PvP / duel open-lobby card (players section)."""
    return card(title, body_lines, icon=icon)


async def movie(client, chat_id, frames, final_text=None,
                delay=0.45, reply_markup=None):
    """Animate by sending the first frame then EDITING through the rest.

    Returns the final message id (or None). Never raises; a failed frame
    simply stops the sequence gracefully.
    """
    frames = list(frames)[:4]
    sent = None
    for i, fr in enumerate(frames):
        try:
            if sent is None:
                sent = await client.send_message(chat_id, fr)
            else:
                await client.edit_message_text(fr, chat_id, sent.id)
        except Exception as e:
            logger.debug("movie frame %d failed: %s", i, e)
            break
        if i < len(frames) - 1:
            try:
                await asyncio.sleep(delay)
            except Exception:
                break
    if final_text:
        try:
            m = await client.send_message(chat_id, final_text,
                                          reply_markup=reply_markup)
            return getattr(m, "id", getattr(m, "message_id", None))
        except Exception as e:
            logger.debug("movie caption failed: %s", e)
    if sent is not None:
        return getattr(sent, "id", getattr(sent, "message_id", None))
    return None


async def safe_reply(message, text, **kw):
    """Reply that never raises."""
    try:
        return await message.reply(text, **kw)
    except Exception as e:
        logger.debug("safe_reply failed: %s", e)
        return None


def truncate(name: str, limit: int = 18) -> str:
    name = str(name or "")
    return name if len(name) <= limit else name[:limit - 1] + "…"


def stable_pct(uid: int, salt: str = "") -> int:
    """Deterministic 0-99 percent per (uid, salt) — ratings stay put."""
    import hashlib
    h = hashlib.sha256(f"{uid}:{salt}".encode()).hexdigest()
    return int(h[:8], 16) % 100


def hearts_bar(pct: int, width: int = 5) -> str:
    filled = max(1, round(pct / 100 * width))
    return "💖" * filled + "🤍" * (width - filled)
