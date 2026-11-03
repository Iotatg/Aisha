# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""Aisha — auto-reaction engine + handler.

When a user's message (text, caption, or sticker) clearly calls for it,
Aisha reacts with a single Telegram reaction emoji (Telegram's native
message-reaction feature, via `client.send_reaction`). Pure offline
keyword/emoji detection — no AI, no cost. Personality is tuned to Aisha
(love/cute/funny/thanks heavy with 🥰).
"""
import logging
import random
import re
import time

logger = logging.getLogger(__name__)

# Telegram's documented reaction whitelist.
_ALLOWED = {
    "👍", "👎", "❤", "🔥", "🥰", "👏", "😁", "🤔", "🤯", "😱",
    "🤬", "😢", "🎉", "🤩", "🙏", "👌", "🕊", "🤡", "🥱", "🥴",
    "😍", "🐳", "🌚", "🌭", "💯", "🤣", "⚡", "🍌", "🏆",
    "💔", "🤨", "😐", "🍓", "🍾", "💋", "🖕", "😈", "😴", "😭",
    "🤓", "👻", "👀", "🎃", "🙈", "😇", "😨", "🤝", "✍",
    "🤗", "🫡", "🎅", "🎄", "☃", "💅", "🤪", "🗿", "🆒", "💘",
    "🙉", "🦄", "😘", "💊", "🙊", "😎", "👾", "🤷", "😡",
}

_EMOJI_REACT: dict[str, list[str]] = {
    "😂": ["🤣", "😁"], "🤣": ["😂", "😁"], "😁": ["😂", "🤣"],
    "😍": ["😍", "❤"], "🥰": ["🥰", "❤"], "😘": ["😘", "🥰"],
    "❤": ["❤", "🥰"], "💘": ["💘", "❤"], "💔": ["💔", "😢"],
    "😢": ["😢", "💔"], "😭": ["😢", "💔"],
    "😡": ["😡", "🤬"], "🤬": ["🤬", "😡"],
    "🎉": ["🎉", "🤩"], "🥳": ["🎉", "🤩"], "🔥": ["🔥", "🤩"],
    "😱": ["😱", "🤯"], "🤯": ["🤯", "😱"], "😎": ["😎", "🔥"],
    "👏": ["👏", "👍"], "👍": ["👍", "👏"], "🙏": ["🙏", "👏"],
    "💯": ["💯", "🔥"], "🤩": ["🤩", "🔥"], "🤗": ["🤗", "🥰"],
    "😈": ["😈", "🤬"], "😴": ["😴", "🥱"], "🥱": ["🥱", "😴"],
    "🤡": ["🤡", "😂"], "🤨": ["🤨", "😐"], "😐": ["😐", "🤨"],
    "🤔": ["🤔", "😐"], "🤭": ["😁", "😂"], "🥺": ["😢", "🥰"],
    "🤪": ["🤪", "😂"], "👻": ["👻", "😂"], "🙈": ["🙈", "🤣"],
    "🤓": ["🤓", "👍"], "😇": ["😇", "🥰"], "😨": ["😨", "😱"],
    "😌": ["🥰", "🥰"], "😊": ["🥰", "🥰"], "🤝": ["🤝", "🙏"],
    "✍": ["✍", "👍"], "🫡": ["🫡", "👍"], "⚡": ["⚡", "🔥"],
    "🏆": ["🏆", "🎉"], "🍌": ["🍌", "😂"], "🌚": ["🌚", "😈"],
    "🦄": ["🦄", "😍"], "🐳": ["🐳", "😂"],
}

_RULES: list[tuple[re.Pattern, str, list[str]]] = [
    (re.compile(
        r"\b(jeet g(?:a)?y(?:a)?|jeet liya|jeet li|won|winner|we won|i won|"
        r"champion|victory|number one|new highscore|high score|top scorer)\b",
        re.I), "win", ["🏆", "🎉", "🔥"]),
    (re.compile(
        r"\b(happy birthday|hbd|congrats|congratulations|badhai|mubarak|"
        r"birthday|anniversary)\b", re.I),
     "party", ["🎉", "🤩"]),
    (re.compile(
        r"\b(lol|lmao|rofl|haha+|hehe+|hihi+|funny|joke|mazak|hilarious|"
        r"roflmao)\b", re.I),
     "funny", ["🤣", "😁"]),
    (re.compile(
        r"\b(sad|dukhi|dukh|ro raha|ro rahi|roya|rone|rula|upset|depressed|"
        r"dead|died|mar gaya|mar gayi|miss you|yaad aati|lonely|breakup|"
        r"dhokha|tuta|tute)\b", re.I),
     "sad", ["😢", "💔"]),
    (re.compile(
        r"\b(i love you|love you|love u|i love|pyaar|ishq|mohabbat|shaadi|"
        r"marry me|wife|husband|crush|babe|cutie|meri jaan|dil)\b", re.I),
     "love", ["🥰", "❤"]),
    (re.compile(
        r"\b(you'?re (so )?(cute|smart|amazing|best|great|beautiful|lovely)|"
        r"tum (kitni|bahut|itni) (cute|pyari|acha|acchi|khoobsurat)|"
        r"good (job|work)|well done|shabash|great work)\b", re.I),
     "compliment", ["🥰", "😍"]),
    (re.compile(
        r"\b(wow+|omg|oh my god|ohh|wtf|shocking|surprise|what+|kya baat|"
        r"kaisa hua|no way|really!)\b", re.I),
     "shock", ["😱", "🤯"]),
    (re.compile(
        r"\b(fire|lit|awesome|epic|goated|insane|op|beast|legend|fantastic|"
        r"superb|killer|monster|crush)\b", re.I),
     "hype", ["🔥", "🤩"]),
    (re.compile(
        r"\b(angry|gussa|gusse|irritat|annoy|pissed|hate|naraz|bht gussa)\b",
        re.I), "anger", ["😡", "🤬"]),
    (re.compile(
        r"\b(thank you|thanks|thx|thank u|tysm|dhanyawad|shukriya)\b", re.I),
     "thanks", ["🙏", "👏"]),
    (re.compile(
        r"\b(good morning|good evening|suprabhat|namaste|welcome back|"
        r"gud mrng)\b", re.I),
     "greet", ["🥰", "😁"]),
    (re.compile(
        r"\b(goodbye|alvida|cya|see you|tata bye|bye bye)\b", re.I),
     "bye", ["🥰", "😁"]),
    (re.compile(
        r"\b(party|celebrat|enjoy|masti|chill|rave|concert|hangout)\b", re.I),
     "party", ["🎉", "🤩"]),
    (re.compile(
        r"\b(music|song|gaana|gana|track|melody|beat|playlist|album|lyrics)\b",
        re.I), "music", ["🥰", "🤩"]),
    (re.compile(
        r"\b(cute|adorable|sweet|pyara|pyari|soo cute|kawaii|aww|soft|"
        r"innocent)\b", re.I),
     "cute", ["🥰", "😍"]),
    (re.compile(
        r"\b(dance|nacho|nach|groove|step it up|thumka)\b", re.I),
     "dance", ["🥰", "🤩"]),
    (re.compile(
        r"\b(burn|roast|savage|clapback|rekt|destroyed|spicy reply)\b", re.I),
     "roast", ["🥰", "🤣"]),
    (re.compile(
        r"\b(money|paise|paisa|coins|gems|rich|profit|jackpot|lottery|cash)\b",
        re.I), "money", ["🥰", "🔥"]),
    (re.compile(
        r"\b(sleep|so jao|so gaya|nind|neend|tired|thak gya|thak gyi|"
        r"exhausted)\b", re.I),
     "sleep", ["😴", "🥱"]),
    (re.compile(
        r"\b(cool|nice|super|smooth|sigma|chad|goat|great move)\b", re.I),
     "cool", ["🥰", "🔥"]),
    (re.compile(
        r"\b(all the best|good luck|best of luck|shubh kamnaye)\b", re.I),
     "luck", ["🙏", "👍"]),
]

_NEUTRAL = {
    "ok", "okay", "okk", "okayy", "k", "kk", "yes", "no", "yep", "yeah",
    "nah", "nope", "hmm", "um", "umm", "mm", "m", "idk", "same", "wtv",
    "oh", "ohh", "acha", "accha", "haan", "ha", "na", "nai", "ji", "sir",
    "kya", "kyu", "why", "hm", "done", "thik", "theek",
}

# Per-command reactions — make Aisha feel alive on every interaction.
# Each value is a (pool, chance) override of PERSONALITY.
_COMMAND_REACT: dict[str, tuple[list[str], float]] = {
    "start": (["🥰", "😍"], 0.5),
    "help": (["🥰", "🤗"], 0.5),
    "menu": (["🥰", "🤗"], 0.5),
    "aisha": (["🥰", "😍"], 0.5),
    "daily": (["🥰", "🎉"], 0.5),
    "balance": (["🥰", "💅"], 0.5),
    "profile": (["🥰", "😍"], 0.5),
    "leaders": (["🏆", "🤩"], 0.5),
    "topxp": (["🏆", "🤩"], 0.5),
    "topkills": (["🔪", "🤩"], 0.5),
    "top": (["🏆", "🤩"], 0.5),
    "wallet": (["🥰", "💅"], 0.5),
    "shield": (["🥰", "🛡"], 0.6),  # 🛡 not whitelisted — falls back to allow-list
    "raid": (["🔥", "😈"], 0.5),
    "quests": (["🥰", "🎉"], 0.5),
    "kingdom": (["🥰", "🤩"], 0.5),
    "village": (["🥰", "🤩"], 0.5),
    "attack": (["🔥", "😈"], 0.5),
    "defense": (["💪", "🥰"], 0.5),
    "train": (["💪", "🥰"], 0.5),
    "spy": (["🤔", "🥰"], 0.5),
    "settle": (["🥰", "🤗"], 0.5),
    "convert": (["🥰", "💅"], 0.5),
    "collect": (["🥰", "💅"], 0.5),
    "build": (["🥰", "🔥"], 0.5),
    "ttt": (["🔥", "🎉"], 0.5),
    "bingo": (["🔥", "🎉"], 0.5),
    "typerace": (["🔥", "⚡"], 0.5),
    "wordchain": (["🤔", "🥰"], 0.5),
    "trivia": (["🤔", "🧠"], 0.6),  # 🧠 not whitelisted
    "duel": (["🔥", "😈"], 0.5),
    "luckybox": (["🎉", "🤩"], 0.5),
    "dice": (["🎲", "🤩"], 0.6),    # 🎲 not whitelisted
    "coin": (["🥰", "🤔"], 0.5),
    "flipcoin": (["🥰", "🤔"], 0.5),
    "dicebet": (["🎲", "🤩"], 0.6),
    "gamble": (["🥰", "🔥"], 0.5),
    "pay": (["🥰", "💘"], 0.5),
    "market": (["🥰", "💅"], 0.5),
}

# Aisha personality — love/cute/funny/thanks heavy, 🥰 dominant.
PERSONALITY: dict = {
    "pool": {
        "love": ["🥰", "😍"],
        "cute": ["🥰", "😍"],
        "compliment": ["🥰", "😍"],
        "funny": ["😁", "🤣"],
        "sad": ["😢", "🥰"],
        "thanks": ["🙏", "🥰"],
        "greet": ["🥰", "😁"],
        "party": ["🎉", "🤩"],
        "hype": ["🤩", "🔥"],
        "win": ["🎉", "🤩"],
        "bye": ["🥰", "😁"],
        "music": ["🥰", "🤩"],
    },
    "chance": 0.35,
}

_REACT_PROBABILITY = 0.30
_CHAT_COOLDOWN = 10.0

_last_react: dict = {}


def _pick(candidates):
    allowed = [c for c in candidates if c in _ALLOWED]
    return random.choice(allowed or ["👍"])


def _is_neutral(text):
    t = (text or "").strip().lower().rstrip(".!? ")
    if t in _NEUTRAL:
        return True
    if len(t) <= 2 and not any(c.isdigit() for c in t):
        return True
    return False


def choose_reaction(text):
    text = (text or "").strip()
    if not text:
        return None
    for ch in text:
        if ch in _EMOJI_REACT:
            return _pick(_EMOJI_REACT[ch])
    if _is_neutral(text):
        return None
    low = text.lower()
    for pattern, mood, emojis in _RULES:
        if pattern.search(low):
            pool = emojis
            pref = PERSONALITY["pool"].get(mood)
            if pref and random.random() < PERSONALITY["chance"]:
                pool = pref
            return _pick(pool)
    return None


def choose_for_command(command: str):
    """Pick a reaction for a known command. Returns None if no entry."""
    cmd = (command or "").lstrip("/").split("@")[0].lower()
    spec = _COMMAND_REACT.get(cmd)
    if not spec:
        return None
    pool, chance = spec
    if random.random() > chance:
        return None
    return _pick(pool)


def choose_for_sticker(sticker_emoji):
    se = (sticker_emoji or "").strip()
    if not se:
        return None
    for ch in se:
        if ch in _EMOJI_REACT:
            return _pick(_EMOJI_REACT[ch])
    for ch in se:
        if ch in _ALLOWED:
            return ch
    return None


async def maybe_react(client, message, command: str | None = None) -> bool:
    try:
        if getattr(message, "outgoing", False):
            return False
        fu = getattr(message, "from_user", None)
        if fu is not None and getattr(fu, "is_bot", False):
            return False
        chat = getattr(message, "chat", None)
        chat_id = getattr(chat, "id", None) or getattr(message, "chat_id", None)
        if not chat_id:
            return False
        now = time.time()
        if now - _last_react.get(chat_id, 0.0) < _CHAT_COOLDOWN:
            return False
        chosen = None
        sticker = getattr(message, "sticker", None)
        if sticker is not None:
            chosen = choose_for_sticker(getattr(sticker, "emoji", "") or "")
        text = (
            getattr(message, "text", None)
            or getattr(message, "caption", None)
            or ""
        ).strip()
        if chosen is None and command:
            chosen = choose_for_command(command)
        if chosen is None and text:
            chosen = choose_reaction(text)
        if chosen is None:
            return False
        if random.random() > _REACT_PROBABILITY:
            return False
        mid = getattr(message, "id", None) or getattr(message, "message_id", None)
        if not mid:
            return False
        _last_react[chat_id] = now
        await client.send_reaction(
            chat_id=chat_id, message_id=mid, emoji=chosen
        )
        return True
    except Exception as e:
        logger.debug("maybe_react: reaction failed (non-fatal): %s", e)
        return False


async def on_react_message(client, message):
    await maybe_react(client, message)


def register(add, filters, add_cb, **kwargs) -> int:
    """Register the auto-reaction handlers (group=-1, before chatbot)."""
    n = 0
    # Free-text / caption / sticker reactions (skip commands).
    free_flt = (
        ((filters.text & ~filters.regex(r"^/")) | filters.sticker)
        & ~filters.bot
        & ~filters.service
    )
    add(on_react_message, free_flt, group=-1)
    n += 1
    # Command reactions: react to known commands so /aisha, /daily,
    # /balance etc. feel alive. Uses a separate handler so the text
    # filter above keeps its command-skip behavior.
    cmds = list(_COMMAND_REACT.keys())
    add(on_command_react, filters.command(cmds) & ~filters.bot, group=-1)
    n += 1
    return n


async def on_command_react(client, message):
    """React to known commands (passes the command name to maybe_react)."""
    text = (getattr(message, "text", "") or "").split()
    cmd = text[0][1:].split("@")[0].lower() if text and text[0].startswith("/") else ""
    await maybe_react(client, message, command=cmd)
