# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""Truth or Dare: /td picks a random prompt, /td truth or /td dare is explicit."""
import logging
import random

from core.fonts import smallcaps as _sc

logger = logging.getLogger(__name__)

TRUTHS = [
    "what's the most embarrassing song on your playlist?",
    "who was your last crush in this group?",
    "what's a lie you told to get out of plans?",
    "biggest fear nobody here knows about?",
    "have you ever pretended to be asleep to avoid someone?",
    "what's the cringiest thing you posted online?",
    "who in this chat would you swap phones with for a day?",
    "what's a secret talent you pretend not to have?",
    "worst pickup line you've ever used?",
    "have you ever stalked a stranger's profile for an hour?",
]
DARES = [
    "send the last emoji you copied to the group.",
    "say 'i love you' to the person you last replied to.",
    "change your nickname to 'aisha's pet' for 10 minutes.",
    "type your search history from the last 5 minutes.",
    "send a voice note humming your favorite song.",
    "compliment the person on your left.",
    "post a baby photo of yourself (or a random cute pic).",
    "let the group pick your next status for a day.",
    "do 10 jumping jacks and prove it with a pic.",
    "text your mom 'i love you' and screenshot it here.",
]


def register(add, filters, add_cb):
    add(cmd_td, filters.command("td"))


async def cmd_td(client, message):
    parts = message.text.split(maxsplit=1)
    kind = parts[1].strip().lower() if len(parts) > 1 else ""
    if kind == "truth":
        pick = random.choice(TRUTHS)
        label = _sc("truth")
    elif kind == "dare":
        pick = random.choice(DARES)
        label = _sc("dare")
    else:
        if random.random() < 0.5:
            pick, label = random.choice(TRUTHS), _sc("truth")
        else:
            pick, label = random.choice(DARES), _sc("dare")
    await message.reply(f"🎲 <b>{label}</b>\n\n{pick}")
