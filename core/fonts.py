# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""Unicode text styling toolkit: font transforms, a small figlet font,
and a keyword->emoji translator.

All transforms are pure (no network) so they are trivially testable.
"""
import random

# --------------------------------------------------------------------------
# small-caps (shared with social.py's _sc for a consistent bot voice)
# --------------------------------------------------------------------------
_ALPHA = "abcdefghijklmnopqrstuvwxyz"
_SC = "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘQʀꜱᴛᴜᴠᴡxʏᴢ"
SC_MAP = dict(zip(_ALPHA, _SC))


def smallcaps(text: str) -> str:
    return "".join(SC_MAP.get(c, c) for c in text.lower())


# --------------------------------------------------------------------------
# font styles
# --------------------------------------------------------------------------
def _map_from(upper_start, lower_start, special=None):
    m = {}
    for i, c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
        m[c] = chr(upper_start + i)
    for i, c in enumerate("abcdefghijklmnopqrstuvwxyz"):
        m[c] = chr(lower_start + i)
    if special:
        m.update(special)
    return m


_BOLD = _map_from(0x1D400, 0x1D41A)
_BUBBLE = _map_from(0x24B6, 0x24D0)
_SQUARE = {c: chr(0x1F130 + i) for i, c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ")}
_FULL = _map_from(0xFF21, 0xFF41)
for i, c in enumerate("0123456789"):
    _FULL[c] = chr(0xFF10 + i)

_ZALGO = [c for c in range(0x0300, 0x036F)]
_STRIKE = "\u0336"
_UNDER = "\u0332"

_FLIP = {
    "a": "\u0250", "b": "q", "c": "\u0254", "d": "p", "e": "\u01DD",
    "f": "\u025F", "g": "b", "h": "\u0265", "i": "\u0131", "j": "\u027E",
    "k": "\u029E", "l": "l", "m": "\u026F", "n": "u", "o": "o", "p": "d",
    "q": "b", "r": "\u0279", "s": "s", "t": "\u0287", "u": "n", "v": "\u028C",
    "w": "\u028D", "x": "x", "y": "\u028E", "z": "z",
}


def _apply(mapping, text):
    return "".join(mapping.get(c, c) for c in text)


def _zalgo(text, intensity=0.4):
    out = []
    for c in text:
        out.append(c)
        if c != " " and random.random() < intensity:
            out.append(chr(random.choice(_ZALGO)))
    return "".join(out)


def _flip(text):
    return "".join(_FLIP.get(c, c) for c in reversed(text))


STYLES = {
    "bold": lambda t: _apply(_BOLD, t),
    "bubble": lambda t: _apply(_BUBBLE, t),
    "square": lambda t: _apply(_SQUARE, t.upper()),
    "full": lambda t: _apply(_FULL, t),
    "tiny": smallcaps,
    "zalgo": _zalgo,
    "strike": lambda t: "".join(c + _STRIKE for c in t),
    "under": lambda t: "".join(c + _UNDER for c in t),
    "flip": _flip,
}


def style(name: str, text: str) -> str:
    fn = STYLES.get(name.lower())
    if fn is None:
        raise KeyError(name)
    return fn(text)


def style_help() -> str:
    return " | ".join(STYLES.keys())


# --------------------------------------------------------------------------
# minimal 5-row figlet font (uppercase A-Z 0-9 + space)
# --------------------------------------------------------------------------
_FIG = {
    "A": ["\u2588\u2588\u2588\u2588\u2588", "\u2588   \u2588", "\u2588\u2588\u2588\u2588\u2588", "\u2588   \u2588", "\u2588   \u2588"],
    "B": ["\u2588\u2588\u2588\u2588\u2588", "\u2588   \u2588", "\u2588\u2588\u2588\u2588\u2588", "\u2588   \u2588", "\u2588\u2588\u2588\u2588\u2588"],
    "C": ["\u2588\u2588\u2588\u2588\u2588", "\u2588    ", "\u2588    ", "\u2588    ", "\u2588\u2588\u2588\u2588\u2588"],
    "D": ["\u2588\u2588\u2588\u2588\u2588", "\u2588   \u2588", "\u2588   \u2588", "\u2588   \u2588", "\u2588\u2588\u2588\u2588\u2588"],
    "E": ["\u2588\u2588\u2588\u2588\u2588", "\u2588    ", "\u2588\u2588\u2588\u2588 ", "\u2588    ", "\u2588\u2588\u2588\u2588\u2588"],
    "F": ["\u2588\u2588\u2588\u2588\u2588", "\u2588    ", "\u2588\u2588\u2588\u2588 ", "\u2588    ", "\u2588    "],
    "G": ["\u2588\u2588\u2588\u2588\u2588", "\u2588    ", "\u2588  \u2588\u2588", "\u2588   \u2588", "\u2588\u2588\u2588\u2588\u2588"],
    "H": ["\u2588   \u2588", "\u2588   \u2588", "\u2588\u2588\u2588\u2588\u2588", "\u2588   \u2588", "\u2588   \u2588"],
    "I": ["\u2588\u2588\u2588\u2588\u2588", "  \u2588  ", "  \u2588  ", "  \u2588  ", "\u2588\u2588\u2588\u2588\u2588"],
    "J": ["  \u2588\u2588\u2588", "   \u2588 ", "   \u2588 ", "\u2588  \u2588 ", "\u2588\u2588\u2588  "],
    "K": ["\u2588   \u2588", "\u2588  \u2588 ", "\u2588\u2588\u2588  ", "\u2588  \u2588 ", "\u2588   \u2588"],
    "L": ["\u2588    ", "\u2588    ", "\u2588    ", "\u2588    ", "\u2588\u2588\u2588\u2588\u2588"],
    "M": ["\u2588   \u2588", "\u2588\u2588 \u2588\u2588", "\u2588 \u2588 \u2588", "\u2588   \u2588", "\u2588   \u2588"],
    "N": ["\u2588   \u2588", "\u2588\u2588  \u2588", "\u2588 \u2588 \u2588", "\u2588  \u2588\u2588", "\u2588   \u2588"],
    "O": ["\u2588\u2588\u2588\u2588\u2588", "\u2588   \u2588", "\u2588   \u2588", "\u2588   \u2588", "\u2588\u2588\u2588\u2588\u2588"],
    "P": ["\u2588\u2588\u2588\u2588\u2588", "\u2588   \u2588", "\u2588\u2588\u2588\u2588\u2588", "\u2588    ", "\u2588    "],
    "Q": ["\u2588\u2588\u2588\u2588\u2588", "\u2588   \u2588", "\u2588   \u2588", "\u2588  \u2588\u2588", "\u2588 \u2588\u2588 "],
    "R": ["\u2588\u2588\u2588\u2588\u2588", "\u2588   \u2588", "\u2588\u2588\u2588\u2588\u2588", "\u2588  \u2588 ", "\u2588   \u2588"],
    "S": ["\u2588\u2588\u2588\u2588\u2588", "\u2588    ", "\u2588\u2588\u2588\u2588\u2588", "    \u2588", "\u2588\u2588\u2588\u2588\u2588"],
    "T": ["\u2588\u2588\u2588\u2588\u2588", "  \u2588  ", "  \u2588  ", "  \u2588  ", "  \u2588  "],
    "U": ["\u2588   \u2588", "\u2588   \u2588", "\u2588   \u2588", "\u2588   \u2588", "\u2588\u2588\u2588\u2588\u2588"],
    "V": ["\u2588   \u2588", "\u2588   \u2588", "\u2588   \u2588", " \u2588 \u2588 ", "  \u2588  "],
    "W": ["\u2588   \u2588", "\u2588   \u2588", "\u2588 \u2588 \u2588", "\u2588\u2588 \u2588\u2588", "\u2588   \u2588"],
    "X": ["\u2588   \u2588", " \u2588 \u2588 ", "  \u2588  ", " \u2588 \u2588 ", "\u2588   \u2588"],
    "Y": ["\u2588   \u2588", " \u2588 \u2588 ", "  \u2588  ", "  \u2588  ", "  \u2588  "],
    "Z": ["\u2588\u2588\u2588\u2588\u2588", "   \u2588 ", "  \u2588  ", " \u2588   ", "\u2588\u2588\u2588\u2588\u2588"],
    "0": ["\u2588\u2588\u2588\u2588\u2588", "\u2588  \u2588\u2588", "\u2588 \u2588 \u2588", "\u2588\u2588  \u2588", "\u2588\u2588\u2588\u2588\u2588"],
    "1": ["  \u2588  ", " \u2588\u2588  ", "  \u2588  ", "  \u2588  ", "\u2588\u2588\u2588\u2588\u2588"],
    "2": ["\u2588\u2588\u2588\u2588\u2588", "    \u2588", "\u2588\u2588\u2588\u2588\u2588", "\u2588    ", "\u2588\u2588\u2588\u2588\u2588"],
    "3": ["\u2588\u2588\u2588\u2588\u2588", "    \u2588", "\u2588\u2588\u2588\u2588\u2588", "    \u2588", "\u2588\u2588\u2588\u2588\u2588"],
    "4": ["\u2588   \u2588", "\u2588   \u2588", "\u2588\u2588\u2588\u2588\u2588", "    \u2588", "    \u2588"],
    "5": ["\u2588\u2588\u2588\u2588\u2588", "\u2588    ", "\u2588\u2588\u2588\u2588\u2588", "    \u2588", "\u2588\u2588\u2588\u2588\u2588"],
    "6": ["\u2588\u2588\u2588\u2588\u2588", "\u2588    ", "\u2588\u2588\u2588\u2588\u2588", "\u2588   \u2588", "\u2588\u2588\u2588\u2588\u2588"],
    "7": ["\u2588\u2588\u2588\u2588\u2588", "    \u2588", "   \u2588 ", "  \u2588  ", " \u2588   "],
    "8": ["\u2588\u2588\u2588\u2588\u2588", "\u2588   \u2588", "\u2588\u2588\u2588\u2588\u2588", "\u2588   \u2588", "\u2588\u2588\u2588\u2588\u2588"],
    "9": ["\u2588\u2588\u2588\u2588\u2588", "\u2588   \u2588", "\u2588\u2588\u2588\u2588\u2588", "    \u2588", "\u2588\u2588\u2588\u2588\u2588"],
    " ": ["     ", "     ", "     ", "     ", "     "],
}


def figlet(text: str) -> str:
    text = text.upper()[:30]
    glyphs = [_FIG.get(c, _FIG[" "]) for c in text]
    rows = []
    for i in range(5):
        rows.append(" ".join(g[i] for g in glyphs))
    return "\n".join(rows)


# --------------------------------------------------------------------------
# keyword -> emoji translator
# --------------------------------------------------------------------------
EMOJI_WORDS = {
    "love": "\u2764\ufe0f", "heart": "\u2764\ufe0f", "fire": "\U0001f525",
    "star": "\u2b50", "cat": "\U0001f431", "dog": "\U0001f436",
    "sun": "\u2600\ufe0f", "moon": "\U0001f319", "rain": "\U0001f327\ufe0f",
    "sad": "\U0001f622", "happy": "\U0001f600", "cry": "\U0001f62d",
    "laugh": "\U0001f602", "cool": "\U0001f60e", "angry": "\U0001f620",
    "sleep": "\U0001f634", "wink": "\U0001f609", "kiss": "\U0001f48b",
    "music": "\U0001f3b6", "book": "\U0001f4da", "car": "\U0001f698",
    "money": "\U0001f4b0", "coin": "\U0001fa99", "gem": "\U0001f48e",
    "flower": "\U0001f33a", "tree": "\U0001f333", "skull": "\U0001f480",
    "ghost": "\U0001f47b", "robot": "\U0001f916", "rocket": "\U0001f680",
    "earth": "\U0001f30e", "water": "\U0001f423", "food": "\U0001f32f",
    "pizza": "\U0001f355", "cake": "\U0001f370", "coffee": "\u2615",
    "game": "\U0001f3ae", "phone": "\U0001f4de", "time": "\u23f0",
    "lock": "\U0001f512", "key": "\U0001f511", "gift": "\U0001f381",
    "ball": "\u26bd", "cup": "\U0001f3c6", "medal": "\U0001f396\ufe0f",
    "crown": "\U0001f451", "eye": "\U0001f441\ufe0f", "hand": "\U0001f44b",
    "yes": "\u2705", "no": "\u274c", "win": "\U0001f389", "luck": "\U0001f970",
}

_RANDOM_EMOJI = list("".join(EMOJI_WORDS.values()))


def emoji_for(word: str) -> str:
    return EMOJI_WORDS.get(word.lower(), "")


def random_emoji() -> str:
    return random.choice(_RANDOM_EMOJI)
