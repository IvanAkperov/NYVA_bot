"""
Асинхронный клиент нейросети поверх aiohttp.
Работает с OpenRouter (если в .env есть OPENROUTER_API_KEY) или с Mistral.
Оба API OpenAI-совместимые, поэтому код общий.
"""
import asyncio
import json
import logging
import re

import aiohttp

from config import AI_MODEL, AI_PROVIDER, AI_VISION_MODEL, MISTRAL_API_KEY, OPENROUTER_API_KEY

log = logging.getLogger("ai")

if AI_PROVIDER == "openrouter":
    API_URL = "https://openrouter.ai/api/v1/chat/completions"
    API_KEY = OPENROUTER_API_KEY
    EXTRA_HEADERS = {"HTTP-Referer": "https://t.me/NYVA_bot", "X-Title": "NYVA bot"}
else:
    API_URL = "https://api.mistral.ai/v1/chat/completions"
    API_KEY = MISTRAL_API_KEY
    EXTRA_HEADERS = {}

TEXT_MODEL = AI_MODEL
MIN_TOKENS = 1000 if AI_PROVIDER == "openrouter" else 0  # «думающим» моделям нужен запас, длину держит промпт

_session: aiohttp.ClientSession | None = None


class AIError(Exception):
    pass


async def _get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=90), trust_env=True)
    return _session


async def close() -> None:
    if _session and not _session.closed:
        await _session.close()


def clean(text: str) -> str:
    """Убираем markdown-звёздочки и случайные «мысли» модели."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    return text.replace("**", "").replace("__", "").strip()


async def chat(messages: list, *, model: str | None = None, temperature: float = 0.8,
               top_p: float = 0.95, max_tokens: int = 300, json_mode: bool = False, **extra) -> str:
    payload = {
        "model": model or TEXT_MODEL,
        "messages": messages,
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max(max_tokens, MIN_TOKENS),
    }
    for key in ("frequency_penalty", "presence_penalty"):
        if key in extra:
            payload[key] = extra[key]
    if AI_PROVIDER == "openrouter":
        payload["reasoning"] = {"exclude": True}
    elif json_mode:
        payload["response_format"] = {"type": "json_object"}

    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json", **EXTRA_HEADERS}
    session = await _get_session()
    last_error = None
    for attempt in range(3):
        try:
            async with session.post(API_URL, json=payload, headers=headers) as resp:
                data = await resp.json(content_type=None)
                if resp.status == 429 or resp.status >= 500:
                    last_error = f"HTTP {resp.status}: {str(data)[:300]}"
                    await asyncio.sleep(3 * (attempt + 1))
                    continue
                if resp.status != 200 or "choices" not in data:
                    raise AIError(f"{AI_PROVIDER} {resp.status}: {str(data)[:500]}")
                content = data["choices"][0]["message"].get("content") or ""
                if isinstance(content, list):
                    content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
                content = clean(content)
                if not content:
                    last_error = "пустой ответ"
                    continue
                return content
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            last_error = repr(e)
            await asyncio.sleep(3 * (attempt + 1))
    raise AIError(f"{AI_PROVIDER} не ответил: {last_error}")


async def chat_json(messages: list, **kwargs) -> dict:
    messages = list(messages)
    messages[-1] = {**messages[-1], "content": str(messages[-1]["content"]) +
                    "\n\nОтветь СТРОГО одним JSON-объектом, без пояснений и без ```."}
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
    data_url = f"data:image/jpeg;base64,{image_b64}"
    image_part = ({"type": "image_url", "image_url": {"url": data_url}} if AI_PROVIDER == "openrouter"
                  else {"type": "image_url", "image_url": data_url})
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": [{"type": "text", "text": question}, image_part]},
    ]
    return await chat(messages, model=AI_VISION_MODEL, max_tokens=max_tokens, temperature=temperature)
