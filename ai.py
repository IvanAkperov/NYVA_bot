"""
Асинхронный клиент Mistral поверх aiohttp (уже стоит вместе с aiogram).
Не блокирует бота, умеет JSON-режим и картинки.
"""
import asyncio
import json
import logging
import re

import aiohttp

from config import MISTRAL_API_KEY

log = logging.getLogger("ai")

API_URL = "https://api.mistral.ai/v1/chat/completions"
TEXT_MODEL = "mistral-small-latest"
VISION_MODELS = ("mistral-small-latest", "pixtral-12b-latest")

_session: aiohttp.ClientSession | None = None


class AIError(Exception):
    pass


async def _get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60), trust_env=True)
    return _session


async def close() -> None:
    if _session and not _session.closed:
        await _session.close()


def clean(text: str) -> str:
    """Убираем markdown-звёздочки, которые в телеге без parse_mode выглядят мусором."""
    return text.replace("**", "").replace("__", "").strip()


async def chat(messages: list, *, model: str = TEXT_MODEL, temperature: float = 0.8,
               top_p: float = 0.95, max_tokens: int = 300, json_mode: bool = False, **extra) -> str:
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max_tokens,
    }
    for key in ("frequency_penalty", "presence_penalty"):
        if key in extra:
            payload[key] = extra[key]
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    headers = {"Authorization": f"Bearer {MISTRAL_API_KEY}", "Content-Type": "application/json"}
    session = await _get_session()
    last_error = None
    for attempt in range(3):
        try:
            async with session.post(API_URL, json=payload, headers=headers) as resp:
                if resp.status == 429 or resp.status >= 500:
                    last_error = f"HTTP {resp.status}"
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                data = await resp.json(content_type=None)
                if resp.status != 200:
                    raise AIError(f"Mistral {resp.status}: {data}")
                content = data["choices"][0]["message"]["content"]
                if isinstance(content, list):  # на всякий случай: ответ частями
                    content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
                return content.strip()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            last_error = repr(e)
            await asyncio.sleep(2 * (attempt + 1))
    raise AIError(f"Mistral не ответил: {last_error}")


async def chat_json(messages: list, **kwargs) -> dict:
    text = await chat(messages, json_mode=True, **kwargs)
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if match:
            return json.loads(match.group(0))
        raise AIError(f"Не JSON: {text[:200]}")


async def vision(system_prompt: str, question: str, image_b64: str, max_tokens: int = 250,
                 temperature: float = 0.8) -> str:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": [
            {"type": "text", "text": question},
            {"type": "image_url", "image_url": f"data:image/jpeg;base64,{image_b64}"},
        ]},
    ]
    last = None
    for model in VISION_MODELS:
        try:
            return await chat(messages, model=model, max_tokens=max_tokens, temperature=temperature)
        except AIError as e:
            last = e
            log.warning("vision model %s failed: %s", model, e)
    raise AIError(str(last))
