# Authored By Iota Coders © 2025-2026
# SPDX-License-Identifier: MIT
"""AI provider chain — OpenAI-compatible endpoints with key rotation.

Providers are tried in order; within a provider, keys rotate round-robin.
`call_ai` NEVER raises: on total failure it returns None so the caller can
fall back to the offline sass engine. No keys configured → instant None.
"""
import json
import logging
import urllib.request

import config

logger = logging.getLogger(__name__)

PROVIDERS = [
    ("apinex", "https://api.apinex.bond/v1/chat/completions",
      [config.APINEX_MODEL] + (
          [config.APINEX_FALLBACK_MODEL]
          if config.APINEX_FALLBACK_MODEL and config.APINEX_FALLBACK_MODEL != config.APINEX_MODEL
          else []
      ),
      [config.APINEX_API_KEY] if config.APINEX_API_KEY else []),
    ("groq", "https://api.groq.com/openai/v1/chat/completions",
      [config.GROQ_MODEL], config.GROQ_KEYS),
    ("gemini", "https://generativelanguage.googleapis.com/v1beta/openai"
               "/chat/completions",
      [config.GEMINI_MODEL], config.GEMINI_KEYS),
    ("openrouter", "https://openrouter.ai/api/v1/chat/completions",
      [config.OPENROUTER_MODEL], config.OPENROUTER_KEYS),
]

_key_cursor = 0


def has_keys() -> bool:
    return any(keys for _, _, _, keys in PROVIDERS)


def _post_json(url: str, payload: dict, api_key: str, timeout: int):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def call_ai_sync(system: str, turns: list[dict]) -> str | None:
    """Blocking call; run via asyncio.to_thread. Returns reply text or None.

    turns = [{"role": "user"|"assistant", "content": str}, ...]
    """
    global _key_cursor
    if not has_keys():
        return None
    messages = [{"role": "system", "content": system}] + turns
    payload = {"messages": messages,
               "temperature": 0.9,
               "max_tokens": 220}
    for name, url, models, keys in PROVIDERS:
        for model in models:
            for _ in keys:
                key = keys[_key_cursor % len(keys)]
                _key_cursor += 1
                try:
                    body = dict(payload, model=model)
                    data = _post_json(url, body, key, config.AI_TIMEOUT)
                    text = (data["choices"][0]["message"]["content"] or "").strip()
                    if text:
                        return text
                except Exception as e:
                    logger.debug("provider %s model %s failed: %s", name, model, e)
                    continue
    return None
