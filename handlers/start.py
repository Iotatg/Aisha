# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""Start & help commands — first contact with Aisha."""

HELP_SECTIONS = [
    ("🎀 ɢᴇɴᴇʀᴀʟ", "/start • /help • /about • /ping • /me • /topxp • /id"),
    ("💰 ᴇᴄᴏɴᴏᴍʏ", "/balance • /daily • /pay • /leaders • /gamble"),
    ("🎲 ᴅɪᴄᴇ ᴀʀᴄᴀᴅᴇ", "/dicebet • /dart • /basket • /foot • /bowl"),
    ("👥 ᴅᴜᴇʟ", "/duel <bet> (ʀɪᴠᴀʟ ᴛᴀᴘꜱ ᴊᴏɪɴ)"),
    ("🌸 ɢᴀᴍᴇꜱ", "/trivia • /luckybox • /wordchain • /typerace"),
    ("💋 ꜰᴜɴ & ꜱᴏᴄɪᴀʟ", "/slap • /punch • /kick • /murder • /kiss • /bite "
                       "• /hug • /pat • /ship • /charm • /truth • /dare "
                       "• /puzzle • /roast • /8ball • /afk"),
]


def help_text() -> str:
    lines = ["🎀 <b>ᴀɪꜱʜᴀ'ꜱ ᴍᴀɢɪᴄ ʙᴏx</b> ✨"]
    for title, body in HELP_SECTIONS:
        lines.append(f"\n{title}\n{body}")
    return "\n".join(lines)


ABOUT_TEXT = (
    "💗 <b>ᴀɪꜱʜᴀ</b> — ꜱᴏꜰᴛ, ꜱᴀꜱꜱʏ & ᴀʟᴡᴀʏꜱ ʜᴇʀᴇ ᴛᴏ ᴘʟᴀʏ.\n"
    "ʙᴜɪʟᴛ ᴡɪᴛʜ ᴋᴜʀɪɢʀᴀᴍ + ᴍᴏɴɢᴏᴅʙ 🌸"
)


async def cmd_help(client, message):
    await message.reply(help_text())


async def cmd_about(client, message):
    await message.reply(ABOUT_TEXT)


async def cmd_ping(client, message):
    import time
    t0 = time.perf_counter()
    m = await message.reply("🏓 ᴘᴏɴɢ...")
    dt = (time.perf_counter() - t0) * 1000
    try:
        await m.edit_text(f"🏓 ᴘᴏɴɢ! {dt:.0f} ᴍꜱ ✨")
    except Exception:
        pass


async def cmd_id(client, message):
    u = message.from_user
    cid = message.chat.id
    tgt = u
    if message.reply_to_message:
        tgt = message.reply_to_message.from_user
    await message.reply(
        "🪪 <b>ɪᴅ ᴄᴀʀᴅ</b>\n\n"
        f"👤 ᴜꜱᴇʀ: <code>{tgt.id}</code>\n"
        f"💬 ᴄʜᴀᴛ: <code>{cid}</code>"
    )


def register(add, filters, add_cb) -> int:
    add(cmd_help, filters.command(["help"]))
    add(cmd_about, filters.command(["about"]))
    add(cmd_ping, filters.command(["ping"]))
    add(cmd_id, filters.command(["id"]))
    return 4
