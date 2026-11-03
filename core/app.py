# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""App assembly: builds the kurigram Client and registers all handlers.

Each handler module exposes ``register(add, filters, add_cb)``; the list
below is the single source of truth for what gets wired. Modules that do
not exist yet (phased build) are skipped silently.
"""
import importlib
import logging

from pyrogram import Client, filters

import config

logger = logging.getLogger(__name__)

HANDLER_MODULES = [
    "start",
    "economy",
    "profile",
    "arcade",
    "duel",
    "games.trivia",
    "games.luckybox",
    "games.wordchain",
    "games.typerace",
    "extras",
    "fun",
    "sticker",
    "kingdom",
    "ttt",
    "bingo",
    "social",
    "quote",
    "font",
    "confess",
    "td",
    "emoji",
    "pet",
    "crush",
    "welcome",
    "broadcast",
    "chatbot",
    "diag",
    "presence",
    "reactions",
    "aisha",
    "owner",
]

HANDLER_COUNT = 0
CLIENT = None


def register_all(app) -> int:
    """Attach every available handler group; returns handler count."""
    global HANDLER_COUNT
    n = 0

    def add(fn, flt, group=0):
        nonlocal n
        from pyrogram.handlers import MessageHandler
        app.add_handler(MessageHandler(fn, flt), group)
        n += 1

    def add_cb(fn, pat):
        nonlocal n
        from pyrogram.handlers import CallbackQueryHandler
        app.add_handler(CallbackQueryHandler(fn, pat), 0)
        n += 1

    def add_raw(fn):
        nonlocal n
        from pyrogram.handlers import RawUpdateHandler
        app.add_handler(RawUpdateHandler(fn), 0)
        n += 1

    def add_chat_member(fn):
        nonlocal n
        from pyrogram.handlers import ChatMemberUpdatedHandler
        app.add_handler(ChatMemberUpdatedHandler(fn), 0)
        n += 1

    def add_msg_edited(fn):
        nonlocal n
        from pyrogram.handlers import MessageHandler
        app.add_handler(MessageHandler(fn, filters.edited), 0)
        n += 1

    for name in HANDLER_MODULES:
        try:
            mod = importlib.import_module(f"handlers.{name}")
        except ModuleNotFoundError as e:
            logger.debug("handler module %s not present yet: %s", name, e)
            continue
        reg = getattr(mod, "register", None)
        if callable(reg):
            import inspect
            params = inspect.signature(reg).parameters
            kwargs = {}
            for opt, fn in (("add_raw", add_raw),
                            ("add_msg_edited", add_msg_edited),
                            ("add_chat_member", add_chat_member)):
                if opt in params:
                    kwargs[opt] = fn
            reg(add, filters, add_cb, **kwargs)
    HANDLER_COUNT = n
    return n


def build_client(session_name: str = "aisha") -> Client:
    if not config.API_ID or not config.API_HASH:
        raise SystemExit(
            "API_ID and API_HASH are required "
            "(get them at https://my.telegram.org)")
    app = Client(
        session_name,
        api_id=config.API_ID,
        api_hash=config.API_HASH,
        bot_token=config.BOT_TOKEN,
        in_memory=True,
    )
    global CLIENT
    CLIENT = app
    register_all(app)
    return app
