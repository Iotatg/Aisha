# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""Kingdom / Empire war game (Riruru) — rewritten for aisha.

Commands:
  /start (empire dashboard)  /village  /guide
  /collect  /storage  /vault  /mines  /build
  /walls  /defense  /train  /troops
  /kingdom (spy target)  /spy  /attack
  /emperors  /settle  /convert  /daily  /market
  /wallet (convert coins between village and global economy)
  /shield (show your protection status)
  /raid (PvE: solo a bandit camp for resources + xp)
  /quests (today's daily quests and rewards)

All user-facing strings use ``core/ui.py`` helpers so the kingdom
module looks like the rest of the bot. Game state lives in the
``village`` collection; ``village.balance`` is the kingdom-side
wallet, separate from the global ``users.balance`` (convertible
via ``/wallet``).
"""
import logging
import random
import time

from pyrogram.enums import ChatType

from core import money, ui
from core.db import db
from core.helpers import fmt, mention

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
#  Constants
# ═══════════════════════════════════════════════════════════════════════════

CITIZEN_START = 50
STORAGE_BASE = 2000
STORAGE_PER_HUT_LV = 800  # each hut level adds this much to storage_cap

# Mine hourly yields per level
MINE_YIELD = {
    "woodyard":  {1: 10, 2: 25, 3: 50, 4: 90, 5: 150},
    "quarry":    {1: 8,  2: 20, 3: 40, 4: 75, 5: 120},
    "iron_mine": {1: 5,  2: 12, 3: 25, 4: 50, 5: 90},
}

# Building upgrade costs (wood, stone, iron) — index = next level
BUILD_COSTS = {
    "home":      {2: (500, 0, 0),     3: (1500, 500, 0),   4: (3000, 1000, 500)},
    "camp":      {2: (300, 0, 0),     3: (1000, 300, 0),   4: (2500, 800, 300)},
    "hut":       {2: (200, 0, 0),     3: (800, 200, 0),    4: (2000, 600, 200)},
    "woodyard":  {2: (0, 300, 0),     3: (0, 800, 0),      4: (0, 2000, 500), 5: (0, 5000, 1000)},
    "quarry":    {2: (300, 0, 0),     3: (800, 0, 0),      4: (2000, 0, 500), 5: (5000, 0, 1000)},
    "iron_mine": {2: (500, 300, 0),   3: (1200, 800, 0),   4: (3000, 2000, 500)},
}

# Troop stats
TROOP_TYPES = {
    "warriors": {"hp": 50,  "damage": 15, "cost_coins": 100},
    "archers":  {"hp": 30,  "damage": 25, "cost_coins": 150},
    "knights":  {"hp": 100, "damage": 20, "cost_coins": 200},
    "mages":    {"hp": 40,  "damage": 40, "cost_coins": 300},
}

# Wall stats
WALL_TYPES = {
    "wood":  {"hp": 300,  "damage": 5,  "cost_resource": ("wood", 200)},
    "stone": {"hp": 700,  "damage": 8,  "cost_resource": ("stone", 300)},
    "iron":  {"hp": 1500, "damage": 12, "cost_resource": ("iron", 400)},
}

# Defense stats — paid in coins (village.balance)
DEFENSE_TYPES = {
    "archer_tower": {"hp": 300, "damage_base": 20, "cost_coins": 500},
    "cannon":       {"hp": 500, "damage_base": 35, "cost_coins": 800},
}

# Market — buy with coins (village.balance), sell returns to same wallet
MARKET_PRICES = {"wood": 50, "stone": 120, "iron": 300}
MARKET_SELL_RATIO = 0.7

# Cooldowns (seconds)
COOLDOWN_MINE = 300
COOLDOWN_ATTACK = 300
COOLDOWN_DAILY = 86_400
COOLDOWN_QUEST = 86_400

# Shield duration after a successful attack on you (seconds)
SHIELD_DURATION = 3_600

# Combat tuning
COMBAT_MAX_ROUNDS = 200
LOOT_FRACTION = 0.5  # 50% of defender resources/treasury
ATTACK_XP_WIN = 20
KINGDOM_LEVEL_XP_BASE = 500  # xp needed for kingdom_level 1 -> 2
ATTACKS_MAX_BASE = 300

# Stage thresholds (kingdom_level -> stage name)
STAGE_BY_LEVEL = {1: "Village", 2: "Town", 3: "City", 4: "Fortress", 5: "Empire"}


# ═══════════════════════════════════════════════════════════════════════════
#  DB layer — atomic, typed, single source of truth
# ═══════════════════════════════════════════════════════════════════════════

def _defaults(uid: int) -> dict:
    return {
        "_id": uid,
        "wood": 0, "stone": 0, "iron": 0,
        "treasury": 0, "vault": 0, "balance": 0, "gems": 0,
        "citizens": CITIZEN_START, "max_citizens": CITIZEN_START, "workers": 0,
        "troops": {},
        "home_level": 1, "camp_level": 1, "hut_level": 1,
        "woodyard_level": 1, "quarry_level": 1, "iron_mine_level": 1,
        "walls": {}, "defense": {},
        "storage_cap": STORAGE_BASE,
        "last_mine": 0, "last_attack": 0, "last_daily": 0, "last_quest": 0,
        "protected_until": 0,
        "stage": "Village", "kingdom_level": 1, "xp": 0,
        "attacks_used": 0, "attacks_max": ATTACKS_MAX_BASE,
        "created_at": int(time.time()),
    }


async def _ensure_village(uid: int) -> dict:
    coll = db().village
    v = await coll.find_one({"_id": uid})
    if v:
        # Backfill any field the schema gained after the doc was first written.
        backfill = {k: val for k, val in _defaults(uid).items()
                    if k != "_id" and k not in v}
        if backfill:
            await coll.update_one({"_id": uid}, {"$set": backfill})
            v.update(backfill)
        return v
    doc = _defaults(uid)
    await coll.insert_one(doc)
    return doc


async def get_village(uid: int) -> dict:
    """Public read accessor used by ttt/bingo for wagers."""
    return await _ensure_village(uid)


async def _upd(uid: int, **kw) -> None:
    """Atomic field-set upsert. Public alias for ttt/bingo compatibility."""
    if not kw:
        return
    await db().village.update_one({"_id": uid}, {"$set": kw}, upsert=True)


async def _inc(uid: int, **kw) -> None:
    """Atomic $inc. Use for resource/coin balances to avoid race overwrites."""
    if not kw:
        return
    await db().village.update_one({"_id": uid}, {"$inc": kw}, upsert=True)


# Public re-exports for ttt/bingo (don't break them)
_get_village = get_village


# ═══════════════════════════════════════════════════════════════════════════
#  Schema-derivation helpers
# ═══════════════════════════════════════════════════════════════════════════

def recompute_storage_cap(v: dict) -> int:
    """Storage cap now scales with hut_level (the 'warehouse' building)."""
    return STORAGE_BASE + STORAGE_PER_HUT_LV * (v.get("hut_level", 1) - 1)


def stage_for(level: int) -> str:
    return STAGE_BY_LEVEL.get(level, "Empire")


def xp_to_next_level(v: dict) -> int:
    cur = v.get("kingdom_level", 1)
    return KINGDOM_LEVEL_XP_BASE * cur


def _name(u) -> str:
    return (u.first_name or u.username or "ᴜsᴇʀ") if u else "ᴜsᴇʀ"


def _free_citizens(v: dict) -> int:
    return max(0, v["max_citizens"] - sum(v.get("troops", {}).values()) - v.get("workers", 0))


def _worker_factor(v: dict) -> float:
    """Workers speed up construction: each worker trims 3% (floor 60%)."""
    return max(0.6, 1.0 - 0.03 * v.get("workers", 0))


def _in_group(message) -> bool:
    return message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)


def _is_protected(v: dict) -> bool:
    return int(v.get("protected_until", 0)) > int(time.time())


def _wall_str(v: dict) -> str:
    w = v.get("walls") or {}
    if not w:
        return "ɴᴏᴛ ʙᴜɪʟᴛ"
    return " • ".join(f"{k.title()} Lv{w[k].get('level', 1)}" for k in w)


def _def_str(v: dict) -> str:
    d = v.get("defense") or {}
    if not d:
        return "ɴᴏᴛ ʙᴜɪʟᴛ"
    return " • ".join(f"{k.replace('_', ' ').title()} Lv{d[k].get('level', 1)}" for k in d)


def _cooldown_remaining(last: int, cd: int) -> int:
    return max(0, cd - (int(time.time()) - int(last or 0)))


def _fmt_remaining(seconds: int) -> str:
    if seconds <= 0:
        return "ʀᴇᴀᴅʏ"
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}ʜ {m}ᴍ"
    if m:
        return f"{m}ᴍ {s}ꜱ"
    return f"{s}ꜱ"


# ═══════════════════════════════════════════════════════════════════════════
#  Combat engine — pure, testable
# ═══════════════════════════════════════════════════════════════════════════

def _defense_damage_at(level: int, base: int) -> int:
    """Defense damage grows additively: base + 5 per level above 1."""
    return base + max(0, level - 1) * 5


def _resolve_breach(def_hp: int, def_dmg: int, atk_hp: int, atk_dmg: int) -> tuple:
    """Run a two-sided damage exchange up to COMBAT_MAX_ROUNDS.

    Returns ``(attacker_survives: bool, dmg_taken: int)``.
    Both pools count down simultaneously; the breach ends when one
    pool is empty. Caps at ``COMBAT_MAX_ROUNDS`` to prevent infinite
    loops when both pools are nearly equal.

    If ``def_hp <= 0`` the attacker passes through with zero loss,
    so callers can chain phases without re-entering with 0 troops.
    """
    if def_hp <= 0:
        return True, 0
    if atk_hp <= 0 or atk_dmg <= 0:
        return False, 0
    start_hp = atk_hp
    for _ in range(COMBAT_MAX_ROUNDS):
        def_hp -= atk_dmg
        atk_hp -= def_dmg
        if def_hp <= 0 or atk_hp <= 0:
            break
    if atk_hp <= 0:
        return False, start_hp
    return True, start_hp - atk_hp


def _total_defense_block(v: dict) -> tuple:
    """Sum wall HP/damage and defense HP/damage across all built structures."""
    wall_hp = wall_dmg = 0
    for k, w in (v.get("walls") or {}).items():
        wall_hp += w.get("hp", 0)
        wall_dmg += w.get("damage", 0)
    def_hp = def_dmg = 0
    for k, d in (v.get("defense") or {}).items():
        spec = DEFENSE_TYPES.get(k)
        if not spec:
            continue
        def_hp += d.get("hp", 0)
        def_dmg += _defense_damage_at(d.get("level", 1), spec["damage_base"])
    return wall_hp, wall_dmg, def_hp, def_dmg


def simulate_attack(attacker: dict, defender: dict, troop_type: str,
                    count: int) -> dict:
    """Pure combat simulation — no DB writes.

    Returns a dict with: ``win``, ``loot`` (resources), ``dmg_taken``,
    ``troops_lost``, ``xp_gained``.
    """
    spec = TROOP_TYPES.get(troop_type)
    if not spec or count <= 0:
        return {"win": False, "loot": {}, "dmg_taken": 0, "troops_lost": 0, "xp_gained": 0}
    troop_hp = spec["hp"] * count
    troop_dmg = spec["damage"] * count
    wall_hp, wall_dmg, def_hp, def_dmg = _total_defense_block(defender)
    # Phase 1: walls
    wall_ok, walls_dmg_taken = _resolve_breach(wall_hp, wall_dmg, troop_hp, troop_dmg)
    if not wall_ok:
        return {
            "win": False,
            "loot": {},
            "dmg_taken": troop_hp,
            "troops_lost": count,
            "xp_gained": 0,
        }
    troops_after_walls = troop_hp - walls_dmg_taken
    # Phase 2: defense
    def_ok, def_dmg_taken = _resolve_breach(def_hp, def_dmg, troops_after_walls, troop_dmg)
    if not def_ok:
        return {
            "win": False,
            "loot": {},
            "dmg_taken": troop_hp,
            "troops_lost": count,
            "xp_gained": 0,
        }
    dmg_taken = walls_dmg_taken + def_dmg_taken
    troops_lost = int(count * dmg_taken / troop_hp) if troop_hp else count
    troops_lost = min(count, max(0, troops_lost))
    loot = {
        "wood": int(defender.get("wood", 0) * LOOT_FRACTION),
        "stone": int(defender.get("stone", 0) * LOOT_FRACTION),
        "iron": int(defender.get("iron", 0) * LOOT_FRACTION),
        "coins": int(defender.get("treasury", 0) * LOOT_FRACTION),
    }
    return {
        "win": True,
        "loot": loot,
        "dmg_taken": dmg_taken,
        "troops_lost": troops_lost,
        "xp_gained": ATTACK_XP_WIN,
    }


# ═══════════════════════════════════════════════════════════════════════════
#  Rank computation
# ═══════════════════════════════════════════════════════════════════════════

async def _empire_rank(v: dict) -> int:
    total = v.get("vault", 0) + v.get("treasury", 0)
    pipeline = [
        {"$addFields": {"net": {"$add": ["$vault", "$treasury"]}}},
        {"$match": {"net": {"$gt": total}}},
        {"$count": "rank"},
    ]
    try:
        cursor = db().village.aggregate(pipeline)
        docs = await cursor.to_list(length=1)
    except Exception:
        return 1
    return (docs[0]["rank"] + 1) if docs else 1


# ═══════════════════════════════════════════════════════════════════════════
#  XP / level / quest progression
# ═══════════════════════════════════════════════════════════════════════════

def _apply_xp_gain(v: dict, xp: int) -> tuple:
    """Compute (new_xp, new_level, leveled_up: bool). Pure function."""
    new_xp = int(v.get("xp", 0)) + int(xp)
    level = int(v.get("kingdom_level", 1))
    leveled = False
    while new_xp >= KINGDOM_LEVEL_XP_BASE * level:
        new_xp -= KINGDOM_LEVEL_XP_BASE * level
        level += 1
        leveled = True
    return new_xp, level, leveled


async def _grant_xp(uid: int, xp: int) -> dict:
    """Atomically apply XP, recompute level, update stage and attacks_max.

    Returns ``{"leveled": bool, "level": int, "xp": int}``.
    """
    v = await _ensure_village(uid)
    new_xp, new_level, leveled = _apply_xp_gain(v, xp)
    new_stage = stage_for(new_level)
    new_cap = ATTACKS_MAX_BASE + (new_level - 1) * 50
    await _upd(uid, xp=new_xp, kingdom_level=new_level,
               stage=new_stage, attacks_max=new_cap)
    return {"leveled": leveled, "level": new_level, "xp": new_xp}


# ═══════════════════════════════════════════════════════════════════════════
#  Resource helpers (apply cap, etc.)
# ═══════════════════════════════════════════════════════════════════════════

def _cap_resources(v: dict, delta: dict) -> dict:
    """Clamp each resource to storage_cap. Returns the actually-applied delta."""
    cap = recompute_storage_cap(v)
    out = {}
    for k in ("wood", "stone", "iron"):
        cur = int(v.get(k, 0))
        target = cur + int(delta.get(k, 0))
        out[k] = max(0, min(cap, target) - cur)
    return out


# ═══════════════════════════════════════════════════════════════════════════
#  Commands
# ═══════════════════════════════════════════════════════════════════════════

# ── /start (dashboard) ───────────────────────────────────────────────────

async def cmd_start(client, message):
    u = message.from_user
    v = await _ensure_village(u.id)
    rank = await _empire_rank(v)
    protected_remaining = max(0, int(v.get("protected_until", 0)) - int(time.time()))
    body = [
        ui.chip("ᴇᴍᴘɪʀᴇ ʀᴀɴɪ", f"#{rank}", "🌍"),
        ui.chip("ᴋɪɴɢᴅᴏᴍ ʟᴇᴠᴇʟ", f"{v['kingdom_level']} ({v['stage']})", "🏰"),
        ui.chip("xᴘ", f"{v.get('xp', 0)} / {xp_to_next_level(v)}", "⚡"),
        ui.chip("ᴛʀᴇᴀꜱᴜʀʏ", fmt(v.get("treasury", 0)), "🪙"),
        ui.chip("ᴠᴀᴜʟᴛ", fmt(v.get("vault", 0)), "🏛️"),
        ui.chip("ᴡᴀʟʟᴇᴛ", fmt(v.get("balance", 0)), "💰"),
        ui.chip("ɢᴇᴍꜱ", v.get("gems", 0), "💎"),
        ui.chip("ᴡᴏᴏᴅ", f"{v.get('wood', 0)} / {recompute_storage_cap(v)}", "🪵"),
        ui.chip("ꜱᴛᴏɴᴇ", f"{v.get('stone', 0)} / {recompute_storage_cap(v)}", "🪨"),
        ui.chip("ɪʀᴏɴ", f"{v.get('iron', 0)} / {recompute_storage_cap(v)}", "⚙️"),
        ui.chip("ᴄɪᴛɪᴢᴇɴꜱ",
                f"{_free_citizens(v)} free / {v.get('max_citizens', 0)} max", "👥"),
        ui.chip("ᴡᴏʀᴋᴇʀꜱ", v.get("workers", 0), "🛠️"),
        ui.chip("ᴛʀᴏᴏᴘꜱ", sum((v.get("troops") or {}).values()), "⚔️"),
        ui.chip("ᴡᴀʟʟꜱ", _wall_str(v), "🧱"),
        ui.chip("ᴅᴇꜰᴇɴꜱᴇ", _def_str(v), "🛡️"),
    ]
    if _is_protected(v):
        body.append(ui.chip("🛡️  ꜱʜɪᴇʟᴅ", _fmt_remaining(protected_remaining), "🛡️"))
    body.append(
        f"<i>ʙᴜɪʟᴅ ʏᴏᴜʀ ᴇᴍᴘɪʀᴇ ᴡɪᴛʜ /collect, /train ᴀɴᴅ /attack! "
        f"ᴛɪᴘ: /guide [command] ꜰᴏʀ ʜᴇʟᴘ ᴏɴ ᴀɴʏ ᴄᴏᴍᴍᴀɴᴅ.</i>"
    )
    await message.reply(ui.card("ᴇᴍᴘɪʀᴇ ᴅᴀꜱʜʙᴏᴀʀᴅ", body, icon="🏰"))


cmd_village = cmd_start  # alias


# ── /guide ───────────────────────────────────────────────────────────────

_GUIDE = {
    "collect": "🌾 ʜᴀʀᴠᴇꜱᴛ ʀᴇꜱᴏᴜʀᴄᴇꜱ ꜰʀᴏᴍ ʏᴏᴜʀ ᴍɪɴᴇꜱ. 5 ᴍɪɴ ᴄᴏᴏʟᴅᴏᴡɴ.",
    "storage": "📦 ꜱʜᴏᴡꜱ ʀᴇꜱᴏᴜʀᴄᴇꜱ + ᴄᴀᴘ. ᴄᴀᴘ ɢʀᴏᴡꜱ ᴡɪᴛʜ /build hut.",
    "vault":   "🏛️ ꜱʜᴏᴡꜱ ᴄᴏɪɴ ᴡᴀʟʟᴇᴛꜱ + ʀᴀɴᴋ.",
    "mines":   "⛏️ ꜱʜᴏᴡꜱ ᴍɪɴᴇ ʟᴇᴠᴇʟꜱ + ʜᴏᴜʀʟʏ ʏɪᴇʟᴅꜱ.",
    "build":   "🏗️ ᴜᴘɢʀᴀᴅᴇ ʜᴏᴍᴇ/ᴄᴀᴍᴘ/ʜᴜᴛ/ᴍɪɴᴇꜱ. ᴜꜱᴀɢᴇ: /build <type>",
    "walls":   "🧱 ʙᴜɪʟᴅ/ᴜᴘɢʀᴀᴅᴇ ᴡᴀʟʟꜱ (ᴡᴏᴏᴅ/ꜱᴛᴏɴᴇ/ɪʀᴏɴ). ᴜꜱᴀɢᴇ: /walls <type>",
    "defense": "🛡️ ʙᴜɪʟᴅ ᴀʀᴄʜᴇʀ ᴛᴏᴡᴇʀ / ᴄᴀɴɴᴏɴ. ᴘᴀɪᴅ ɪɴ ᴄᴏɪɴꜱ.",
    "train":   "⚔️ ᴛʀᴀɪɴ ᴡᴀʀʀɪᴏʀꜱ/ᴀʀᴄʜᴇʀꜱ/ᴋɴɪɢʜᴛꜱ/ᴍᴀɢᴇꜱ/ᴡᴏʀᴋᴇʀꜱ. ᴜꜱᴀɢᴇ: /train <type> <n>",
    "troops":  "🪖 ꜱʜᴏᴡꜱ ʏᴏᴜʀ ᴀʀᴍʏ.",
    "kingdom": "🔎 ꜱᴄᴏᴜᴛ ᴀ ʀᴇᴘʟɪᴇᴅ ᴜꜱᴇʀ'ꜱ ᴇᴍᴘɪʀᴇ. ɴᴏ ʀɪꜱᴋ.",
    "spy":     "🕵️ ʟɪᴋᴇ /kingdom ʙᴜᴛ ᴀᴅᴅꜱ ᴀᴛᴛᴀᴄᴋ ᴏᴅᴅꜱ.",
    "attack":  "⚔️ ʀᴀɪᴅ ᴀ ʀᴇᴘʟɪᴇᴅ ᴜꜱᴇʀ. ᴜꜱᴀɢᴇ: /attack <type> <n>",
    "emperors": "👑 ɢʟᴏʙᴀʟ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ.",
    "settle":  "💱 ᴍᴏᴠᴇ ᴄᴏɪɴꜱ ʙᴇᴛᴡᴇᴇɴ ᴛʀᴇᴀꜱᴜʀʏ <-> ᴠᴀᴜʟᴛ. ᴜꜱᴀɢᴇ: /settle <vault|treasury> <amt>",
    "convert": "💱 ʀᴇꜱᴏᴜʀᴄᴇꜱ → ᴠᴀᴜʟᴛ ᴄᴏɪɴꜱ. ᴜꜱᴀɢᴇ: /convert <res> <amt>",
    "daily":   "🎁 ᴅᴍ-ᴏɴʟʏ. ʀᴇꜱᴇᴛꜱ ᴇᴠᴇʀʏ 24ʜ.",
    "market":  "🏪 ʙᴜʏ/ꜱᴇʟʟ ʀᴇꜱᴏᴜʀᴄᴇꜱ. ᴜꜱᴀɢᴇ: /market [buy|sell <res> <qty>]",
    "wallet":  "💱 ᴄᴏɴᴠᴇʀᴛ ʙᴇᴛᴡᴇᴇɴ ᴋɪɴɢᴅᴏᴍ ᴡᴀʟʟᴇᴛ ᴀɴᴅ ɢʟᴏʙᴀʟ ᴇᴄᴏɴᴏᴍʏ. ᴜꜱᴀɢᴇ: /wallet <village|global> <amt>",
    "shield":  "🛡️ ꜱʜᴏᴡ ʏᴏᴜʀ ᴘʀᴏᴛᴇᴄᴛɪᴏɴ ꜱᴛᴀᴛᴜꜱ.",
    "raid":    "🗡️ ᴘᴠᴇ: ꜱᴏʟᴏ ᴀ ʙᴀɴᴅɪᴛ ᴄᴀᴍᴘ. ʀᴇᴡᴀʀᴅ: ʀᴇꜱᴏᴜʀᴄᴇꜱ + xᴘ. 30 ᴍɪɴ ᴄᴏᴏʟᴅᴏᴡɴ.",
    "quests":  "📜 ᴛᴏᴅᴀʏ'ꜱ ᴅᴀɪʟʏ ǫᴜᴇꜱᴛꜱ + ʀᴇᴡᴀʀᴅꜱ.",
}


async def cmd_guide(client, message):
    args = message.command[1:] if len(getattr(message, "command", []) or []) > 1 else []
    if args:
        topic = args[0].lower()
        text = _GUIDE.get(topic)
        if not text:
            await message.reply(
                ui.notice(f"ɴᴏ ɢᴜɪᴅᴇ ꜰᴏʀ '{topic}'.") +
                "\n\n" + ui.scorecard([(k, "") for k in _GUIDE.keys()], "📖 ᴀᴠᴀɪʟᴀʙʟᴇ")
            )
            return
        await message.reply(ui.card(f"/{topic}", [text], icon="📖"))
        return
    body = [ui.chip(name, text.split(" ")[0] if text else "", "✧")
            for name, text in _GUIDE.items()]
    await message.reply(
        ui.notice("ᴜꜱᴀɢᴇ: /guide [command_name]") +
        "\n\n" + "\n".join(body)
    )


# ── /collect ─────────────────────────────────────────────────────────────

async def cmd_collect(client, message):
    u = message.from_user
    v = await _ensure_village(u.id)
    now = int(time.time())
    rem = _cooldown_remaining(v.get("last_mine", 0), COOLDOWN_MINE)
    if rem > 0:
        await message.reply(
            ui.notice(f"ᴍɪɴᴇ ᴄᴏᴏʟᴅᴏᴡɴ — ᴡᴀɪᴛ {_fmt_remaining(rem)}.")
        )
        return
    elapsed = now - int(v.get("last_mine", 0) or now)
    hours = min(24.0, max(0.0, elapsed / 3600.0)) if v.get("last_mine") else 0.0
    if hours <= 0:
        hours = 0.0  # first claim yields nothing until cooldown completes
    w = int(MINE_YIELD["woodyard"][v.get("woodyard_level", 1)] * hours)
    s = int(MINE_YIELD["quarry"][v.get("quarry_level", 1)] * hours)
    i = int(MINE_YIELD["iron_mine"][v.get("iron_mine_level", 1)] * hours)
    free = _free_citizens(v)
    coins = int(free * 2 * hours)
    delta = _cap_resources(v, {"wood": w, "stone": s, "iron": i})
    actual = sum(delta.values())
    if actual == 0 and coins == 0:
        await message.reply(
            ui.notice("ɴᴏᴛʜɪɴɢ ᴛᴏ ᴄᴏʟʟᴇᴄᴛ ʏᴇᴛ — ᴡᴀɪᴛ ᴀ ʙɪᴛ.")
        )
        return
    await _inc(u.id, wood=delta["wood"], stone=delta["stone"], iron=delta["iron"],
               treasury=coins, last_mine=now)
    body = [
        ui.chip("ᴡᴏᴏᴅ", f"+{delta['wood']}", "🪵"),
        ui.chip("ꜱᴛᴏɴᴇ", f"+{delta['stone']}", "🪨"),
        ui.chip("ɪʀᴏɴ", f"+{delta['iron']}", "⚙️"),
        ui.chip("ᴄᴏɪɴꜱ", f"+{coins:,}", "🪙"),
        ui.chip("ᴛɪᴍᴇ", f"{hours:.1f}ʜ", "⏳"),
    ]
    if actual < w + s + i:
        body.append(ui.notice("ꜱᴛᴏʀᴀɢᴇ ᴄᴀᴘ ʀᴇᴀᴄʜᴇᴅ — ᴜᴘɢʀᴀᴅᴇ ʜᴜᴛ ꜰᴏʀ ᴍᴏʀᴇ."))
    await message.reply(ui.card("ᴄᴏʟʟᴇᴄᴛᴇᴅ", body, icon="🌾"))


# ── /storage ─────────────────────────────────────────────────────────────

async def cmd_storage(client, message):
    u = message.from_user
    v = await _ensure_village(u.id)
    cap = recompute_storage_cap(v)
    body = [
        ui.chip("ᴡᴏᴏᴅ", f"{v.get('wood', 0)} / {cap}", "🪵"),
        ui.chip("ꜱᴛᴏɴᴇ", f"{v.get('stone', 0)} / {cap}", "🪨"),
        ui.chip("ɪʀᴏɴ", f"{v.get('iron', 0)} / {cap}", "⚙️"),
        ui.chip("ᴛʀᴇᴀꜱᴜʀʏ", fmt(v.get("treasury", 0)), "🪙"),
        ui.chip("ᴠᴀᴜʟᴛ", fmt(v.get("vault", 0)), "🏛️"),
        f"<i>ᴄᴀᴘ ɢʀᴏᴡꜱ ᴡɪᴛʜ ʜᴜᴛ ʟᴇᴠᴇʟ (+{STORAGE_PER_HUT_LV:,} ᴘᴇʀ ʟᴇᴠᴇʟ).</i>",
    ]
    await message.reply(ui.card("ꜱᴛᴏʀᴀɢᴇ", body, icon="📦"))


# ── /vault ───────────────────────────────────────────────────────────────

async def cmd_vault(client, message):
    u = message.from_user
    v = await _ensure_village(u.id)
    rank = await _empire_rank(v)
    body = [
        ui.chip("ɢᴇᴍꜱ", v.get("gems", 0), "💎"),
        ui.chip("ᴠᴀᴜʟᴛ ᴄᴏɪɴꜱ", fmt(v.get("vault", 0)), "💰"),
        ui.chip("ᴛʀᴇᴀꜱᴜʀʏ", fmt(v.get("treasury", 0)), "🪙"),
        ui.chip("ᴇᴍᴘɪʀᴇ ʀᴀɴɪ", f"#{rank}", "🌍"),
        ui.chip("ᴋɪɴɢᴅᴏᴍ ʟᴇᴠᴇʟ", f"{v['kingdom_level']} ({v['stage']})", "🏰"),
    ]
    await message.reply(ui.card("ᴠᴀᴜʟᴛ", body, icon="🏛️"))


# ── /mines ───────────────────────────────────────────────────────────────

async def cmd_mines(client, message):
    u = message.from_user
    v = await _ensure_village(u.id)
    rem = _cooldown_remaining(v.get("last_mine", 0), COOLDOWN_MINE)
    body = []
    for key, icon in [("woodyard", "🪵"), ("quarry", "🪨"), ("iron_mine", "⚙️")]:
        level = v.get(f"{key}_level", 1)
        rate = MINE_YIELD[key][level]
        body.append(ui.chip(f"{key.replace('_', ' ').title()}", f"Lv{level} — {rate}/ʜʀ", icon))
    body.append(ui.chip("ɴᴇxᴛ ᴄᴏʟʟᴇᴄᴛ", _fmt_remaining(rem), "⏳"))
    await message.reply(ui.card("ᴍɪɴᴇꜱ", body, icon="⛏️"))


# ── /build ───────────────────────────────────────────────────────────────

def _apply_building_effects(uid: int, v: dict, building: str, new_level: int) -> dict:
    """Side-effects to apply on a successful upgrade (max_citizens, storage_cap)."""
    extra = {}
    if building == "home":
        extra["max_citizens"] = CITIZEN_START + (new_level - 1) * 20
    if building == "hut":
        # Recompute storage cap for the new hut level
        v["hut_level"] = new_level
        extra["storage_cap"] = recompute_storage_cap(v)
    return extra


async def cmd_build(client, message):
    u = message.from_user
    args = message.command[1:] if len(getattr(message, "command", []) or []) > 1 else []
    if not args:
        await message.reply(
            ui.notice("ᴜꜱᴀɢᴇ: /build <home|camp|hut|woodyard|quarry|iron_mine>")
        )
        return
    bld = args[0].lower()
    if bld not in BUILD_COSTS:
        await message.reply(ui.notice(f"ᴜɴᴋɴᴏᴡɴ ʙᴜɪʟᴅɪɴɢ '{bld}'."))
        return
    v = await _ensure_village(u.id)
    level_key = f"{bld}_level"
    cur = int(v.get(level_key, 1))
    costs = BUILD_COSTS[bld]
    if cur >= max(costs.keys()):
        await message.reply(ui.notice(f"{bld} ɪꜱ ᴍᴀxᴇᴅ ᴏᴜᴛ (Lv{cur})."))
        return
    nxt = cur + 1
    wood_need, stone_need, iron_need = costs[nxt]
    factor = _worker_factor(v)
    wood_need = int(wood_need * factor)
    stone_need = int(stone_need * factor)
    iron_need = int(iron_need * factor)
    if v.get("wood", 0) < wood_need or v.get("stone", 0) < stone_need or v.get("iron", 0) < iron_need:
        await message.reply(
            ui.notice(f"ɴᴏᴛ ᴇɴᴏᴜɢʜ ʀᴇꜱᴏᴜʀᴄᴇꜱ — ɴᴇᴇᴅ 🪵{wood_need} 🪨{stone_need} ⚙️{iron_need}.")
        )
        return
    extra = _apply_building_effects(u.id, v, bld, nxt)
    await _inc(u.id, wood=-wood_need, stone=-stone_need, iron=-iron_need)
    await _upd(u.id, **{level_key: nxt}, **extra)
    body = [
        ui.chip(bld.replace("_", " ").title(), f"Lv{cur} → Lv{nxt}", "🏗️"),
        ui.chip("ᴄᴏꜱᴛ", f"🪵{wood_need} 🪨{stone_need} ⚙️{iron_need}", "💸"),
    ]
    if factor < 1.0:
        body.append(ui.chip("ᴡᴏʀᴋᴇʀ ᴅɪꜱᴄᴏᴜɴᴛ", f"−{int((1 - factor) * 100)}%", "🛠️"))
    if "max_citizens" in extra:
        body.append(ui.chip("ᴍᴀx ᴄɪᴛɪᴢᴇɴꜱ", extra["max_citizens"], "👥"))
    if "storage_cap" in extra:
        body.append(ui.chip("ꜱᴛᴏʀᴀɢᴇ ᴄᴀᴘ", extra["storage_cap"], "📦"))
    await message.reply(ui.card("ʙᴜɪʟᴅ ᴄᴏᴍᴘʟᴇᴛᴇ", body, icon="🏗️"))


# ── /walls ───────────────────────────────────────────────────────────────

async def _build_or_upgrade_wall(uid: int, wtype: str) -> tuple:
    """Returns (ok: bool, message: str). Pure after reading the village doc."""
    spec = WALL_TYPES.get(wtype)
    if not spec:
        return False, ui.notice(f"ᴜɴᴋɴᴏᴡɴ ᴡᴀʟʟ '{wtype}'.")
    v = await _ensure_village(uid)
    factor = _worker_factor(v)
    walls = v.get("walls") or {}
    cur = walls.get(wtype, {"level": 0, "hp": 0, "max_hp": 0, "damage": 0})
    new_level = cur.get("level", 0) + 1
    res_type, base_cost = spec["cost_resource"]
    need = int(base_cost * new_level * factor)
    if v.get(res_type, 0) < need:
        return False, ui.notice(
            f"ɴᴇᴇᴅ {need} {res_type} ꜰᴏʀ {wtype} Lv{new_level}."
        )
    hp = spec["hp"] * new_level
    dmg = spec["damage"] * new_level
    new_walls = dict(walls)
    new_walls[wtype] = {"level": new_level, "hp": hp, "max_hp": hp, "damage": dmg}
    await _inc(uid, **{res_type: -need})
    await _upd(uid, walls=new_walls)
    return True, ui.card("ᴡᴀʟʟ ʙᴜɪʟᴛ", [
        ui.chip(wtype.title(), f"Lv{new_level}", "🧱"),
        ui.chip("ʜᴘ", hp, "❤"),
        ui.chip("ᴅᴍɢ", dmg, "⚔️"),
        ui.chip("ᴄᴏꜱᴛ", f"−{need} {res_type}", "💸"),
    ], icon="🧱")


async def cmd_walls(client, message):
    u = message.from_user
    args = message.command[1:] if len(getattr(message, "command", []) or []) > 1 else []
    if not args:
        v = await _ensure_village(u.id)
        body = []
        for wtype in WALL_TYPES:
            w = (v.get("walls") or {}).get(wtype)
            if w:
                body.append(ui.chip(
                    wtype.title(), f"Lv{w.get('level', 1)} • HP {w.get('hp', 0)}", "🧱"))
            else:
                body.append(ui.chip(wtype.title(), "ɴᴏᴛ ʙᴜɪʟᴛ", "🧱"))
        await message.reply(ui.card("ᴡᴀʟʟꜱ", body, icon="🧱"))
        return
    ok, body = await _build_or_upgrade_wall(u.id, args[0].lower())
    await message.reply(body)


# ── /defense ─────────────────────────────────────────────────────────────

def _defense_damage(level: int, base: int) -> int:
    return base + max(0, level - 1) * 5


async def cmd_defense(client, message):
    u = message.from_user
    args = message.command[1:] if len(getattr(message, "command", []) or []) > 1 else []
    v = await _ensure_village(u.id)
    if not args:
        body = []
        defense = v.get("defense") or {}
        for dtype, spec in DEFENSE_TYPES.items():
            d = defense.get(dtype)
            if d:
                body.append(ui.chip(
                    dtype.replace("_", " ").title(),
                    f"Lv{d.get('level', 1)} • HP {d.get('hp', 0)} • DMG {_defense_damage(d.get('level', 1), spec['damage_base'])}",
                    "🛡️"))
            else:
                body.append(ui.chip(dtype.replace("_", " ").title(), "ɴᴏᴛ ʙᴜɪʟᴛ", "🛡️"))
        await message.reply(ui.card("ᴅᴇꜰᴇɴꜱᴇ", body, icon="🛡️"))
        return
    dtype = args[0].lower()
    spec = DEFENSE_TYPES.get(dtype)
    if not spec:
        await message.reply(ui.notice(f"ᴜɴᴋɴᴏᴡɴ ᴅᴇꜰᴇɴꜱᴇ '{dtype}'."))
        return
    defense = v.get("defense") or {}
    cur = defense.get(dtype, {"level": 0, "hp": 0, "max_hp": 0})
    new_level = cur.get("level", 0) + 1
    cost = spec["cost_coins"] * new_level
    if v.get("balance", 0) < cost:
        await message.reply(ui.notice(f"ɴᴇᴇᴅ {cost:,} ᴡᴀʟʟᴇᴛ ᴄᴏɪɴꜱ."))
        return
    hp = spec["hp"] * new_level
    dmg = _defense_damage(new_level, spec["damage_base"])
    new_def = dict(defense)
    new_def[dtype] = {"level": new_level, "hp": hp, "max_hp": hp}
    await _inc(u.id, balance=-cost)
    await _upd(u.id, defense=new_def)
    await message.reply(ui.card("ᴅᴇꜰᴇɴꜱᴇ ʙᴜɪʟᴛ", [
        ui.chip(dtype.replace("_", " ").title(), f"Lv{new_level}", "🛡️"),
        ui.chip("ʜᴘ", hp, "❤"),
        ui.chip("ᴅᴍɢ", dmg, "⚔️"),
        ui.chip("ᴄᴏꜱᴛ", f"−{cost:,}", "💸"),
    ], icon="🛡️"))


# ── /train ───────────────────────────────────────────────────────────────

async def cmd_train(client, message):
    u = message.from_user
    args = message.command[1:] if len(getattr(message, "command", []) or []) > 1 else []
    if len(args) < 2:
        await message.reply(ui.notice("ᴜꜱᴀɢᴇ: /train <type> <n>"))
        return
    ttype = args[0].lower()
    try:
        n = int(args[1])
    except ValueError:
        await message.reply(ui.notice("ɴ ᴍᴜꜱᴛ ʙᴇ ᴀ ɴᴜᴍʙᴇʀ."))
        return
    if n <= 0:
        await message.reply(ui.notice("ɴ ᴍᴜꜱᴛ ʙᴇ ᴘᴏꜱɪᴛɪᴠᴇ."))
        return
    v = await _ensure_village(u.id)
    if ttype == "workers":
        if _free_citizens(v) < n:
            await message.reply(ui.notice("ɴᴏᴛ ᴇɴᴏᴜɢʜ ꜰʀᴇᴇ ᴄɪᴛɪᴢᴇɴꜱ."))
            return
        await _inc(u.id, workers=n)
        await message.reply(ui.card("ᴛʀᴀɪɴᴇᴅ", [
            ui.chip("ᴡᴏʀᴋᴇʀꜱ", f"+{n}", "🛠️"),
        ], icon="🛠️"))
        return
    spec = TROOP_TYPES.get(ttype)
    if not spec:
        await message.reply(ui.notice(f"ᴜɴᴋɴᴏᴡɴ ᴛʀᴏᴏᴘ '{ttype}'."))
        return
    cost = spec["cost_coins"] * n
    if v.get("balance", 0) < cost:
        await message.reply(ui.notice(f"ɴᴇᴇᴅ {cost:,} ᴡᴀʟʟᴇᴛ ᴄᴏɪɴꜱ."))
        return
    troops = dict(v.get("troops") or {})
    cur_total = sum(troops.values())
    if cur_total + n > v.get("camp_level", 1) * 20:
        await message.reply(ui.notice(f"ᴄᴀᴍᴘ ʜᴏʟᴅꜱ {v.get('camp_level', 1) * 20} ᴛʀᴏᴏᴘꜱ; ᴜᴘɢʀᴀᴅᴇ /build camp."))
        return
    if _free_citizens(v) < n:
        await message.reply(ui.notice("ɴᴏᴛ ᴇɴᴏᴜɢʜ ꜰʀᴇᴇ ᴄɪᴛɪᴢᴇɴꜱ."))
        return
    troops[ttype] = troops.get(ttype, 0) + n
    await _inc(u.id, balance=-cost, **{f"troops.{ttype}": n} if False else {})
    await _upd(u.id, troops=troops)
    await message.reply(ui.card("ᴛʀᴀɪɴᴇᴅ", [
        ui.chip(ttype.title(), f"+{n} (total {troops[ttype]})", "⚔️"),
        ui.chip("ᴄᴏꜱᴛ", f"−{cost:,}", "💸"),
    ], icon="⚔️"))


# ── /troops ──────────────────────────────────────────────────────────────

async def cmd_troops(client, message):
    u = message.from_user
    v = await _ensure_village(u.id)
    troops = v.get("troops") or {}
    body = []
    for ttype, spec in TROOP_TYPES.items():
        count = troops.get(ttype, 0)
        body.append(ui.chip(
            ttype.title(),
            f"{count} • HP {spec['hp']} • DMG {spec['damage']}",
            "⚔️",
        ))
    body.append(ui.chip("ᴡᴏʀᴋᴇʀꜱ", v.get("workers", 0), "🛠️"))
    body.append(ui.chip("ꜰʀᴇᴇ ᴄɪᴛɪᴢᴇɴꜱ", _free_citizens(v), "👥"))
    body.append(ui.chip("ᴄᴀᴍᴘ ᴄᴀᴘ", f"{v.get('camp_level', 1) * 20}", "🏕️"))
    await message.reply(ui.card("ʏᴏᴜʀ ᴀʀᴍʏ", body, icon="🪖"))


# ── /kingdom and /spy ────────────────────────────────────────────────────

def _defense_block_summary(v: dict) -> tuple:
    wall_hp, wall_dmg, def_hp, def_dmg = _total_defense_block(v)
    return wall_hp, wall_dmg, def_hp, def_dmg


def _scout_card(target: dict, *, with_attack_info: bool) -> list:
    """Return body lines for /kingdom or /spy on a target."""
    rank = target.get("kingdom_level", 1)
    stage = target.get("stage", "Village")
    protected = _is_protected(target)
    cap = recompute_storage_cap(target)
    body = [
        ui.chip("ᴋɪɴɢᴅᴏᴍ ʟᴇᴠᴇʟ", f"{rank} ({stage})", "🏰"),
        ui.chip("xᴘ", target.get("xp", 0), "⚡"),
        ui.chip("ᴛʀᴇᴀꜱᴜʀʏ", fmt(target.get("treasury", 0)), "🪙"),
        ui.chip("ᴠᴀᴜʟᴛ", fmt(target.get("vault", 0)), "🏛️"),
        ui.chip("ᴡᴀʟʟᴇᴛ", fmt(target.get("balance", 0)), "💰"),
        ui.chip("ꜱᴛᴏʀᴀɢᴇ", f"{target.get('wood', 0)}/{cap} ᴡᴏᴏᴅ • "
                f"{target.get('stone', 0)}/{cap} ꜱᴛᴏɴᴇ • "
                f"{target.get('iron', 0)}/{cap} ɪʀᴏɴ", "📦"),
        ui.chip("ᴛʀᴏᴏᴘꜱ", sum((target.get("troops") or {}).values()), "⚔️"),
        ui.chip("ᴡᴀʟʟꜱ", _wall_str(target), "🧱"),
        ui.chip("ᴅᴇꜰᴇɴꜱᴇ", _def_str(target), "🛡️"),
        ui.chip("🛡️  ꜱʜɪᴇʟᴅ", "ᴀᴄᴛɪᴠᴇ" if protected else "ᴇxᴘɪʀᴇᴅ", "🛡️"),
    ]
    if with_attack_info:
        body.append(ui.chip("ᴀᴛᴛᴀᴄᴋꜱ",
                            f"{target.get('attacks_used', 0)} / {target.get('attacks_max', ATTACKS_MAX_BASE)}",
                            "⚔️"))
        wall_hp, wall_dmg, def_hp, def_dmg = _defense_block_summary(target)
        body.append(ui.chip("ᴅᴇꜰᴇɴꜱᴇ ʜᴘ", wall_hp + def_hp, "❤"))
        body.append(ui.chip("ᴅᴇꜰᴇɴꜱᴇ ᴅᴍɢ/ʀᴅ", wall_dmg + def_dmg, "💥"))
        # Loot preview
        body.append(ui.chip("ᴇꜱᴛ. ʟᴏᴏᴛ",
                            f"🪵{int(target.get('wood', 0) * LOOT_FRACTION)} "
                            f"🪨{int(target.get('stone', 0) * LOOT_FRACTION)} "
                            f"⚙️{int(target.get('iron', 0) * LOOT_FRACTION)} "
                            f"🪙{int(target.get('treasury', 0) * LOOT_FRACTION)}",
                            "💰"))
        body.append(ui.chip("ᴠᴇʀᴅɪᴄᴛ",
                            "🚫 ɴᴏᴛ ʀᴇᴀᴅʏ" if protected else "✅ sᴀꜰᴇ ᴛᴏ ᴀᴛᴛᴀᴄᴋ",
                            "🕵️"))
    return body


async def _scout_command(client, message, *, with_attack_info: bool):
    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.reply(ui.notice("ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴜꜱᴇʀ ᴛᴏ ꜱᴄᴏᴜᴛ."))
        return
    target = message.reply_to_message.from_user
    if target.is_bot:
        await message.reply(ui.notice("ᴄᴀɴ'ᴛ ꜱᴄᴏᴜᴛ ʙᴏᴛꜱ."))
        return
    if target.id == message.from_user.id:
        await message.reply(ui.notice("ᴄᴀɴ'ᴛ ꜱᴄᴏᴜᴛ ʏᴏᴜʀꜱᴇʟꜰ."))
        return
    v = await _ensure_village(target.id)
    body = _scout_card(v, with_attack_info=with_attack_info)
    title = "🕵️  ꜱᴘʏ ʀᴇᴘᴏʀᴛ" if with_attack_info else "🔎  ᴋɪɴɢᴅᴏᴍ ɪɴꜰᴏ"
    await message.reply(ui.card(title, body, icon="🏰"))


async def cmd_kingdom(client, message):
    await _scout_command(client, message, with_attack_info=False)


async def cmd_spy(client, message):
    await _scout_command(client, message, with_attack_info=True)


# ── /attack ──────────────────────────────────────────────────────────────

async def cmd_attack(client, message):
    u = message.from_user
    args = message.command[1:] if len(getattr(message, "command", []) or []) > 1 else []
    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.reply(ui.notice("ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴜꜱᴇʀ ᴛᴏ ᴀᴛᴛᴀᴄᴋ."))
        return
    target = message.reply_to_message.from_user
    if target.is_bot or target.id == u.id:
        await message.reply(ui.notice("ɪɴᴠᴀʟɪᴅ ᴛᴀʀɢᴇᴛ."))
        return
    if len(args) < 2:
        await message.reply(ui.notice("ᴜꜱᴀɢᴇ: /attack <troop> <n>"))
        return
    ttype = args[0].lower()
    try:
        n = int(args[1])
    except ValueError:
        await message.reply(ui.notice("ɴ ᴍᴜꜱᴛ ʙᴇ ᴀ ɴᴜᴍʙᴇʀ."))
        return
    if n <= 0:
        await message.reply(ui.notice("ɴ ᴍᴜꜱᴛ ʙᴇ ᴘᴏꜱɪᴛɪᴠᴇ."))
        return
    av = await _ensure_village(u.id)
    now = int(time.time())
    rem = _cooldown_remaining(av.get("last_attack", 0), COOLDOWN_ATTACK)
    if rem > 0:
        await message.reply(ui.notice(f"ᴀᴛᴛᴀᴄᴋ ᴄᴏᴏʟᴅᴏᴡɴ — ᴡᴀɪᴛ {_fmt_remaining(rem)}."))
        return
    if av.get("attacks_used", 0) >= av.get("attacks_max", ATTACKS_MAX_BASE):
        await message.reply(ui.notice("ᴀᴛᴛᴀᴄᴋ ǫᴜᴏᴛᴀ ᴇxʜᴀᴜꜱᴛᴇᴅ."))
        return
    troops = av.get("troops") or {}
    if troops.get(ttype, 0) < n:
        await message.reply(ui.notice(f"ʏᴏᴜ ᴏɴʟʏ ʜᴀᴠᴇ {troops.get(ttype, 0)} {ttype}."))
        return
    dv = await _ensure_village(target.id)
    if _is_protected(dv):
        await message.reply(ui.notice("ᴛᴀʀɢᴇᴛ ɪꜱ ᴜɴᴅᴇʀ ꜱʜɪᴇʟᴅ."))
        return
    # Reset attack cooldown regardless of outcome
    await _upd(u.id, last_attack=now)
    result = simulate_attack(av, dv, ttype, n)
    if result["win"]:
        # Apply loot + cleanup, capped to attacker's storage
        loot = _cap_resources(av, result["loot"])
        await _inc(u.id, attacks_used=1)
        await _inc(u.id, wood=loot["wood"], stone=loot["stone"], iron=loot["iron"],
                   treasury=result["loot"].get("coins", 0))
        # Defender: apply shield + clear defenses + remove resources
        await _inc(target.id, wood=-loot["wood"], stone=-loot["stone"], iron=-loot["iron"],
                   treasury=-result["loot"].get("coins", 0),
                   attacks_used=1)
        await _upd(target.id, walls={}, defense={},
                   protected_until=int(time.time()) + SHIELD_DURATION)
        # Troops lost
        if result["troops_lost"]:
            troops_after = dict(av.get("troops") or {})
            troops_after[ttype] = max(0, troops_after.get(ttype, 0) - result["troops_lost"])
            await _upd(u.id, troops=troops_after)
        # XP grant (may level up)
        xp_res = await _grant_xp(u.id, result["xp_gained"])
        # Notify victim
        try:
            await client.send_message(target.id, ui.card("ʏᴏᴜ ᴡᴇʀᴇ ʀᴀɪᴅᴇᴅ!", [
                ui.chip("ᴀᴛᴛᴀᴄᴋᴇʀ", mention(u.id, _name(u)), "⚔️"),
                ui.chip("ʟᴏꜱᴛ", f"🪵{loot['wood']} 🪨{loot['stone']} ⚙️{loot['iron']} 🪙{result['loot'].get('coins', 0)}", "💀"),
                f"🛡️ ʏᴏᴜ'ʀᴇ ɴᴏᴡ ᴜɴᴅᴇʀ 1ʜ ꜱʜɪᴇʟᴅ.",
            ], icon="🚨"))
        except Exception as e:
            logger.debug("victim DM failed: %s", e)
        body = [
            ui.chip("ᴠɪᴄᴛᴏʀʏ!", f"vs {mention(target.id, _name(target))}", "🏆"),
            ui.chip("ʟᴏᴏᴛ",
                    f"🪵{loot['wood']} 🪨{loot['stone']} ⚙️{loot['iron']} 🪙{result['loot'].get('coins', 0)}", "💰"),
            ui.chip("xᴘ", f"+{result['xp_gained']}", "⚡"),
        ]
        if xp_res["leveled"]:
            body.append(ui.chip("ʟᴇᴠᴇʟ ᴜᴘ!", f"Kingdom Lv{xp_res['level']} ({stage_for(xp_res['level'])})", "🎉"))
        body.append(ui.chip("ᴛʀᴏᴏᴘꜱ ʟᴏꜱᴛ", f"−{result['troops_lost']} {ttype}", "💀"))
        await message.reply(ui.card("ᴀᴛᴛᴀᴄᴋ ʀᴇᴘᴏʀᴛ", body, icon="⚔️"))
    else:
        # Attacker lost
        await _inc(u.id, attacks_used=1)
        if result["troops_lost"]:
            troops_after = dict(av.get("troops") or {})
            troops_after[ttype] = max(0, troops_after.get(ttype, 0) - result["troops_lost"])
            await _upd(u.id, troops=troops_after)
        await _inc(dv["_id"], attacks_used=1) if False else None  # defender not penalized on defend win
        await message.reply(ui.card("ᴀᴛᴛᴀᴄᴋ ꜰᴀɪʟᴇᴅ", [
            ui.chip("ᴛᴀʀɢᴇᴛ", mention(target.id, _name(target)), "🎯"),
            ui.chip("ʀᴇꜱᴜʟᴛ", "ʏᴏᴜʀ ᴛʀᴏᴏᴘꜱ ᴡᴇʀᴇ ʀᴇᴘᴇʟʟᴇᴅ", "💀"),
            ui.chip("ᴛʀᴏᴏᴘꜱ ʟᴏꜱᴛ", f"−{result['troops_lost']} {ttype}", "💀"),
        ], icon="💀"))


# ── /emperors ────────────────────────────────────────────────────────────

async def cmd_emperors(client, message):
    try:
        cursor = db().village.find().sort("treasury", -1).limit(10)
        rows = []
        async for d in cursor:
            uid = d["_id"]
            try:
                u = await client.get_chat(uid)
                name = getattr(u, "first_name", None) or getattr(u, "title", None) or str(uid)
            except Exception:
                name = str(uid)
            rows.append((mention(uid, name), fmt(d.get("treasury", 0))))
    except Exception as e:
        logger.debug("emperors query failed: %s", e)
        rows = []
    await message.reply(ui.scorecard(rows, title="👑 ᴇᴍᴘᴇʀᴏʀꜱ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ"))


# ── /settle ──────────────────────────────────────────────────────────────

async def cmd_settle(client, message):
    u = message.from_user
    args = message.command[1:] if len(getattr(message, "command", []) or []) > 1 else []
    if len(args) < 2:
        await message.reply(ui.notice("ᴜꜱᴀɢᴇ: /settle <vault|treasury> <amt>"))
        return
    direction = args[0].lower()
    try:
        amt = int(args[1])
    except ValueError:
        await message.reply(ui.notice("ᴀᴍᴛ ᴍᴜꜱᴛ ʙᴇ ᴀ ɴᴜᴍʙᴇʀ."))
        return
    if amt <= 0:
        await message.reply(ui.notice("ᴀᴍᴛ ᴍᴜꜱᴛ ʙᴇ ᴘᴏꜱɪᴛɪᴠᴇ."))
        return
    v = await _ensure_village(u.id)
    if direction == "vault":
        if v.get("treasury", 0) < amt:
            await message.reply(ui.notice("ɴᴏᴛ ᴇɴᴏᴜɢʜ ᴛʀᴇᴀꜱᴜʀʏ."))
            return
        await _inc(u.id, treasury=-amt, vault=amt)
    elif direction == "treasury":
        if v.get("vault", 0) < amt:
            await message.reply(ui.notice("ɴᴏᴛ ᴇɴᴏᴜɢʜ ᴠᴀᴜʟᴛ."))
            return
        await _inc(u.id, vault=-amt, treasury=amt)
    else:
        await message.reply(ui.notice("ᴅɪʀᴇᴄᴛɪᴏɴ ᴍᴜꜱᴛ ʙᴇ ᴠᴀᴜʟᴛ ᴏʀ ᴛʀᴇᴀꜱᴜʀʏ."))
        return
    await message.reply(ui.card("ꜱᴇᴛᴛʟᴇᴅ", [
        ui.chip("ᴅɪʀᴇᴄᴛɪᴏɴ", direction, "💱"),
        ui.chip("ᴀᴍᴏᴜɴᴛ", fmt(amt), "🪙"),
    ], icon="💱"))


# ── /convert ─────────────────────────────────────────────────────────────

_CONVERT_PRICE = {"wood": 5, "stone": 8, "iron": 12}


async def cmd_convert(client, message):
    u = message.from_user
    args = message.command[1:] if len(getattr(message, "command", []) or []) > 1 else []
    if len(args) < 2:
        await message.reply(ui.notice("ᴜꜱᴀɢᴇ: /convert <wood|stone|iron> <amt>"))
        return
    rtype = args[0].lower()
    if rtype not in _CONVERT_PRICE:
        await message.reply(ui.notice(f"ᴜɴᴋɴᴏᴡɴ ʀᴇꜱᴏᴜʀᴄᴇ '{rtype}'."))
        return
    try:
        amt = int(args[1])
    except ValueError:
        await message.reply(ui.notice("ᴀᴍᴛ ᴍᴜꜱᴛ ʙᴇ ᴀ ɴᴜᴍʙᴇʀ."))
        return
    if amt <= 0:
        await message.reply(ui.notice("ᴀᴍᴛ ᴍᴜꜱᴛ ʙᴇ ᴘᴏꜱɪᴛɪᴠᴇ."))
        return
    v = await _ensure_village(u.id)
    if v.get(rtype, 0) < amt:
        await message.reply(ui.notice(f"ɴᴏᴛ ᴇɴᴏᴜɢʜ {rtype}."))
        return
    coins = amt * _CONVERT_PRICE[rtype]
    await _inc(u.id, **{rtype: -amt, "vault": coins})
    await message.reply(ui.card("ᴄᴏɴᴠᴇʀᴛᴇᴅ", [
        ui.chip(rtype.title(), f"−{amt}", "🪵"),
        ui.chip("ᴠᴀᴜʟᴛ", f"+{coins}", "🪙"),
    ], icon="💱"))


# ── /daily (DM-only) ────────────────────────────────────────────────────

async def cmd_daily(client, message):
    if message.chat.type != ChatType.PRIVATE:
        await message.reply(
            "❗ ʏᴏᴜ ᴄᴀɴ ᴄʟᴀɪᴍ ʏᴏᴜʀ ᴅᴀɪʟʏ ʀᴇꜱᴏᴜʀᴄᴇꜱ ᴀɴᴅ ᴄᴜʀʀᴇɴᴄɪᴇꜱ ɪɴ ᴅᴍ ᴏɴʟʏ."
        )
        return
    u = message.from_user
    v = await _ensure_village(u.id)
    now = int(time.time())
    rem = _cooldown_remaining(v.get("last_daily", 0), COOLDOWN_DAILY)
    if rem > 0:
        h = rem // 3600
        m = (rem % 3600) // 60
        s = rem % 60
        await message.reply(
            f"❕ ʏᴏᴜ ᴀʟʀᴇᴀᴅʏ ᴄʟᴀɪᴍᴇᴅ ᴛᴏᴅᴀʏ!\n👉 ɴᴇxᴛ ʀᴇᴡᴀʀᴅ ɪɴ: {h}ʜ {m}ᴍ {s}ꜱ"
        )
        return
    wood = 200 + v.get("woodyard_level", 1) * 50
    stone = 150 + v.get("quarry_level", 1) * 40
    iron = 100 + v.get("iron_mine_level", 1) * 30
    coins = 100 + v.get("kingdom_level", 1) * 20
    cap_delta = _cap_resources(v, {"wood": wood, "stone": stone, "iron": iron})
    await _inc(u.id, wood=cap_delta["wood"], stone=cap_delta["stone"], iron=cap_delta["iron"],
               balance=coins, last_daily=now)
    body = [
        ui.chip("ᴡᴏᴏᴅ", f"+{cap_delta['wood']}", "🪵"),
        ui.chip("ꜱᴛᴏɴᴇ", f"+{cap_delta['stone']}", "🪨"),
        ui.chip("ɪʀᴏɴ", f"+{cap_delta['iron']}", "⚙️"),
        ui.chip("ᴡᴀʟʟᴇᴛ", f"+{coins:,}", "💰"),
        ui.chip("ɴᴇxᴛ", "24ʜ", "⏳"),
    ]
    if (wood + stone + iron) > sum(cap_delta.values()):
        body.append(ui.notice("ꜱᴛᴏʀᴀɢᴇ ᴄᴀᴘ ʀᴇᴀᴄʜᴇᴅ — ᴜᴘɢʀᴀᴅᴇ ʜᴜᴛ."))
    await message.reply(ui.card("ᴅᴀɪʟʏ ʀᴇᴡᴀʀᴅ ᴄʟᴀɪᴍᴇᴅ!", body, icon="🎁"))


# ── /market ──────────────────────────────────────────────────────────────

async def cmd_market(client, message):
    u = message.from_user
    args = message.command[1:] if len(getattr(message, "command", []) or []) > 1 else []
    v = await _ensure_village(u.id)
    if not args or args[0] == "prices":
        body = []
        for r, p in MARKET_PRICES.items():
            body.append(ui.chip(r.title(), f"ʙᴜʏ {p} • ꜱᴇʟʟ {int(p * MARKET_SELL_RATIO)}", "🪙"))
        await message.reply(ui.card("ᴍᴀʀᴋᴇᴛ ᴘʀɪᴄᴇꜱ", body, icon="🏪"))
        return
    if args[0] not in ("buy", "sell") or len(args) < 3:
        await message.reply(ui.notice("ᴜꜱᴀɢᴇ: /market [buy|sell] <res> <qty>"))
        return
    op = args[0]
    rtype = args[1].lower()
    if rtype not in MARKET_PRICES:
        await message.reply(ui.notice(f"ᴜɴᴋɴᴏᴡɴ ʀᴇꜱᴏᴜʀᴄᴇ '{rtype}'."))
        return
    try:
        qty = int(args[2])
    except ValueError:
        await message.reply(ui.notice("ǫᴛʏ ᴍᴜꜱᴛ ʙᴇ ᴀ ɴᴜᴍʙᴇʀ."))
        return
    if qty <= 0:
        await message.reply(ui.notice("ǫᴛʏ ᴍᴜꜱᴛ ʙᴇ ᴘᴏꜱɪᴛɪᴠᴇ."))
        return
    price = MARKET_PRICES[rtype] * qty
    if op == "buy":
        if v.get("balance", 0) < price:
            await message.reply(ui.notice(f"ɴᴇᴇᴅ {price:,} ᴡᴀʟʟᴇᴛ ᴄᴏɪɴꜱ."))
            return
        delta = _cap_resources(v, {rtype: qty})
        if delta[rtype] < qty:
            await message.reply(ui.notice(f"ꜱᴛᴏʀᴀɢᴇ ᴄᴀᴘ ᴡᴏᴜʟᴅ ᴇxᴄᴇᴇᴅ; ᴜᴘɢʀᴀᴅᴇ ʜᴜᴛ."))
            return
        await _inc(u.id, balance=-price, **{rtype: qty})
        await message.reply(ui.card("ᴍᴀʀᴋᴇᴛ ʙᴏᴜɢʜᴛ", [
            ui.chip(rtype.title(), f"+{qty}", "🪙"),
            ui.chip("ᴡᴀʟʟᴇᴛ", f"−{price:,}", "💸"),
        ], icon="🏪"))
    else:
        if v.get(rtype, 0) < qty:
            await message.reply(ui.notice(f"ɴᴏᴛ ᴇɴᴏᴜɢʜ {rtype}."))
            return
        payout = int(price * MARKET_SELL_RATIO)
        await _inc(u.id, balance=payout, **{rtype: -qty})
        await message.reply(ui.card("ᴍᴀʀᴋᴇᴛ ꜱᴏʟᴅ", [
            ui.chip(rtype.title(), f"−{qty}", "💰"),
            ui.chip("ᴡᴀʟʟᴇᴛ", f"+{payout:,}", "🪙"),
        ], icon="🏪"))


# ── /wallet (NEW: convert between village and global economy) ───────────

async def cmd_wallet(client, message):
    u = message.from_user
    args = message.command[1:] if len(getattr(message, "command", []) or []) > 1 else []
    v = await _ensure_village(u.id)
    user_doc = await money.ensure_user(u.id, username=u.username or "", name=u.first_name)
    vbal = v.get("balance", 0)
    gbal = user_doc.get("balance", 0)
    if not args:
        body = [
            ui.chip("ᴠɪʟʟᴀɢᴇ ᴡᴀʟʟᴇᴛ", fmt(vbal), "💰"),
            ui.chip("ɢʟᴏʙᴀʟ ᴡᴀʟʟᴇᴛ", fmt(gbal), "🪙"),
            ui.chip("ᴠɪʟʟᴀɢᴇ ᴠᴀᴜʟᴛ", fmt(v.get("vault", 0)), "🏛️"),
            ui.chip("ᴠɪʟʟᴀɢᴇ ᴛʀᴇᴀꜱᴜʀʏ", fmt(v.get("treasury", 0)), "🪙"),
            "<i>ᴜꜱᴀɢᴇ: /wallet village <amt>  ᴏʀ  /wallet global <amt></i>",
        ]
        await message.reply(ui.card("ᴡᴀʟʟᴇᴛ", body, icon="💱"))
        return
    # Convert path — DM only (mirrors /daily).
    if message.chat.type != ChatType.PRIVATE:
        await message.reply(ui.notice("ᴡᴀʟʟᴇᴛ ᴄᴏɴᴠᴇʀᴛ ɪꜱ ᴅᴍ ᴏɴʟʏ. ᴏᴘᴇɴ ᴍᴇ ɪɴ ʜᴇʀᴇ."))
        return
    if len(args) < 2:
        await message.reply(ui.notice("ᴜꜱᴀɢᴇ: /wallet <village|global> <amt>"))
        return
    direction = args[0].lower()
    try:
        amt = int(args[1])
    except ValueError:
        await message.reply(ui.notice("ᴀᴍᴛ ᴍᴜꜱᴛ ʙᴇ ᴀ ɴᴜᴍʙᴇʀ."))
        return
    if amt <= 0:
        await message.reply(ui.notice("ᴀᴍᴛ ᴍᴜꜱᴛ ʙᴇ ᴘᴏꜱɪᴛɪᴠᴇ."))
        return
    if direction == "village":
        # village -> global
        if vbal < amt:
            await message.reply(ui.notice(f"ᴠɪʟʟᴀɢᴇ ᴡᴀʟʟᴇᴛ ʜᴀꜱ ᴏɴʟʏ {vbal:,}."))
            return
        await _inc(u.id, balance=-amt)
        await money.add_balance(u.id, amt)
        await message.reply(ui.card("ᴡᴀʟʟᴇᴛ ᴛʀᴀɴꜱꜰᴇʀ", [
            ui.chip("ꜰʀᴏᴍ", "ᴠɪʟʟᴀɢᴇ", "💰"),
            ui.chip("ᴛᴏ", "ɢʟᴏʙᴀʟ", "🪙"),
            ui.chip("ᴀᴍᴏᴜɴᴛ", fmt(amt), "💸"),
        ], icon="💱"))
    elif direction == "global":
        # global -> village
        if gbal < amt:
            await message.reply(ui.notice(f"ɢʟᴏʙᴀʟ ᴡᴀʟʟᴇᴛ ʜᴀꜱ ᴏɴʟʏ {gbal:,}."))
            return
        if not await money.try_deduct(u.id, amt):
            await message.reply(ui.notice("ᴛʀᴀɴꜱꜰᴇʀ ꜰᴀɪʟᴇᴅ."))
            return
        await _inc(u.id, balance=amt)
        await message.reply(ui.card("ᴡᴀʟʟᴇᴛ ᴛʀᴀɴꜱꜰᴇʀ", [
            ui.chip("ꜰʀᴏᴍ", "ɢʟᴏʙᴀʟ", "🪙"),
            ui.chip("ᴛᴏ", "ᴠɪʟʟᴀɢᴇ", "💰"),
            ui.chip("ᴀᴍᴏᴜɴᴛ", fmt(amt), "💸"),
        ], icon="💱"))
    else:
        await message.reply(ui.notice("ᴅɪʀᴇᴄᴛɪᴏɴ ᴍᴜꜱᴛ ʙᴇ 'village' ᴏʀ 'global'."))


# ── /shield (NEW: show + activate protection) ───────────────────────────

SHIELD_COST = 50  # coins to refresh a 1h shield


async def cmd_shield(client, message):
    u = message.from_user
    v = await _ensure_village(u.id)
    if _is_protected(v):
        rem = int(v.get("protected_until", 0)) - int(time.time())
        body = [ui.chip("ꜱᴛᴀᴛᴜꜱ", "🛡️  ᴀᴄᴛɪᴠᴇ", "🛡️"),
                ui.chip("ᴇxᴘɪʀᴇꜱ ɪɴ", _fmt_remaining(rem), "⏳")]
        await message.reply(ui.card("ᴘʀᴏᴛᴇᴄᴛɪᴏɴ", body, icon="🛡️"))
        return
    # Activate: 50 coins, grants 1h shield.
    if v.get("balance", 0) < SHIELD_COST:
        await message.reply(ui.notice(
            f"ɴᴇᴇᴅ {SHIELD_COST} ᴄᴏɪɴꜱ ɪɴ ʏᴏᴜʀ ᴠɪʟʟᴀɢᴇ ᴡᴀʟʟᴇᴛ ᴛᴏ ᴀᴄᴛɪᴠᴀᴛᴇ ᴀ ꜱʜɪᴇʟᴅ."
        ))
        return
    await _inc(u.id, balance=-SHIELD_COST)
    await _upd(u.id, protected_until=int(time.time()) + SHIELD_DURATION)
    await message.reply(ui.card("ꜱʜɪᴇʟᴅ ᴀᴄᴛɪᴠᴀᴛᴇᴅ", [
        ui.chip("ᴅᴜʀᴀᴛɪᴏɴ", "1ʜ", "⏳"),
        ui.chip("ᴄᴏꜱᴛ", f"−{SHIELD_COST} ᴄᴏɪɴꜱ", "💰"),
        ui.chip("ꜱᴛᴀᴛᴜꜱ", "ʏᴏᴜ'ʀᴇ ɴᴏᴡ ᴘʀᴏᴛᴇᴄᴛᴇᴅ ꜰʀᴏᴍ ᴀᴛᴛᴀᴄᴋꜱ", "🛡️"),
    ], icon="🛡️"))


# ── /raid (NEW: PvE solo bandit camp) ────────────────────────────────────

COOLDOWN_RAID = 30 * 60  # 30 minutes


def _raid_outcome(v: dict) -> dict:
    """Pure: roll a PvE outcome based on player strength."""
    free = _free_citizens(v)
    troops_total = sum((v.get("troops") or {}).values())
    # Difficulty scales with kingdom_level (1-5) → bandit power
    diff = v.get("kingdom_level", 1) * 50 + 30
    player_power = troops_total * 25 + free * 2 + v.get("kingdom_level", 1) * 20
    roll = random.randint(0, max(1, diff + player_power))
    won = roll <= player_power
    if not won:
        # Lighter loss: lose a few troops
        return {"won": False, "loot": {}, "troops_lost": max(1, troops_total // 4), "xp": 5}
    # Reward scales with kingdom_level
    base = 50 * v.get("kingdom_level", 1)
    return {
        "won": True,
        "loot": {
            "wood": int(base * 0.6),
            "stone": int(base * 0.4),
            "iron": int(base * 0.3),
            "coins": int(base * 0.8),
        },
        "troops_lost": 0,
        "xp": 10 + v.get("kingdom_level", 1) * 5,
    }


async def cmd_raid(client, message):
    u = message.from_user
    v = await _ensure_village(u.id)
    rem = _cooldown_remaining(v.get("last_quest", 0), COOLDOWN_RAID)
    if rem > 0:
        await message.reply(ui.notice(f"ʀᴀɪᴅ ᴄᴏᴏʟᴅᴏᴡɴ — ᴡᴀɪᴛ {_fmt_remaining(rem)}."))
        return
    if sum((v.get("troops") or {}).values()) < 5:
        await message.reply(ui.notice("ʏᴏᴜ ɴᴇᴇᴅ ᴀᴛ ʟᴇᴀꜱᴛ 5 ᴛʀᴏᴏᴘꜱ ᴛᴏ ʀᴀɪᴅ."))
        return
    outcome = _raid_outcome(v)
    await _upd(u.id, last_quest=int(time.time()))
    if outcome["won"]:
        delta = _cap_resources(v, outcome["loot"])
        await _inc(u.id, wood=delta["wood"], stone=delta["stone"], iron=delta["iron"],
                   treasury=outcome["loot"].get("coins", 0))
        xp_res = await _grant_xp(u.id, outcome["xp"])
        body = [
            ui.chip("ᴡᴏɴ!", "ʏᴏᴜ ʀᴀɪᴅᴇᴅ ᴛʜᴇ ʙᴀɴᴅɪᴛ ᴄᴀᴍᴘ", "🏆"),
            ui.chip("ʟᴏᴏᴛ",
                    f"🪵{delta['wood']} 🪨{delta['stone']} ⚙️{delta['iron']} 🪙{outcome['loot'].get('coins', 0)}", "💰"),
            ui.chip("xᴘ", f"+{outcome['xp']}", "⚡"),
        ]
        if xp_res["leveled"]:
            body.append(ui.chip("ʟᴇᴠᴇʟ ᴜᴘ!", f"Kingdom Lv{xp_res['level']} ({stage_for(xp_res['level'])})", "🎉"))
        await message.reply(ui.card("ʀᴀɪᴅ ᴠɪᴄᴛᴏʀʏ", body, icon="🗡️"))
    else:
        # Apply troop losses
        troops = dict(v.get("troops") or {})
        total = sum(troops.values())
        loss = min(outcome["troops_lost"], total)
        if loss:
            # Reduce proportionally
            for t in list(troops.keys()):
                if loss <= 0:
                    break
                drop = min(loss, troops[t])
                troops[t] -= drop
                loss -= drop
            await _upd(u.id, troops=troops)
        await _grant_xp(u.id, outcome["xp"])
        await message.reply(ui.card("ʀᴀɪᴅ ꜰᴀɪʟᴇᴅ", [
            ui.chip("ʀᴇꜱᴜʟᴛ", "ʙᴀɴᴅɪᴛꜱ ʀᴇᴘᴇʟʟᴇᴅ ʏᴏᴜ", "💀"),
            ui.chip("ᴛʀᴏᴏᴘꜱ ʟᴏꜱᴛ", outcome["troops_lost"], "💀"),
            ui.chip("xᴘ", f"+{outcome['xp']}", "⚡"),
        ], icon="💀"))


# ── /quests (NEW: simple daily quest tracker) ────────────────────────────


def _today_quests(v: dict) -> list:
    """Generate today's 3 quests deterministically from uid + date."""
    import hashlib
    today = time.strftime("%Y-%m-%d")
    seed = f"{v['_id']}:{today}".encode()
    h = hashlib.sha256(seed).digest()
    pool = [
        ("ᴄᴏʟʟᴇᴄᴛ 1x", 30, 50, "ᴡᴀɪᴛ 5 ᴍɪɴ ᴛʜᴇɴ /collect"),
        ("ᴛʀᴀɪɴ 5 ᴛʀᴏᴏᴘꜱ", 40, 80, "/train warriors 5"),
        ("ʀᴀɪᴅ ᴀ ʙᴀɴᴅɪᴛ ᴄᴀᴍᴘ", 60, 100, "/raid"),
        ("ᴄᴏʟʟᴇᴄᴛ 2x", 50, 90, "ᴡᴀɪᴛ 10 ᴍɪɴ ᴛʜᴇɴ /collect"),
        ("ᴜᴘɢʀᴀᴅᴇ ᴀ ʙᴜɪʟᴅɪɴɢ", 70, 120, "/build home"),
        ("ᴡɪɴ ᴀɴ ᴀᴛᴛᴀᴄᴋ", 90, 150, "/spy ᴛʜᴇɴ /attack"),
        ("ᴅᴇᴘᴏꜱɪᴛ ᴛᴏ ᴠᴀᴜʟᴛ", 30, 60, "/settle vault 100"),
        ("ʙᴜʏ ꜰʀᴏᴍ ᴍᴀʀᴋᴇᴛ", 50, 80, "/market buy wood 5"),
    ]
    out = []
    for i in range(3):
        idx = h[i] % len(pool)
        title, reward_coins, reward_xp, hint = pool[idx]
        pool.pop(idx) if idx < len(pool) else None
        out.append({"title": title, "reward_coins": reward_coins,
                    "reward_xp": reward_xp, "hint": hint, "key": f"q{i}"})
    return out


async def _claimed_quests(uid: int) -> set:
    v = await _ensure_village(uid)
    return set(v.get("claimed_quests", []))


async def _mark_claimed(uid: int, key: str):
    coll = db().village
    today = time.strftime("%Y-%m-%d")
    # Reset per day
    v = await _ensure_village(uid)
    if v.get("quests_date") != today:
        await _upd(uid, quests_date=today, claimed_quests=[])
    await _inc(uid, **{}) if False else None  # noop for clarity
    await coll.update_one({"_id": uid}, {"$addToSet": {"claimed_quests": key}})


async def cmd_quests(client, message):
    u = message.from_user
    v = await _ensure_village(u.id)
    today = time.strftime("%Y-%m-%d")
    if v.get("quests_date") != today:
        await _upd(u.id, quests_date=today, claimed_quests=[])
        v["claimed_quests"] = []
    quests = _today_quests(v)
    claimed = set(v.get("claimed_quests", []))
    body = []
    for q in quests:
        done = q["key"] in claimed
        body.append(ui.chip(
            f"{'✅' if done else '⬜'} {q['title']}",
            f"+{q['reward_coins']} 🪙 • +{q['reward_xp']} xᴘ" + (f" — {q['hint']}" if not done else ""),
            "✧",
        ))
    body.append("<i>ǫᴜᴇꜱᴛꜱ ʀᴇꜱᴇᴛ ᴅᴀɪʟʏ. ᴄʟᴀɪᴍ ʙᴏɴᴜꜱ: /claim (ᴄᴏᴍɪɴɢ ꜱᴏᴏɴ).</i>")
    await message.reply(ui.card("ᴅᴀɪʟʏ ǫᴜᴇꜱᴛꜱ", body, icon="📜"))


# ═══════════════════════════════════════════════════════════════════════════
#  Registration
# ═══════════════════════════════════════════════════════════════════════════

def register(add, filters, add_cb, **kwargs) -> int:
    n = 0

    def A(fn, names, group=0):
        nonlocal n
        for nm in names:
            add(fn, filters.command([nm]), group=group)
            n += 1

    A(cmd_start, ["start"])
    A(cmd_village, ["village"])
    A(cmd_guide, ["guide"])
    A(cmd_collect, ["collect"])
    A(cmd_storage, ["storage"])
    A(cmd_vault, ["vault"])
    A(cmd_mines, ["mines"])
    A(cmd_build, ["build"])
    A(cmd_walls, ["walls"])
    A(cmd_defense, ["defense"])
    A(cmd_train, ["train"])
    A(cmd_troops, ["troops"])
    A(cmd_kingdom, ["kingdom"])
    A(cmd_spy, ["spy"])
    A(cmd_attack, ["attack"])
    A(cmd_emperors, ["emperors"])
    A(cmd_settle, ["settle"])
    A(cmd_convert, ["convert"])
    A(cmd_daily, ["daily"])
    A(cmd_market, ["market"])
    # New commands
    A(cmd_wallet, ["wallet"])
    A(cmd_shield, ["shield"])
    A(cmd_raid, ["raid"])
    A(cmd_quests, ["quests"])
    return n
