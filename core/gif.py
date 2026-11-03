# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""Aisha GIF provider — GIPHY-backed gif source.

Why this design:
  • GIPHY's live search is the GIF source. Hardcoded media-ID fallback
    lists rot (deleted / rate-limited / moderated) and break silently —
    this bot's earlier failure mode. So we ONLY use the live search, and
    if it is ever unreachable we return None and callers send text only
    (never a broken image).
  • Aisha's MTProto transport cannot always rely on Telegram fetching a
    hotlinked URL, so delivery downloads the bytes and uploads them
    directly (see handlers/fun.py). This module owns the *search/select*
    logic; delivery is the caller's concern.

SETUP: uses AISHA_GIPHY_API_KEY (config.GIPHY_API_KEY). Falls back to
a shared public demo key if unset (rate-limited — get your own).
"""
import aiohttp
import logging
import random
import time

import config

logger = logging.getLogger(__name__)

# Shared public GIPHY beta key (historical default). Replace with your own
# free key via AISHA_GIPHY_API_KEY for production reliability.
_PUBLIC_DEMO_KEY = "dc6zaTOxFJmzC"

GIPHY_API_KEY = (getattr(config, "GIPHY_API_KEY", "") or "").strip() or _PUBLIC_DEMO_KEY
GIPHY_SEARCH_URL = "https://api.giphy.com/v1/gifs/search"

# In-memory cache: query -> (timestamp, [gif_urls], ttl)
# Failed/empty searches are cached with a short TTL so a dead/unreachable
# GIPHY doesn't make every single command wait out the full timeout.
_CACHE: dict = {}
_CACHE_TTL = 600        # successful search: 10 min
_FAIL_TTL = 60          # failed search: 1 min (recover if GIPHY returns)

# Mood/action -> best search terms (natural phrasing keeps search quality
# high; each call picks a random result from the top N).
_SEARCH_TERMS = {
    "happy":    "anime happy excited",
    "sad":      "anime sad crying",
    "love":     "anime love heart cute",
    "laugh":    "anime laughing lol",
    "angry":    "anime angry mad rage",
    "cute":     "anime cute aww",
    "dance":    "anime dance happy",
    "cool":     "anime cool sunglasses",
    "surprise": "anime surprised shocked",
    "default":  "anime wave hello",
    "slap":     "anime slap",
    "punch":    "anime punch",
    "kiss":     "anime kiss",
    "hug":      "anime hug",
    "bite":     "anime bite",
    "pat":      "anime head pat",
    "murder":   "anime knife dramatic",
    "welcome":  "anime welcome wave",
    "card_win": "anime celebration win",
    "card_tie": "anime tie draw",
    "attack_win": "anime victory battle",
    "ludo":     "dice roll game",
    "fall":     "anime falling cliff",
    "throw":    "anime throw across room",
    "kick":     "anime kick",
    "funny":    "funny meme reaction",
    "highfive": "anime high five",
    "poke":     "anime poke",
    "tickle":   "anime tickle",
    "facepalm": "anime facepalm",
    "pie":      "anime pie face",
    "trip":     "anime trip",
    "freeze":   "anime freeze",
    "zap":      "anime zap lightning",
    "dancewith": "anime dance",
    "cuddle":   "anime cuddle",
    "lick":     "anime lick",
    "bonk":     "anime bonk",
    "glare":    "anime glare",
    "feed":     "anime feed",
    "beer":     "anime cheers drink",
    "boop":     "anime boop nose",
    "ruffle":   "anime hair ruffle",
    "smooch":   "anime kiss",
    "tackle":   "anime tackle",
    "pinch":    "anime pinch",
    "fistbump": "anime fist bump",
    "bearhug":  "anime bear hug",
    "foreheadkiss": "anime kiss forehead",
    "spin":     "anime spin",
    "dab":      "anime dab",
    "flex":     "anime flex",
    "nom":      "anime eat",
    "squish":   "anime squish cute",
    "yeet":     "anime yeet throw",
    "stare":    "anime stare",
    "shoulderpunch": "anime punch shoulder",
    "cheekpinch": "anime cheek pinch",
    "headrub":  "anime head rub",
    "grouphug": "anime group hug",
    "suplex":   "anime suplex wrestling",
    "boopboop": "anime boop",
    "cheekkiss": "anime kiss cheek",
    "headpat":  "anime head pat",
}


async def _giphy_search(query: str, limit: int = 20) -> list:
    """Search GIPHY for `query`. Returns direct .gif URLs, or [] on any
    failure (never raises)."""
    now = time.time()
    cached = _CACHE.get(query)
    if cached and now - cached[0] < cached[2]:
        return cached[1]

    try:
        async with aiohttp.ClientSession() as s:
            params = {
                "q": query,
                "api_key": GIPHY_API_KEY,
                "limit": limit,
                "rating": "pg-13",
                "lang": "en",
            }
            async with s.get(
                GIPHY_SEARCH_URL, params=params,
                timeout=aiohttp.ClientTimeout(total=3),
            ) as r:
                if r.status == 429:
                    logger.warning(
                        "GIPHY rate limit (429). Set AISHA_GIPHY_API_KEY "
                        "(own free key) for reliable production use.")
                    _CACHE[query] = (now, [], _FAIL_TTL)
                    return []
                if r.status != 200:
                    logger.debug("GIPHY non-200 (%s) for '%s'", r.status, query)
                    _CACHE[query] = (now, [], _FAIL_TTL)
                    return []
                data = await r.json()
    except Exception as e:
        logger.debug("GIPHY search failed for '%s': %s", query, e)
        _CACHE[query] = (now, [], _FAIL_TTL)  # don't retry for a bit
        return []

    urls = []
    for item in data.get("data", []):
        try:
            gif_url = (
                item.get("images", {}).get("downsized", {}).get("url")
                or item.get("images", {}).get("original", {}).get("url")
            )
            if gif_url:
                urls.append(gif_url)
        except (KeyError, TypeError, AttributeError):
            continue

    # Cache both hits (long TTL) and misses (short TTL) so a dead GIPHY
    # degrades to instant text instead of a per-command timeout wait.
    _CACHE[query] = (now, urls, _CACHE_TTL if urls else _FAIL_TTL)
    return urls


async def get_gif_for_mood(mood: str):
    """Return one GIF URL for `mood`, or None if GIPHY unreachable."""
    query = _SEARCH_TERMS.get(mood, _SEARCH_TERMS["default"])
    try:
        urls = await _giphy_search(query)
        if urls:
            return random.choice(urls)
    except Exception as e:
        logger.debug("get_gif_for_mood error for '%s': %s", mood, e)
    return None


async def get_gif_for_query(query: str, fallback_mood: str = "default"):
    """Free-text GIF search; falls back to a mood GIF, then None."""
    try:
        urls = await _giphy_search(query)
        if urls:
            return random.choice(urls)
    except Exception as e:
        logger.debug("get_gif_for_query error for '%s': %s", query, e)
    return await get_gif_for_mood(fallback_mood)


# ── Aisha delivery helpers (bytes, since MTProto hotlink fetch is flaky) ──
_GIF_BYTES_CACHE: dict = {}


async def get_gif_bytes(mood: str):
    """Return raw GIF bytes for `mood`, or None. Downloads + caches the
    URL chosen by get_gif_for_mood so we only hit the network once."""
    url = await get_gif_for_mood(mood)
    if not url:
        return None
    if url in _GIF_BYTES_CACHE:
        return _GIF_BYTES_CACHE[url]
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                url, timeout=aiohttp.ClientTimeout(total=5),
                headers={"User-Agent": "Mozilla/5.0"},
            ) as r:
                if r.status != 200:
                    return None
                data = await r.read()
        if data and data[:6] in (b"GIF89a", b"GIF87a"):
            _GIF_BYTES_CACHE[url] = data
            return data
    except Exception as e:
        logger.debug("gif download failed for %s: %s", e)
    return None


async def send_animation_url(chat_id, url: str, caption: str, reply_to,
                             bot_token: str, parse_mode: str = "HTML") -> bool:
    """Send an animation BY URL through the Bot API so Telegram's servers
    fetch it (instant, no in-bot download+re-upload). Returns True if
    Telegram accepted it. Used by fun.py and the sticker/gif reply system.
    """
    if not bot_token or not url:
        return False
    api = f"https://api.telegram.org/bot{bot_token}/sendAnimation"
    payload = {
        "chat_id": chat_id,
        "animation": url,
        "reply_to_message_id": reply_to,
    }
    if caption:
        payload["caption"] = caption
        payload["parse_mode"] = parse_mode
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                api, json=payload,
                timeout=aiohttp.ClientTimeout(total=12),
            ) as r:
                return r.status == 200
    except Exception as e:
        logger.debug("send_animation_url failed: %s", e)
        return False

