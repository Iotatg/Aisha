# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""Text styling commands: /font (unicode styles) and /figlet (block art).

/font <text>        -> shows the text in every available style
/font <style> <text> -> applies one style (bold, bubble, square, full,
                        tiny, zalgo, strike, under, flip)
/figlet <text>      -> big block-art banner (max 30 chars)
"""
import logging

from core.fonts import style, style_help, figlet, smallcaps

logger = logging.getLogger(__name__)


def register(add, filters, add_cb):
    add(cmd_font, filters.command("font"))
    add(cmd_figlet, filters.command("figlet"))


async def cmd_font(client, message):
    parts = message.text.split(maxsplit=1)
    arg = parts[1].strip() if len(parts) > 1 else ""
    if not arg:
        await message.reply(
            f"🎨 <b>{smallcaps('font')}</b>\n\n"
            f"{smallcaps('use')}: /font <text>\n"
            f"{smallcaps('or')}: /font <style> <text>\n\n"
            f"{smallcaps('styles')}: {style_help()}"
        )
        return
    first, _, rest = arg.partition(" ")
    if first.lower() in ("bold", "bubble", "square", "full", "tiny",
                          "zalgo", "strike", "under", "flip") and rest:
        try:
            out = style(first, rest)
        except Exception:
            out = rest
        await message.reply(f"<code>{out}</code>")
        return
    lines = "\n".join(
        f"<b>{smallcaps(name)}</b>: <code>{style(name, arg)}</code>"
        for name in ("bold", "bubble", "square", "full", "tiny",
                     "zalgo", "strike", "under", "flip")
    )
    await message.reply(f"🎨 <b>{smallcaps('font styles')}</b>\n\n{lines}")


async def cmd_figlet(client, message):
    parts = message.text.split(maxsplit=1)
    text = parts[1].strip() if len(parts) > 1 else ""
    if not text:
        await message.reply(f"🔠 <b>{smallcaps('figlet')}</b>\n\n"
                             f"{smallcaps('use')}: /figlet <text>")
        return
    art = figlet(text)
    await message.reply(f"<pre>{art}</pre>")
