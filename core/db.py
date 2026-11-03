# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""MongoDB access layer for Aisha.

A single lazily-created Motor client; the database object is module-level
so tests can swap it with an in-memory fake via `set_db()` without any
network dependency.
"""
import logging

from motor.motor_asyncio import AsyncIOMotorClient

import config

logger = logging.getLogger(__name__)

_client = None
_db = None


def db():
    """Return the shared database handle (creating it on first use)."""
    global _client, _db
    if _db is None:
        _client = AsyncIOMotorClient(config.MONGO_URI)
        _db = _client[config.DB_NAME]
    return _db


def set_db(fake) -> None:
    """Tests only: replace the database handle."""
    global _client, _db
    _db = fake


def close() -> None:
    global _client, _db
    if _client:
        try:
            _client.close()
        except Exception:
            pass
    _client = None
    _db = None
