# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""Tamagotchi companion: /pet (status), /feed, /play, /petname <name>.

Stats decay with real time; neglect makes the pet miserable (and it can
'pass away' if ignored for 2 days, after which the next /pet revives it).
"""
import logging
import time

from core.db import db
from core.fonts import smallcaps as _sc

logger = logging.getLogger(__name__)

_HUNGER_RATE = 0.05   # points lost per minute
_HAPPY_RATE = 0.04
_DEATH_AFTER = 2 * 86400  # seconds of total neglect


def _decay(pet):
    now = time.time()
    elapsed = (now - pet.get("last", now)) / 60.0
    if elapsed > 0:
        pet["hunger"] = max(0, pet["hunger"] - elapsed * _HUNGER_RATE)
        pet["happy"] = max(0, pet["happy"] - elapsed * _HAPPY_RATE)
    pet["last"] = now
    if pet["hunger"] <= 0 and pet["happy"] <= 0 and \
            (now - pet.get("seen", now)) > _DEATH_AFTER:
        pet["alive"] = False
    pet["seen"] = now
    return pet


def _bar(v):
    filled = int(v // 10)
    return "█" * filled + "░" * (10 - filled)


async def _get_pet(uid):
    col = db().pets
    pet = await col.find_one({"_id": uid})
    if pet is None:
        pet = {"_id": uid, "name": "ᴘᴇᴛ", "hunger": 80, "happy": 80,
               "alive": True, "last": time.time(), "seen": time.time()}
        await col.insert_one(pet)
    return _decay(pet)


async def _save(pet):
    await db().pets.update_one(
        {"_id": pet["_id"]},
        {"$set": {"name": pet["name"], "hunger": round(pet["hunger"], 1),
                  "happy": round(pet["happy"], 1), "alive": pet["alive"],
                  "last": pet["last"], "seen": pet["seen"]}},
    )


def register(add, filters, add_cb):
    add(cmd_pet, filters.command("pet"))
    add(cmd_feed, filters.command("feed"))
    add(cmd_play, filters.command("play"))
    add(cmd_petname, filters.command("petname"))


async def cmd_pet(client, message):
    pet = await _get_pet(message.from_user.id)
    if not pet["alive"]:
        await message.reply(f"💀 <b>{_sc('your pet passed away')}</b>\n\n"
                             f"{_sc('send /feed to adopt a new one')}")
        return
    mood = "😊" if pet["happy"] > 60 else "😐" if pet["happy"] > 30 else "😢"
    await message.reply(
        f"{mood} <b>{pet['name']}</b>\n\n"
        f"🍖 {_sc('hunger')} {_bar(pet['hunger'])} {int(pet['hunger'])}%\n"
        f"💛 {_sc('happy')}  {_bar(pet['happy'])} {int(pet['happy'])}%"
    )


async def cmd_feed(client, message):
    pet = await _get_pet(message.from_user.id)
    if not pet["alive"]:
        pet["alive"] = True
        pet["hunger"] = 70
        pet["happy"] = 70
        await _save(pet)
        await message.reply(f"🐣 <b>{_sc('a new pet was born')}</b> — {pet['name']}")
        return
    pet["hunger"] = min(100, pet["hunger"] + 25)
    await _save(pet)
    await message.reply(f"🍖 {pet['name']} {_sc('ate well')}! ({int(pet['hunger'])}%)")


async def cmd_play(client, message):
    pet = await _get_pet(message.from_user.id)
    if not pet["alive"]:
        await message.reply(f"💀 {_sc('your pet is gone, /feed to adopt')}")
        return
    pet["happy"] = min(100, pet["happy"] + 20)
    pet["hunger"] = max(0, pet["hunger"] - 5)
    await _save(pet)
    await message.reply(f"🎾 {pet['name']} {_sc('had fun')}! ({int(pet['happy'])}%)")


async def cmd_petname(client, message):
    parts = message.text.split(maxsplit=1)
    name = parts[1].strip()[:20] if len(parts) > 1 else ""
    if not name:
        await message.reply(f"🏷️ {_sc('use')}: /petname <name>")
        return
    pet = await _get_pet(message.from_user.id)
    pet["name"] = name
    await _save(pet)
    await message.reply(f"🏷️ {_sc('pet renamed to')} {name}")
