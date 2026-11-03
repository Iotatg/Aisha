# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""Aisha chatbot — DM always-on, groups on mention/reply/tag.

Flow: trigger check → typing action → provider call (if keys) with
per-user memory → offline sass fallback → safe send. The 'thinking…'
placeholder is edited into the reply so chats feel alive, never silent.
"""
import asyncio
import html
import logging

from core import ai, memory, sass
from core.ui import safe_reply

log = logging.getLogger(__name__)

# per-user cooldown so she never double-fires in a busy group
_cooldown: dict[int, float] = {}
COOLDOWN_SECS = 2.0


def _md_to_html(text: str) -> str:
    """Convert common AI markdown to Telegram HTML (escape-first)."""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = _re_code_blocks(text)
    text = _re_inline_code(text)
    text = _re_bold(text)
    text = _re_ital(text)
    return text


def _re_code_blocks(text):
    import re
    return re.sub(r"```[a-z]*\n?(.*?)```",
                  lambda m: f"<code>{m.group(1).strip()}</code>",
                  text, flags=re.DOTALL)


def _re_inline_code(text):
    import re
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", text)


def _re_bold(text):
    import re
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)


def _re_ital(text):
    import re
    text = re.sub(r"\*([^*\n]+?)\*", r"<i>\1</i>", text)
    return re.sub(r"_([^_\n]+?)_", r"<i>\1</i>", text)


def is_triggered(message, bot_id: int, bot_username: str) -> bool:
    """DM: everything. Group: reply-to-bot, @tag / entity mention, or 'aisha'.

    NOTE: even with this passing, Telegram's bot privacy mode decides
    WHICH group messages ever reach us — see README (BotFather privacy).
    """
    raw = getattr(message.chat, "type", None)
    ctype = getattr(raw, "name", None) or str(raw or "")
    if ctype.upper() not in ("GROUP", "SUPERGROUP"):
        return True   # private chat

    reply = getattr(message, "reply_to_message", None)
    reply_user = getattr(reply, "from_user", None) if reply is not None else None
    if reply_user is not None and getattr(reply_user, "id", None) == bot_id:
        return True

    # pyrogram's ``mentioned`` covers both "@username" text and text_mention
    # entities (a user tapped from the member list), which a plain substring
    # test misses — and it never false-fires on an empty bot username.
    if getattr(message, "mentioned", False) is True:
        return True

    # Walk text_mention entities (member-list @tag) explicitly. Pyrogram's
    # ``mentioned`` flag is unreliable on some builds when the mention is
    # a text_mention rather than plain "@username" text.
    if _is_entity_mention(message, bot_id):
        return True

    text = (getattr(message, "text", None)
            or getattr(message, "caption", None) or "").lower()
    needles = ["aisha"]
    if bot_username:
        needles.append(f"@{bot_username.lower()}")
    return any(n in text for n in needles)


def _is_entity_mention(msg, bot_id: int) -> bool:
    """True when Telegram attached a text_mention entity pointing at this bot."""
    if msg is None:
        return False
    entities = list(getattr(msg, "entities", None) or [])
    entities += list(getattr(msg, "caption_entities", None) or [])
    for ent in entities:
        user = getattr(ent, "user", None)
        if user is not None and getattr(user, "id", None) == bot_id:
            return True
    return False


async def generate_reply(uid: int, name: str, text: str,
                         bot_username: str) -> tuple[str, bool]:
    """Returns (reply_text, used_ai). Falls back to sass engine."""
    turns = await memory.recent_turns(uid)
    turns.append({"role": "user", "content": text})
    system = sass.build_system_prompt(bot_username)
    raw = await asyncio.to_thread(ai.call_ai_sync, system, turns[-12:])
    if raw:
        await memory.remember(uid, "a", raw)
        return _md_to_html(raw), True
    return sass.pick_reply(uid, text), False


async def on_chat_message(client, message):
    u = message.from_user
    if u is None or getattr(u, "is_bot", False):
        return
    text = (message.text or message.caption or "").strip()
    if not text:
        return

    me = await client.get_me()
    log.info("CHAT MSG from=%s chat=%s type=%s text=%.40s",
             u.id, message.chat.id, getattr(message.chat.type, "name", "?"),
             text)
    if not is_triggered(message, me.id, me.username or ""):
        return

    import time as _t
    now = _t.time()
    if now - _cooldown.get(u.id, 0) < COOLDOWN_SECS:
        return
    _cooldown[u.id] = now

    await memory.remember(u.id, "u", text)

    # typing indicator: Telegram actions expire in ~5s, so keep renewing
    # it in the background until her reply is ready.
    stop_typing = asyncio.Event()

    async def _keep_typing():
        from pyrogram.enums import ChatAction
        while not stop_typing.is_set():
            try:
                await client.send_chat_action(message.chat.id,
                                              ChatAction.TYPING)
            except Exception as e:
                log.debug("chat_action failed: %s", e)
            try:
                await asyncio.wait_for(stop_typing.wait(), timeout=4.0)
            except asyncio.TimeoutError:
                pass

    typer = asyncio.create_task(_keep_typing())
    try:
        reply, _used_ai = await generate_reply(
            u.id, u.first_name or "", text, me.username or "")
    finally:
        stop_typing.set()
        try:
            await typer
        except Exception:
            pass
    esc = reply if "<" in reply else html.escape(reply)
    await safe_reply(message, esc)


async def cmd_aiclear(client, message):
    ok = await memory.clear(message.from_user.id)
    await message.reply(
        "🧹 ᴄʜᴀᴛ ᴍᴇᴍᴏʀʏ ꜱᴀᴀꜰ! ᴀʙ ᴍᴜᴊʜsᴇ ᴘʏᴀʀ ꜱᴇ ʙᴀᴛ ᴋᴀʀᴏ 😌"
        if ok else "🫧 ᴋᴏɪ ᴍᴇᴍᴏʀʏ ɴᴀʜɪ ᴛʜɪ ᴡᴀɪsᴇ ʙʜɪ~")


def register(add, filters, add_cb) -> int:
    from pyrogram import filters as f
    group_or_dm = f.group | f.private
    # ignore every slash command outright (never eat unknown commands)
    not_cmd = ~f.regex(r"^/")
    # DEDICATED group: games/extras listeners live in group 1; pyrogram
    # runs only the first matching handler per group — sharing a group
    # here made those listeners swallow chat messages before us.
    add(on_chat_message, group_or_dm & (f.text | f.caption) & not_cmd, group=2)
    add(cmd_aiclear, f.command(["aiclear"]))
    return 2
