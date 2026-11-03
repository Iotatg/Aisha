# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""Aisha broadcast / DM commands — owner-only mass messaging with retract +
auto-delete timer, rebuilt systematically on a bot-safe target model.

Commands:
  /broadcast <text>          send text or replied media to every group
  /dm <text>                 send to every DM-able user (or /dm <id> <text>)
  /delbroadcast <id> [chat]  retract a broadcast run
  /deldm <id> [chat]         retract a dm run
  /broadcasthistory          list recent broadcast runs
  /dmhistory                 list recent dm runs

Flags for /broadcast: -pin -pinloud -nobot -user -silent, plus a -<n><h|m|s|d>
timer token (e.g. -12h, -30m, -2d) to auto-delete the run afterwards.
"""
import asyncio
import logging
import re
import time

from pyrogram import errors as tg_errors
from pyrogram.enums import ParseMode

from core.owner import is_owner
from core.broadcast import (
    create_broadcast_record, add_target, get_record,
    list_history, get_all_groups,
    get_broadcastable_users, forget_group, forget_user,
    classify_delivery_error,
)

log = logging.getLogger(__name__)

_DUR_RE = re.compile(r"-(\d+)([hmsd])")
_UNIT_SECS = {"s": 1, "m": 60, "h": 3600, "d": 86400}

_BROADCAST_FLAGS = ("-pin", "-pinloud", "-nobot", "-user", "-silent")


# ── helpers ───────────────────────────────────────────────────────────────────

def parse_duration(text: str):
    """Split a trailing `-<n><unit>` timer token off the text.

    Returns (cleaned_text, delete_after_epoch_or_None).
    """
    m = _DUR_RE.search(text or "")
    if not m:
        return text, None
    cleaned = (text[:m.start()] + text[m.end():]).strip()
    secs = int(m.group(1)) * _UNIT_SECS[m.group(2)]
    return cleaned, int(time.time()) + secs


def delete_after_label(delete_after: int) -> str:
    if not delete_after:
        return ""
    rem = max(0, delete_after - int(time.time()))
    h, mnt = divmod(rem // 60, 60)
    bits = []
    if h:
        bits.append(f"{h}h")
    if mnt or not bits:
        bits.append(f"{mnt}m")
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(delete_after))
    return f"{' '.join(bits)} (at {when})"


def _esc(s: str) -> str:
    return (s or "").replace("<", "&lt;").replace(">", "&gt;")


async def _owner_only(message):
    """Return the sender if they are the owner, else reply a clear notice and
    return None. A silent `return` here is exactly what produced 'no response'
    reports, so we always surface the rejection."""
    u = message.from_user
    if not u or not await is_owner(u.id):
        await message.reply("❌ ɴᴏᴛ ᴏᴡɴᴇʀ — ᴏɴʟʏ ᴍʏ ᴏᴡɴᴇʀ ᴄᴀɴ ᴜsᴇ ᴛʜɪs.")
        return None
    return u


def _preview(message) -> str:
    rm = message.reply_to_message
    if rm:
        return (rm.text or rm.caption or "[media]")
    return (message.text or "")


# ── delivery core ──────────────────────────────────────────────────────────────

async def _send_to(client, cid, make_msg):
    """Send one message, transparently retrying once past a FloodWait.

    Returns ("ok", sent_message) | ("dead", None) | ("fail", None).
    """
    try:
        return "ok", await make_msg(cid)
    except tg_errors.FloodWait as fw:
        await asyncio.sleep(min(int(fw.value), 30))
        try:
            return "ok", await make_msg(cid)
        except Exception as e:  # still failing after the wait
            return classify_delivery_error(e), None
    except Exception as e:
        return classify_delivery_error(e), None


# ── /broadcast ──────────────────────────────────────────────────────────────────

async def cmd_broadcast(client, message):
    u = await _owner_only(message)
    if not u:
        return

    rm = message.reply_to_message
    args = message.command[1:] if len(message.command or []) > 1 else []
    text = " ".join(args)

    flags = {f: (f in text) for f in _BROADCAST_FLAGS}
    for f in flags:
        if flags[f]:
            text = text.replace(f, "").strip()

    text, delete_after = parse_duration(text)

    if not rm and not text:
        await message.reply(
            "📢 <b>ʙʀᴏᴀᴅᴄᴀsᴛ</b>\n\n"
            "/broadcast &lt;text&gt;\n\n"
            "ꜰʟᴀɢs:\n"
            "• <code>-pin</code> — pin silently\n"
            "• <code>-pinloud</code> — pin loudly\n"
            "• <code>-nobot</code> — skip groups\n"
            "• <code>-user</code> — also DM users\n"
            "• <code>-silent</code> — copy reply, no forward tag\n"
            "• <code>-12h / -30m / -2d …</code> — auto-delete after\n\n"
            "ʀᴇᴘʟʏ ᴛᴏ ᴀɴʏ ᴍᴇssᴀɢᴇ ᴛᴏ sᴇɴᴅ ɪᴛ ᴀs-ɪs.",
            parse_mode=ParseMode.HTML,
        )
        return

    bid = await create_broadcast_record("broadcast", _preview(message), u.id,
                                        delete_after=delete_after)
    status = await message.reply(f"📢 ʙʀᴏᴀᴅᴄᴀsᴛɪɴɢ…  <code>#{bid}</code>")
    asyncio.create_task(
        _run_broadcast(client, status, bid, flags, text, rm, delete_after))


async def _run_broadcast(client, status, bid, flags, text, rm, delete_after):
    """Background delivery worker. Returns immediately; keeps `status`
    updated with progress and ALWAYS finalises it (done / partial / error)."""
    try:
        groups = [] if flags["-nobot"] else await get_all_groups()
        users = list(await get_broadcastable_users()) if flags["-user"] else []
        total = len(groups) + len(users)
        sent = pinned = failed = 0

        def make(cid):
            if rm:
                if flags["-silent"]:
                    return client.copy_message(cid, rm.chat.id, rm.id)
                return client.forward_messages(cid, rm.chat.id, rm.id)
            return client.send_message(cid, text)

        for cid in groups:
            res, m = await _send_to(client, cid, make)
            if res == "ok":
                sent += 1
                await add_target(bid, cid, m.id, "group")
                if flags["-pin"] or flags["-pinloud"]:
                    try:
                        await client.pin_chat_message(
                            cid, m.id,
                            disable_notification=not flags["-pinloud"])
                        pinned += 1
                    except Exception:
                        pass
            elif res == "dead":
                await forget_group(cid)
                failed += 1
            else:
                failed += 1
            await _maybe_progress_b(status, bid, delete_after, sent, total, pinned)
            await asyncio.sleep(0.15)

        for cid in users:
            res, m = await _send_to(client, cid, make)
            if res == "ok":
                sent += 1
                await add_target(bid, cid, m.id, "user")
            elif res == "dead":
                await forget_user(cid)
                failed += 1
            else:
                failed += 1
            await _maybe_progress_b(status, bid, delete_after, sent, total, pinned)
            await asyncio.sleep(0.15)

        await _finish_b(status, bid, delete_after, sent, total, pinned, failed)
    except Exception as e:
        log.exception("broadcast run failed bid=%s", bid)
        await _safe_edit(status,
                         f"❌ ʙʀᴏᴀᴅᴄᴀsᴛ ᴇʀʀᴏʀ: <code>{_esc(str(e))}</code>\n"
                         f"🗑️ ʀᴇᴛʀᴀᴄᴛ ᴡɪᴛʜ /delbroadcast {bid}", bid)


async def _maybe_progress_b(status, bid, delete_after, sent, total, pinned):
    if sent % 25 != 0:
        return
    timer = (f"🕒 ᴀᴜᴛᴏ-ᴅᴇʟᴇᴛᴇs ɪɴ <b>{delete_after_label(delete_after)}</b>\n"
             if delete_after else "")
    await _safe_edit(
        status,
        f"📢 ʙʀᴏᴀᴅᴄᴀsᴛɪɴɢ…  <code>#{bid}</code>\n"
        f"🔄 sᴇɴᴛ: <b>{sent}</b> / {total}\n📌 ᴘɪɴɴᴇᴅ: <b>{pinned}</b>\n{timer}",
        bid)


async def _finish_b(status, bid, delete_after, sent, total, pinned, failed):
    timer = (f"🕒 ᴀᴜᴛᴏ-ᴅᴇʟᴇᴛᴇs ɪɴ <b>{delete_after_label(delete_after)}</b>\n"
             if delete_after else "")
    tail = "⚠️ sᴏᴍᴇ ꜰᴀɪʟᴇᴅ" if failed else ""
    await _safe_edit(
        status,
        f"✅ ʙʀᴏᴀᴅᴄᴀsᴛ ᴅᴏɴᴇ!  <code>#{bid}</code>\n"
        f"sᴇɴᴛ: <b>{sent}</b> / {total}\n📌 ᴘɪɴɴᴇᴅ: <b>{pinned}</b>\n"
        f"{timer}{tail}\n🗑️ ʀᴇᴛʀᴀᴄᴛ ᴡɪᴛʜ /delbroadcast {bid}",
        bid)


# ── /dm ────────────────────────────────────────────────────────────────────────

async def cmd_dm(client, message):
    u = await _owner_only(message)
    if not u:
        return

    rm = message.reply_to_message
    args = list(message.command[1:] if len(message.command or []) > 1 else [])

    silent = False
    if "-silent" in args:
        silent = True
        args = [a for a in args if a != "-silent"]

    text = " ".join(args)
    single_uid = None
    if args and args[0].lstrip("-").isdigit() and len(args) > 1:
        single_uid = int(args[0])
        text = " ".join(args[1:])

    text, delete_after = parse_duration(text)

    if not text and not rm:
        await message.reply(
            "📩 <b>ᴅᴍ</b>\n\n"
            "/dm &lt;text&gt; — DM all users\n"
            "/dm &lt;user_id&gt; &lt;text&gt; — DM one user\n"
            "/dm -silent — copy reply without forward tag\n"
            "ʀᴇᴘʟʏ ᴛᴏ ᴀɴʏ ᴍᴇssᴀɢᴇ ᴛᴏ sᴇɴᴅ ɪᴛ ᴀs-ɪs.",
            parse_mode=ParseMode.HTML,
        )
        return

    bid = await create_broadcast_record("dm", _preview(message), u.id,
                                        delete_after=delete_after)

    if single_uid is not None:

        def make(cid):
            if rm:
                if silent:
                    return client.copy_message(cid, rm.chat.id, rm.id)
                return client.forward_messages(cid, rm.chat.id, rm.id)
            return client.send_message(cid, text)

        res, m = await _send_to(client, single_uid, make)
        if res == "ok":
            await add_target(bid, single_uid, m.id, "user")
            await message.reply(
                f"✅ sᴇɴᴛ ᴛᴏ <code>{single_uid}</code>!  <code>#{bid}</code>\n"
                f"🗑️ ʀᴇᴛʀᴀᴄᴛ ᴡɪᴛʜ /deldm {bid}",
                parse_mode=ParseMode.HTML)
        else:
            if res == "dead":
                await forget_user(single_uid)
            await message.reply(
                f"❌ ᴄᴏᴜʟᴅɴ'ᴛ ᴅᴇʟɪᴠᴇʀ: <code>{_esc(str(m) or 'error')}</code>",
                parse_mode=ParseMode.HTML)
        return

    status = await message.reply(f"📩 sᴇɴᴅɪɴɢ ᴅᴍs…  <code>#{bid}</code>")
    asyncio.create_task(
        _run_dm_bulk(client, status, bid, text, rm, silent, delete_after))


async def _run_dm_bulk(client, status, bid, text, rm, silent, delete_after):
    try:
        users = await get_broadcastable_users()
        total = len(users)
        sent = failed = 0

        def make(cid):
            if rm:
                if silent:
                    return client.copy_message(cid, rm.chat.id, rm.id)
                return client.forward_messages(cid, rm.chat.id, rm.id)
            return client.send_message(cid, text)

        for cid in users:
            res, m = await _send_to(client, cid, make)
            if res == "ok":
                sent += 1
                await add_target(bid, cid, m.id, "user")
            elif res == "dead":
                await forget_user(cid)
                failed += 1
            else:
                failed += 1
            if sent % 25 == 0:
                await _safe_edit(
                    status,
                    f"📩 sᴇɴᴅɪɴɢ ᴅᴍs…  <code>#{bid}</code>\n"
                    f"🔄 sᴇɴᴛ: <b>{sent}</b> / {total}",
                    bid)
            await asyncio.sleep(0.15)

        tail = "⚠️ sᴏᴍᴇ ꜰᴀɪʟᴇᴅ" if failed else ""
        await _safe_edit(
            status,
            f"✅ ᴅᴍ ᴅᴏɴᴇ!  <code>#{bid}</code>\n"
            f"sᴇɴᴛ: <b>{sent}</b> / {total} | ꜰᴀɪʟᴇᴅ: <b>{failed}</b>\n{tail}\n"
            f"🗑️ ʀᴇᴛʀᴀᴄᴛ ᴡɪᴛʜ /deldm {bid}",
            bid)
    except Exception as e:
        log.exception("dm run failed bid=%s", bid)
        await _safe_edit(status,
                         f"❌ ᴅᴍ ᴇʀʀᴏʀ: <code>{_esc(str(e))}</code>\n"
                         f"🗑️ ʀᴇᴛʀᴀᴄᴛ ᴡɪᴛʜ /deldm {bid}",
                         bid)


# ── retract ─────────────────────────────────────────────────────────────────────

async def cmd_delbroadcast(client, message):
    await _delete_record(client, message, "broadcast", "/delbroadcast")


async def cmd_deldm(client, message):
    await _delete_record(client, message, "dm", "/deldm")


async def _delete_record(client, message, kind, cmd):
    u = await _owner_only(message)
    if not u:
        return
    args = message.command[1:] if len(message.command or []) > 1 else []
    if not args:
        await message.reply(
            f"ᴜsᴀɢᴇ:\n{cmd} &lt;id&gt; — delete everywhere\n"
            f"{cmd} &lt;id&gt; &lt;chat_id&gt; — delete from one chat\n\n"
            f"ꜰɪɴᴅ ɪᴅs ᴡɪᴛʜ /{'broadcasthistory' if kind == 'broadcast' else 'dmhistory'}",
            parse_mode=ParseMode.HTML)
        return

    bid = args[0]
    rec = await get_record(bid)
    if not rec:
        await message.reply(f"❌ ɴᴏ ʀᴇᴄᴏʀᴅ ᴡɪᴛʜ ɪᴅ <code>{bid}</code>",
                            parse_mode=ParseMode.HTML)
        return
    if rec.get("kind") != kind:
        await message.reply(f"❌ <code>{bid}</code> ɪs ɴᴏᴛ ᴀ {kind} ʀᴇᴄᴏʀᴅ.",
                            parse_mode=ParseMode.HTML)
        return

    only_chat = None
    if len(args) > 1:
        try:
            only_chat = int(args[1])
        except ValueError:
            await message.reply("❌ ᴄʜᴀᴛ ɪᴅ ᴍᴜsᴛ ʙᴇ ᴀ ɴᴜᴍʙᴇʀ!", parse_mode=ParseMode.HTML)
            return

    targets = rec.get("targets", [])
    if only_chat is not None:
        targets = [t for t in targets if t["chat_id"] == only_chat]
        if not targets:
            await message.reply(
                f"❌ ᴛʜɪs ʀᴇᴄᴏʀᴅ ɴᴇᴠᴇʀ ʀᴇᴀᴄʜᴇᴅ <code>{only_chat}</code>.",
                parse_mode=ParseMode.HTML)
            return

    status = await message.reply(
        f"🗑️ ᴅᴇʟᴇᴛɪɴɢ ꜰʀᴏᴍ {len(targets)} ᴛᴀʀɢᴇᴛ(s)…")
    deleted = 0
    for t in targets:
        try:
            await client.delete_messages(t["chat_id"], t["message_id"])
            deleted += 1
        except Exception:
            pass
        await asyncio.sleep(0.05)
    scope = (f"ꜰʀᴏᴍ ᴄʜᴀᴛ <code>{only_chat}</code>"
             if only_chat else "ꜰʀᴏᴍ ᴇᴠᴇʀʏᴡʜᴇʀᴇ")
    await status.edit_text(
        f"🗑️ <b>ᴅᴇʟᴇᴛɪᴏɴ ᴄᴏᴍᴘʟᴇᴛᴇ</b> ({scope})\n\n"
        f"✅ ᴅᴇʟᴇᴛᴇᴅ: {deleted}\n⚠️ ꜰᴀɪʟᴇᴅ: {len(targets) - deleted}",
        parse_mode=ParseMode.HTML)


# ── history ─────────────────────────────────────────────────────────────────────

async def cmd_broadcasthistory(client, message):
    await _history(client, message, "broadcast")


async def cmd_dmhistory(client, message):
    await _history(client, message, "dm")


async def _history(client, message, kind):
    u = await _owner_only(message)
    if not u:
        return
    recs = await list_history(kind, limit=20)
    if not recs:
        await message.reply(f"📜 ɴᴏ {kind} ʜɪsᴛᴏʀʏ ʏᴇᴛ.")
        return
    lines = [f"📜 <b>{kind.upper()} ʜɪsᴛᴏʀʏ</b> (ʟᴀsᴛ {len(recs)})"]
    for r in recs:
        n = len(r.get("targets", []))
        da = r.get("delete_after")
        tag = f" 🕒{delete_after_label(da)}" if da else ""
        lines.append(f"• <code>#{r['_id']}</code> → {n} ᴛᴀʀɢᴇᴛs{tag}\n"
                     f"  {_esc(r.get('content_preview', ''))[:60]}")
    await message.reply("\n".join(lines), parse_mode=ParseMode.HTML)


# ── status edit helper ───────────────────────────────────────────────────────────

async def _safe_edit(status, text, bid):
    try:
        await status.edit_text(text, parse_mode=ParseMode.HTML)
    except Exception:
        log.debug("status edit failed for %s", bid)


def register(add, filters, add_cb, **kwargs) -> int:
    n = 0
    add(cmd_broadcast, filters.command("broadcast")); n += 1
    add(cmd_dm, filters.command("dm")); n += 1
    add(cmd_delbroadcast, filters.command("delbroadcast")); n += 1
    add(cmd_deldm, filters.command("deldm")); n += 1
    add(cmd_broadcasthistory, filters.command("broadcasthistory")); n += 1
    add(cmd_dmhistory, filters.command("dmhistory")); n += 1
    return n
