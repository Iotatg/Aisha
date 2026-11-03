# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""Aisha bot configuration — everything env-driven, nothing hardcoded."""
import os


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


BOT_TOKEN      = _env("BOT_TOKEN", "")
MONGO_URI      = _env("MONGO_URI", "mongodb://localhost:27017")
DB_NAME        = _env("AISHA_DB_NAME", "aisha_bot")

OWNER_ID       = _env_int("OWNER_ID", 0)
BOT_USERNAME   = _env("BOT_USERNAME", "im_aishabot")

# ── MTProto credentials (my.telegram.org) — required for kurigram ─────────
API_ID         = _env_int("API_ID", 0)
API_HASH       = _env("API_HASH", "")

# ── AI chatbot ─────────────────────────────────────────────────────────────
# Keys are USER-supplied (comma-separated lists allowed). With no keys the
# built-in offline sass engine answers instead — the bot never goes mute.
GROQ_KEYS      = [k.strip() for k in _env("AISHA_GROQ_API_KEY", "").split(",") if k.strip()]
GEMINI_KEYS    = [k.strip() for k in _env("AISHA_GEMINI_API_KEY", "").split(",") if k.strip()]
OPENROUTER_KEYS = [k.strip() for k in _env("AISHA_OPENROUTER_API_KEY", "").split(",") if k.strip()]

# APInex (OpenAI-compatible; cheapest, ~10× lower than official)
APINEX_API_KEY = _env("AISHA_APINEX_API_KEY", "")
APINEX_MODEL = _env("AISHA_APINEX_MODEL", "free/glm-5.3-flash")
APINEX_FALLBACK_MODEL = _env("AISHA_APINEX_FALLBACK_MODEL", "free/deepseek-v4-flash-0731")
APINEX_API_URL = "https://api.apinex.bond/v1/chat/completions"

# Model overrides (defaults are sensible free/cheap picks)
OPENROUTER_MODEL = _env("AISHA_OPENROUTER_MODEL",
                        "meta-llama/llama-3.1-8b-instruct:free")
GROQ_MODEL     = _env("AISHA_GROQ_MODEL", "llama-3.3-70b-versatile")
GEMINI_MODEL   = _env("AISHA_GEMINI_MODEL", "gemini-2.0-flash")

AI_TIMEOUT     = _env_int("AI_TIMEOUT", 25)

# ── GIF provider (GIPHY) for fun/social action animations ───────────────────
# Set AISHA_GIPHY_API_KEY to override. The public demo key (dc6zaTOxFJmzC) is
# banned by GIPHY, so a real key is required for the live GIF search to work.
GIPHY_API_KEY = _env("AISHA_GIPHY_API_KEY", "Wewdpr7TcsF0FS6vJghVf28ktFej4OTe")
AI_MAX_TURNS   = 12          # context turns sent to the provider
MEMORY_DAYS    = _env_int("AISHA_MEMORY_DAYS", 30)

def _normalize_owner(name: str, username: str) -> tuple[str, str]:
    username = (username or "").lstrip("@")
    if not name or name in ("NTG", "ntg", "Owner"):
        name = "ɴᴏᴛʜɪɴɢ"
    if not username:
        username = "im_ntg"
    return name, username


# Persona basics (shared only when asked directly)
BOT_NAME       = _env("AISHA_BOT_NAME", "Aisha")
BOT_AGE        = _env("AISHA_BOT_AGE", "21")
BOT_FROM       = _env("AISHA_BOT_FROM", "Mumbai")
BOT_DOB        = _env("AISHA_BOT_DOB", "7 July")
OWNER_NAME, OWNER_USERNAME = _normalize_owner(
    _env("AISHA_OWNER_NAME", "ɴᴏᴛʜɪɴɢ"),
    _env("AISHA_OWNER_USERNAME", "im_ntg"),
)

# ── Economy ────────────────────────────────────────────────────────────────
START_BALANCE  = _env_int("START_BALANCE", 1000)
DAILY_BASE     = _env_int("DAILY_BASE", 500)
DAILY_STREAK_BONUS = _env_int("DAILY_STREAK_BONUS", 100)
DAILY_MAX      = _env_int("DAILY_MAX", 2000)

MIN_BET        = _env_int("MIN_BET", 10)
MAX_BET        = _env_int("MAX_BET", 10000)

TRIVIA_REWARD  = _env_int("TRIVIA_REWARD", 250)
TRIVIA_XP      = _env_int("TRIVIA_XP", 40)

LUCKYBOX_FEE_PAYOUT = 1   # winning box pays bet * this multiplier

TYPERACE_REWARD  = _env_int("TYPERACE_REWARD", 300)
TYPERACE_SECONDS = _env_int("TYPERACE_SECONDS", 30)

WORDCHAIN_MIN_LEN   = _env_int("WORDCHAIN_MIN_LEN", 3)
WORDCHAIN_TURN_SECS = _env_int("WORDCHAIN_TURN_SECS", 20)
WORDCHAIN_WIN_COINS = _env_int("WORDCHAIN_WIN_COINS", 400)
WORDCHAIN_WIN_XP    = _env_int("WORDCHAIN_WIN_XP", 50)

# ── Dice Arcade (native Telegram dice + bets) ─────────────────────────────
# Each game: native dice emoji, win threshold (value >=), win & jackpot mults
DICEBET_COOLDOWN = _env_int("DICEBET_COOLDOWN", 2)
DICEBET_WIN_XP   = _env_int("DICEBET_WIN_XP", 8)

# ── PvP Duel ──────────────────────────────────────────────────────────────
DUEL_JOIN_SECS  = _env_int("DUEL_JOIN_SECS", 30)
DUEL_WIN_XP     = _env_int("DUEL_WIN_XP", 20)

# ── Profile ranks (extended ladder) ───────────────────────────────────────
RANK_TITLES = [
    (0,  "ɴᴇᴡʙɪᴇ 🌱"),
    (3,  "ᴄᴜᴛɪᴇ 🌸"),
    (6,  "ꜱᴛᴀʀʟᴇᴛ ✨"),
    (10, "Qᴜᴇᴇɴ 👑"),
    (15, "ʟᴇɢᴇɴᴅ 💫"),
    (25, "ɢᴏᴅᴅᴇss 💎"),
]
