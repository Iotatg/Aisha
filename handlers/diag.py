# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""Diagnostics — catch "bot is silent" bugs at every layer.

Three probes, each answering a different question:

1. RAW UPDATE LOGGER   → Is Telegram delivering anything at all?
   Logs every raw update type + chat id into an in-memory ring buffer.

2. GROUP TEXT WATCHER  → Did a group text reach the dispatcher but die
   in our filters? Registered in a LATER handler group so it runs even
   when the chatbot handler didn't match.

3. /diag COMMAND       → One-shot health card: identity, handler count,
   recent raw updates, recent seen texts.
"""
import logging
import time
from collections import deque

log = logging.getLogger("diag")

_raw_ring: deque = deque(maxlen=60)
_text_ring: deque = deque(maxlen=30)
_raw_count = 0
_boot = time.time()


def _chat_id_of(update):
    """Best-effort chat id extraction from any raw update type."""
    for attr in ("chat", ):
        c = getattr(update, attr, None)
        if c is not None:
            return getattr(c, "id", None)
    msg = getattr(update, "message", None)
    if msg is not None:
        return getattr(getattr(msg, "chat", None), "id", None)
    return None


async def on_raw_update(client, update, users, chats):
    """RawUpdateHandler — fires for EVERY update Telegram sends us."""
    global _raw_count
    name = type(update).__name__
    cid = _chat_id_of(update)
    entry = {"t": round(time.time(), 2), "type": name, "chat": cid}
    _raw_ring.append(entry)
    _raw_count += 1
    log.info("RAW %s chat=%s", name, cid)


async def watch_group_texts(client, message):
    """Later-group MessageHandler: proves delivery independent of the
    chatbot's own filters."""
    u = getattr(message, "from_user", None)
    _text_ring.append({
        "t": round(time.time(), 2),
        "chat": message.chat.id,
        "user": getattr(u, "id", None),
        "text": (message.text or "")[:60],
    })
    log.info("SEEN TEXT chat=%s user=%s text=%.60s",
             message.chat.id, getattr(u, "id", None), message.text or "")


async def cmd_diag(client, message):
    import core.app as appmod
    me = await client.get_me()
    up = int(time.time() - _boot)
    lines = [
        "🔧 <b>ᴅɪᴀɢɴᴏꜱᴛɪᴄꜱ</b>",
        f"ʙᴏᴛ: @{me.username} (id {me.id})",
        f"ᴜᴘᴛɪᴍᴇ: {up}s • ʜᴀɴᴅʟᴇʀꜱ: {appmod.HANDLER_COUNT}",
        f"ʀᴀᴡ ᴜᴘᴅᴀᴛᴇꜱ: {_raw_count}",
        "",
        f"<b>ʟᴀꜱᴛ ʀᴀᴡ ᴜᴘᴅᴀᴛᴇꜱ ({len(_raw_ring)}):</b>",
    ]
    for e in list(_raw_ring)[-10:]:
        lines.append(f"• {e['t']:.1f} {e['type']} chat={e['chat']}")
    if not _raw_ring:
        lines.append("• (none — Telegram ने कुछ भेजा ही नहीं)")
    lines += ["", f"<b>ɢʀᴏᴜᴘ ᴛᴇxᴛꜱ ꜱᴇᴇɴ ({len(_text_ring)}):</b>"]
    for e in list(_text_ring)[-8:]:
        lines.append(f"• {e['t']:.1f} chat={e['chat']} user={e['user']} "
                     f"{e['text']}")
    if not _text_ring:
        lines.append("• (none)")
    await message.reply("\n".join(lines))


def register(add, filters, add_cb, add_raw=None, add_msg_edited=None) -> int:
    n = 0
    if add_raw:
        add_raw(on_raw_update)
        n += 1
    # last watcher group => proves delivery independent of everything else
    add(watch_group_texts,
        filters.group & filters.text, group=9)
    add(cmd_diag, filters.command(["diag"]))
    return n + 2
