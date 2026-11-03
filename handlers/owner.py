# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""Owner admin commands for aisha.

Owner dot-admin command set, adapted to pyrogram and aisha's
``/``-prefix style. The CRITICAL behaviour is the **owner bypass**:

  The bot OWNER can run any of these commands in any group the bot is
  in — even if the owner themselves is not an admin there — as long
  as the bot itself has the required permission in that group. If the
  bot lacks the right, Telegram's API rejects the call and we surface
  a clean error message.

  Non-owners are gated by the same admin check the rest of the bot
  uses (i.e. they must be an admin with the relevant permission).
  Non-admins get a visible ADMIN_ONLY reply.
"""
import logging
from datetime import datetime, timedelta, timezone

from pyrogram import filters
from pyrogram.enums import ChatMemberStatus, ChatType
from pyrogram.errors import (
    ChatAdminRequired,
    ChatNotModified,
    PeerIdInvalid,
    UserAdminInvalid,
)
from pyrogram.types import ChatPermissions, ChatPrivileges, Message

import config
from core import owner as owner_mod
from core import helpers
from core.helpers import mention

logger = logging.getLogger(__name__)


# ── Permission presets ─────────────────────────────────────────────────────

_LIMITED_PRIVS = ChatPrivileges(
    can_change_info=False,
    can_delete_messages=True,
    can_invite_users=True,
    can_pin_messages=True,
    can_restrict_members=False,
    can_promote_members=False,
    can_manage_chat=True,
    can_manage_video_chats=True,
    is_anonymous=False,
)

_FULL_PRIVS = ChatPrivileges(
    can_change_info=True,
    can_delete_messages=True,
    can_invite_users=True,
    can_restrict_members=True,
    can_pin_messages=True,
    can_promote_members=True,
    can_manage_chat=True,
    can_manage_video_chats=True,
    is_anonymous=False,
)

_DEMOTE_PRIVS = ChatPrivileges(
    can_change_info=False,
    can_delete_messages=False,
    can_invite_users=False,
    can_pin_messages=False,
    can_restrict_members=False,
    can_promote_members=False,
    can_manage_chat=False,
    can_manage_video_chats=False,
    is_anonymous=False,
)

_MUTE_PERMS = ChatPermissions(
    can_send_messages=False,
    can_send_audios=False,
    can_send_documents=False,
    can_send_photos=False,
    can_send_videos=False,
    can_send_video_notes=False,
    can_send_voice_notes=False,
    can_send_polls=False,
    can_send_other_messages=False,
    can_add_web_page_previews=False,
    can_change_info=False,
    can_invite_users=False,
    can_pin_messages=False,
    can_manage_topics=False,
)

_UNMUTE_PERMS = ChatPermissions(
    can_send_messages=True,
    can_send_audios=True,
    can_send_documents=True,
    can_send_photos=True,
    can_send_videos=True,
    can_send_video_notes=True,
    can_send_voice_notes=True,
    can_send_polls=True,
    can_send_other_messages=True,
    can_add_web_page_previews=True,
    can_change_info=False,
    can_invite_users=True,
    can_pin_messages=False,
    can_manage_topics=False,
)


# ── Helpers ───────────────────────────────────────────────────────────────

async def _is_owner(uid: int) -> bool:
    return await owner_mod.is_owner(uid)


async def _blocked(m: Message, uid: int, actor_id: int) -> bool:
    """Refuse mute/ban/demote (etc.) aimed at the bot owner."""
    if uid and await _is_owner(uid) and not await _is_owner(actor_id):
        await m.reply_text(helpers.HARM_OWNER)
        return True
    return False


async def _is_group(m: Message) -> bool:
    t = m.chat.type
    if isinstance(t, ChatType):
        return t in (ChatType.GROUP, ChatType.SUPERGROUP)
    return t in ("group", "supergroup")


async def _bot_can(app, m: Message, right: str) -> bool:
    """True if the bot itself has the given right in this chat."""
    try:
        me = await app.get_chat_member(m.chat.id, app.me.id)
    except Exception:
        return False
    if me.status != ChatMemberStatus.ADMINISTRATOR:
        return False
    if right == "can_promote_members":
        return bool(getattr(me.privileges, "can_promote_members", False))
    if right == "can_restrict_members":
        return bool(getattr(me.privileges, "can_restrict_members", False))
    if right == "can_ban_members":
        return bool(getattr(me.privileges, "can_ban_members", False))
    if right == "can_delete_messages":
        return bool(getattr(me.privileges, "can_delete_messages", False))
    if right == "can_pin_messages":
        return bool(getattr(me.privileges, "can_pin_messages", False))
    return True


async def _user_is_admin(app, chat_id: int, uid: int) -> bool:
    try:
        m = await app.get_chat_member(chat_id, uid)
    except Exception:
        return False
    return m.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)


def _parse_duration(s: str) -> int | None:
    """Return seconds for '1h', '30m', '7d', or None."""
    if not s:
        return None
    s = s.strip().lower()
    if not s:
        return None
    try:
        if s.endswith("d"):
            return int(s[:-1]) * 86400
        if s.endswith("h"):
            return int(s[:-1]) * 3600
        if s.endswith("m"):
            return int(s[:-1]) * 60
        return int(s)
    except ValueError:
        return None


async def _resolve(app, m: Message):
    """Return (uid, name) or (None, None)."""
    if m.reply_to_message and m.reply_to_message.from_user:
        u = m.reply_to_message.from_user
        return u.id, u.first_name or "user"
    parts = (m.text or "").split()
    if len(parts) < 2:
        return None, None
    ref = parts[1]
    if ref.startswith("@"):
        try:
            user = await app.get_users(ref)
        except Exception:
            return None, None
        if not user:
            return None, None
        return user.id, user.first_name or "user"
    try:
        uid = int(ref)
    except ValueError:
        return None, None
    try:
        user = await app.get_users(uid)
    except Exception:
        user = None
    name = (user.first_name if user else None) or "user"
    return uid, name


# ── Owner-bypass admin check ───────────────────────────────────────────────

async def _admin_ok(app, m: Message, needed_right: str) -> tuple[bool, bool]:
    """Return (allowed, is_owner). The owner ALWAYS passes; everyone else
    must be a group admin with the given right."""
    u = m.from_user
    if u is None:
        return False, False
    if await _is_owner(u.id):
        return True, True
    if not await _is_group(m):
        return False, False
    if not await _user_is_admin(app, m.chat.id, u.id):
        return False, False
    if needed_right:
        try:
            cm = await app.get_chat_member(m.chat.id, u.id)
        except Exception:
            return False, False
        if not getattr(cm.privileges, needed_right, False):
            return False, False
    return True, False


def _deny(m: Message):
    return m.reply_text(helpers.ADMIN_ONLY)


# ── Commands ───────────────────────────────────────────────────────────────

USAGE_PROMOTE = "/promote @user [title] — or reply with /promote [title]"
USAGE_FULLPROMOTE = "/fullpromote @user [title] — or reply with /fullpromote [title]"
USAGE_DEMOTE = "/demote @user — or reply with /demote"
USAGE_BAN = "/ban @user [duration] — or reply with /ban [duration]"
USAGE_UNBAN = "/unban @user — or reply with /unban"
USAGE_MUTE = "/mute @user [duration] — or reply with /mute [duration]"
USAGE_UNMUTE = "/unmute @user — or reply with /unmute"
USAGE_KICK = "/kick @user — or reply with /kick"


async def _cmd_promote(app, m: Message):
    if not await _is_group(m):
        return await m.reply_text("❌ Works only in groups.")
    allowed, _ = await _admin_ok(app, m, "can_promote_members")
    if not allowed:
        return await _deny(m)
    uid, name = await _resolve(app, m)
    if uid is None:
        return await m.reply_text(USAGE_PROMOTE)
    if await _blocked(m, uid, m.from_user.id if m.from_user else 0):
        return
    # owner self-promote shortcut: if owner used /promote with no real target
    # but the resolver already resolved to the owner via reply, fall through.
    parts = (m.text or "").split()
    title = " ".join(parts[2:]).strip() or None
    try:
        await app.promote_chat_member(m.chat.id, uid, privileges=_LIMITED_PRIVS)
    except ChatAdminRequired:
        return await m.reply_text(
            "❌ I don't have promote rights in this group. "
            "Make me an admin with Add Members first.")
    except UserAdminInvalid:
        return await m.reply_text("❌ Cannot promote that user.")
    except PeerIdInvalid:
        return await m.reply_text("❌ User not found.")
    except Exception as e:
        return await m.reply_text(f"❌ Promote failed: <code>{e}</code>")
    if title:
        try:
            await app.set_administrator_title(m.chat.id, uid, title)
        except Exception:
            pass
    text = f"⬆️ Promoted {name} in <b>{m.chat.title}</b>"
    if title:
        text += f"\nTitle: <b>{title}</b>"
    await m.reply_text(text)


async def _cmd_fullpromote(app, m: Message):
    if not await _is_group(m):
        return await m.reply_text("❌ Works only in groups.")
    allowed, _ = await _admin_ok(app, m, "can_promote_members")
    if not allowed:
        return await _deny(m)
    uid, name = await _resolve(app, m)
    if uid is None:
        return await m.reply_text(USAGE_FULLPROMOTE)
    if await _blocked(m, uid, m.from_user.id if m.from_user else 0):
        return
    parts = (m.text or "").split()
    title = " ".join(parts[2:]).strip() or None
    try:
        await app.promote_chat_member(m.chat.id, uid, privileges=_FULL_PRIVS)
    except ChatAdminRequired:
        return await m.reply_text("❌ I don't have promote rights in this group.")
    except UserAdminInvalid:
        return await m.reply_text("❌ Cannot promote that user.")
    except PeerIdInvalid:
        return await m.reply_text("❌ User not found.")
    except Exception as e:
        return await m.reply_text(f"❌ Fullpromote failed: <code>{e}</code>")
    if title:
        try:
            await app.set_administrator_title(m.chat.id, uid, title)
        except Exception:
            pass
    text = f"⏫ Fully promoted {name} in <b>{m.chat.title}</b>"
    if title:
        text += f"\nTitle: <b>{title}</b>"
    await m.reply_text(text)


async def _cmd_demote(app, m: Message):
    if not await _is_group(m):
        return await m.reply_text("❌ Works only in groups.")
    allowed, _ = await _admin_ok(app, m, "can_promote_members")
    if not allowed:
        return await _deny(m)
    uid, name = await _resolve(app, m)
    if uid is None:
        return await m.reply_text(USAGE_DEMOTE)
    if await _blocked(m, uid, m.from_user.id if m.from_user else 0):
        return
    try:
        await app.promote_chat_member(m.chat.id, uid, privileges=_DEMOTE_PRIVS)
    except ChatAdminRequired:
        return await m.reply_text("❌ I don't have promote rights in this group.")
    except UserAdminInvalid:
        return await m.reply_text("❌ That user isn't an admin.")
    except ChatNotModified:
        pass
    except Exception as e:
        return await m.reply_text(f"❌ Demote failed: <code>{e}</code>")
    await m.reply_text(f"⬇️ Demoted {name} in <b>{m.chat.title}</b>")


async def _cmd_ban(app, m: Message):
    if not await _is_group(m):
        return await m.reply_text("❌ Works only in groups.")
    allowed, _ = await _admin_ok(app, m, "can_ban_members")
    if not allowed:
        return await _deny(m)
    uid, name = await _resolve(app, m)
    if uid is None:
        return await m.reply_text(USAGE_BAN)
    if await _blocked(m, uid, m.from_user.id if m.from_user else 0):
        return
    parts = (m.text or "").split()
    # If reply used, parts[1] is the duration; otherwise parts[2] is.
    if m.reply_to_message:
        dur_str = parts[1] if len(parts) > 1 else None
    else:
        dur_str = parts[2] if len(parts) > 2 else None
    secs = _parse_duration(dur_str) if dur_str else None
    try:
        if secs:
            until = datetime.now(timezone.utc) + timedelta(seconds=secs)
            await app.ban_chat_member(m.chat.id, uid, until_date=until)
        else:
            await app.ban_chat_member(m.chat.id, uid)
    except ChatAdminRequired:
        return await m.reply_text("❌ I don't have ban rights in this group.")
    except UserAdminInvalid:
        return await m.reply_text("❌ Cannot ban that user.")
    except PeerIdInvalid:
        return await m.reply_text("❌ User not found.")
    except Exception as e:
        return await m.reply_text(f"❌ Ban failed: <code>{e}</code>")
    extra = f" for <b>{dur_str}</b>" if dur_str else ""
    await m.reply_text(f"🚫 Banned {name}{extra} in <b>{m.chat.title}</b>")


async def _cmd_unban(app, m: Message):
    if not await _is_group(m):
        return await m.reply_text("❌ Works only in groups.")
    allowed, _ = await _admin_ok(app, m, "can_ban_members")
    if not allowed:
        return await _deny(m)
    uid, name = await _resolve(app, m)
    if uid is None:
        return await m.reply_text(USAGE_UNBAN)
    try:
        await app.unban_chat_member(m.chat.id, uid)
    except ChatAdminRequired:
        return await m.reply_text("❌ I don't have ban rights in this group.")
    except PeerIdInvalid:
        return await m.reply_text("❌ User not found.")
    except Exception as e:
        return await m.reply_text(f"❌ Unban failed: <code>{e}</code>")
    await m.reply_text(f"✅ Unbanned {name} in <b>{m.chat.title}</b>")


async def _cmd_mute(app, m: Message):
    if not await _is_group(m):
        return await m.reply_text("❌ Works only in groups.")
    allowed, _ = await _admin_ok(app, m, "can_restrict_members")
    if not allowed:
        return await _deny(m)
    uid, name = await _resolve(app, m)
    if uid is None:
        return await m.reply_text(USAGE_MUTE)
    if await _blocked(m, uid, m.from_user.id if m.from_user else 0):
        return
    parts = (m.text or "").split()
    if m.reply_to_message:
        dur_str = parts[1] if len(parts) > 1 else None
    else:
        dur_str = parts[2] if len(parts) > 2 else None
    secs = _parse_duration(dur_str) if dur_str else None
    try:
        if secs:
            until = datetime.now(timezone.utc) + timedelta(seconds=secs)
            await app.restrict_chat_member(
                m.chat.id, uid, _MUTE_PERMS, until_date=until)
        else:
            await app.restrict_chat_member(m.chat.id, uid, _MUTE_PERMS)
    except ChatAdminRequired:
        return await m.reply_text("❌ I don't have restrict rights in this group.")
    except UserAdminInvalid:
        return await m.reply_text("❌ Cannot mute that user.")
    except PeerIdInvalid:
        return await m.reply_text("❌ User not found.")
    except Exception as e:
        return await m.reply_text(f"❌ Mute failed: <code>{e}</code>")
    extra = f" for <b>{dur_str}</b>" if dur_str else " permanently"
    await m.reply_text(f"🔇 Muted {name}{extra} in <b>{m.chat.title}</b>")


async def _cmd_unmute(app, m: Message):
    if not await _is_group(m):
        return await m.reply_text("❌ Works only in groups.")
    allowed, _ = await _admin_ok(app, m, "can_restrict_members")
    if not allowed:
        return await _deny(m)
    uid, name = await _resolve(app, m)
    if uid is None:
        return await m.reply_text(USAGE_UNMUTE)
    try:
        await app.restrict_chat_member(m.chat.id, uid, _UNMUTE_PERMS)
    except ChatAdminRequired:
        return await m.reply_text("❌ I don't have restrict rights in this group.")
    except UserAdminInvalid:
        return await m.reply_text("❌ Cannot unmute that user.")
    except PeerIdInvalid:
        return await m.reply_text("❌ User not found.")
    except Exception as e:
        return await m.reply_text(f"❌ Unmute failed: <code>{e}</code>")
    await m.reply_text(f"🔊 Unmuted {name} in <b>{m.chat.title}</b>")


async def _cmd_kick(app, m: Message):
    """Ban + immediate unban = kick."""
    if not await _is_group(m):
        return await m.reply_text("❌ Works only in groups.")
    allowed, _ = await _admin_ok(app, m, "can_ban_members")
    if not allowed:
        return await _deny(m)
    uid, name = await _resolve(app, m)
    if uid is None:
        return await m.reply_text(USAGE_KICK)
    if await _blocked(m, uid, m.from_user.id if m.from_user else 0):
        return
    try:
        await app.ban_chat_member(m.chat.id, uid)
        await app.unban_chat_member(m.chat.id, uid)
    except ChatAdminRequired:
        return await m.reply_text("❌ I don't have ban rights in this group.")
    except UserAdminInvalid:
        return await m.reply_text("❌ Cannot kick that user.")
    except PeerIdInvalid:
        return await m.reply_text("❌ User not found.")
    except Exception as e:
        return await m.reply_text(f"❌ Kick failed: <code>{e}</code>")
    await m.reply_text(f"👢 Kicked {name} from <b>{m.chat.title}</b>")


# ── Registration ───────────────────────────────────────────────────────────

_HANDLERS = {
    "promote":     _cmd_promote,
    "fullpromote": _cmd_fullpromote,
    "demote":      _cmd_demote,
    "ban":         _cmd_ban,
    "unban":       _cmd_unban,
    "mute":        _cmd_mute,
    "unmute":      _cmd_unmute,
    "kick":        _cmd_kick,
}


def register(add, filters, add_cb, **kwargs) -> int:
    n = 0
    for cmd, fn in _HANDLERS.items():
        add(fn, filters.command([cmd]) & filters.group)
        n += 1
    return n
